from __future__ import annotations

import os
import threading
from pathlib import Path

from eqsanscli.integrations.drtsans_runner import ReductionResult, run_reduction
from eqsanscli.integrations.json_builder import build_reduction_json, save_reduction_json
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.config_manager import get_config


def timeslice_estimate(config_params: dict, duration_s: int) -> dict | None:
    """How many time slices a reduction will produce, or None if not slicing.

    Slicing multiplies the work: drtsans reduces each slice independently and
    writes a full set of files (I(Q), I(Qx,Qy), processed NeXus) per slice. A
    1-hour run at a 5 s interval is 720 slices — hours of compute and a lot of
    disk. Surfacing the count up front lets the user sanity-check the interval
    against the timescale they actually care about.

    Returns {slices, interval_s, duration_s} or None when time-slicing is off,
    the interval is not positive, or the run duration is unknown (can't count).
    """
    if not config_params.get("usetimeslice"):
        return None
    try:
        interval = float(config_params.get("timesliceinterval") or 0)
    except (TypeError, ValueError):
        return None
    if interval <= 0 or duration_s <= 0:
        return None
    import math
    slices = int(math.ceil(duration_s / interval))
    return {"slices": slices, "interval_s": interval, "duration_s": int(duration_s)}


def make_slice_progress(emit, label: str = "", total: int | None = None,
                         every: int = 25, min_seconds: float = 30.0):
    """Build a progress callback for run_reduction's per-line `progress_cb`.

    drtsans writes one `SaveNexus to …_<slice>_processed.nxs` line per completed
    time slice. This counts them and calls `emit(message)` — throttled to at most
    one line per `every` slices AND `min_seconds` apart, so a 720-slice run gives
    a readable heartbeat instead of 720 lines. `total` (expected slices), when
    known, adds `N/total (P%)`.
    """
    import re
    import time
    marker = re.compile(r"savenexus.*processed\.nxs", re.IGNORECASE)
    st = {"count": 0, "last_t": 0.0, "last_count": 0}

    def cb(line: str) -> None:
        if not marker.search(line):
            return
        st["count"] += 1
        n = st["count"]
        now = time.time()
        if (n - st["last_count"]) < every and (now - st["last_t"]) < min_seconds:
            return
        st["last_count"] = n
        st["last_t"] = now
        frac = f"/{total}" if total else ""
        pct = f" ({min(100, 100 * n // total)}%)" if total else ""
        lbl = f"{label}: " if label else ""
        emit(f"      [dim]⏳ {lbl}slice {n}{frac}{pct}[/dim]")

    return cb


def output_dir_problem(output_dir: str) -> str | None:
    """Return a human message if we cannot write reductions to `output_dir`,
    else None. Cheap check done before a batch so a bad `/set outputdir` fails
    with one clear line instead of crashing partway through drtsans.

    The dir need not exist yet (reduce_row creates it) — so if it is missing we
    check the nearest existing ancestor, which is where mkdir will try to write.
    """
    path = Path(os.path.abspath(output_dir))
    probe = path
    while not probe.exists():
        if probe.parent == probe:      # reached the filesystem root
            break
        probe = probe.parent
    if not probe.exists():
        return f"path does not exist and cannot be created: {output_dir}"
    if probe.is_dir() and not os.access(probe, os.W_OK):
        who = str(path) if probe == path else f"{output_dir} (no write access to {probe})"
        return f"permission denied — cannot write to {who}"
    if not probe.is_dir():
        return f"not a directory: {probe}"
    return None


def reduce_row(
    row: WorkingTableRow,
    ipts: int,
    user_configs: dict[str, dict],
    output_dir: str = "./output/",
    filename_suffix: str = "",
    cancel_event: threading.Event | None = None,
    drtsans_version: str = "default",
    progress_cb=None,
) -> ReductionResult:
    # Cancelled before we started — return at once without building a JSON or
    # spawning drtsans. In a parallel batch, the executor keeps handing queued
    # rows to freed workers after the user cancels; this makes each such row a
    # no-op instead of a fresh ~1s drtsans launch that is immediately killed, so
    # a single cancel drains the whole queue at once.
    if cancel_event is not None and cancel_event.is_set():
        row.status = "cancelled"
        return ReductionResult(
            success=False, json_path="", output_file="",
            elapsed_seconds=0.0, stdout="", stderr="Cancelled before start.",
            return_code=-99, cancelled=True,
        )

    config_params = get_config(row.configuration, user_configs)

    # Per-row output directory wins over the session-wide one (and over the
    # config's own `outputdir`, which build_reduction_json otherwise uses) — this
    # is how a data-heavy time-sliced row is kept in its own folder. Empty
    # override → session-wide, exactly as before.
    effective_dir = (getattr(row, "output_override", "") or "").strip() or output_dir
    if effective_dir != config_params.get("outputdir"):
        config_params = {**config_params, "outputdir": effective_dir}

    output_name = row.output_stem
    if filename_suffix:
        output_name += f"_{filename_suffix}"

    json_data = build_reduction_json(
        ipts=ipts,
        scattering_run=row.scattering_run,
        sample_name=row.sample_name,
        transmission_run=row.transmission_run,
        background_scatt=row.background_scatt,
        background_trans=row.background_trans,
        empty_beam=row.empty_beam,
        thickness=row.thickness,
        config_params=config_params,
        output_dir=effective_dir,
        output_filename=output_name,
    )

    # Writing the JSON is the first thing that touches the output dir. If it is
    # not writable (a mistyped or read-only outputdir), fail this row with a
    # clear message instead of letting PermissionError escape the worker and
    # crash the whole app mid-batch.
    json_path = os.path.join(effective_dir, f"{output_name}.json")
    try:
        Path(effective_dir).mkdir(parents=True, exist_ok=True)
        save_reduction_json(json_data, json_path)
    except OSError as exc:
        row.status = "error"
        return ReductionResult(
            success=False, json_path="", output_file="",
            elapsed_seconds=0.0, stdout="",
            stderr=f"Cannot write to output directory {effective_dir}: {exc.strerror or exc}",
            return_code=-98,
        )

    result = run_reduction(json_path, cancel_event=cancel_event,
                           drtsans_version=drtsans_version, progress_cb=progress_cb)

    # Locate the produced I(Q). A single reduction writes `<name>_Iq.dat` or
    # `<name>_frame_0_Iq.dat`; a time-slice reduction writes one per slice
    # (`<name>_0_frame_0_Iq.dat`, `<name>_100_frame_0_Iq.dat`, …), so a glob is
    # the only way to catch every layout.
    import glob
    standard_output = os.path.join(effective_dir, f"{output_name}_Iq.dat")
    frame0_output = os.path.join(effective_dir, f"{output_name}_frame_0_Iq.dat")
    produced = sorted(glob.glob(os.path.join(effective_dir, f"{output_name}*_Iq.dat")))

    if os.path.exists(frame0_output):
        result.output_file = frame0_output
    elif os.path.exists(standard_output):
        result.output_file = standard_output
    elif produced:
        result.output_file = produced[0]
    else:
        result.output_file = standard_output

    # Rescue a false failure: drtsans can write every I(Q) file and THEN exit
    # nonzero on a GUI/display teardown — an interactive Qt plot attempted under
    # `--simple-prompt`, or a dropped X11 connection ("ICE default IO error
    # handler ... exit()"). The science is complete; without this the row would
    # be marked `error` and needlessly re-reduced (a time-slice run is an hour+).
    # Gate tightly: outputs must exist, the tail must carry a recognizable
    # display-teardown signature, AND there must be no Python traceback (which
    # would mean a genuine crash that happened to also touch the GUI).
    if not result.success and not result.cancelled and produced:
        tail = (result.stdout[-8000:] + "\n" + result.stderr).lower()
        display_signatures = (
            "cannot install event loop hook",
            "ice default io error handler",
            "xio:  fatal io error",
            "xio: fatal io error",
            "could not connect to display",
            "qxcbconnection",
            "qt.qpa",
        )
        has_traceback = "traceback (most recent call last)" in tail
        if not has_traceback and any(sig in tail for sig in display_signatures):
            result.success = True
            result.note = (
                f"drtsans exited {result.return_code} on a non-fatal GUI/display "
                f"error after writing {len(produced)} I(Q) file(s) — reduction is "
                f"complete."
            )

    if result.cancelled:
        row.status = "cancelled"
    elif result.success:
        row.status = "done"
        row.output_file = result.output_file
    else:
        row.status = "error"

    return result


# --------------------------------------------------------------------------
# Preflight — what a row must have before drtsans can reduce it
# --------------------------------------------------------------------------
#
# Empty beam is mandatory: json_builder puts it in BOTH beamCenter.runNumber
# and emptyTransmission.runNumber, so without it the reduction has no beam
# centre. Transmission and background are advisory — drtsans accepts a
# transmission value instead of a run, and background-cell rows deliberately
# have no background (see matching_service.assign_background).


def blocking_problems(row: WorkingTableRow) -> list[str]:
    """Reasons this row cannot be reduced at all."""
    problems: list[str] = []
    if not str(row.scattering_run).strip():
        problems.append("no scattering run")
    if not str(row.empty_beam).strip():
        problems.append("no empty beam (needed for beam centre + empty transmission)")
    return problems


def advisory_problems(row: WorkingTableRow) -> list[str]:
    """Reasons this row will reduce but may not be what the user wants."""
    problems: list[str] = []
    if not str(row.transmission_run).strip():
        problems.append("no transmission")
    if not str(row.background_scatt).strip():
        problems.append("no background")
    try:
        if float(row.thickness) <= 0:
            problems.append(f"thickness={row.thickness}")
    except (TypeError, ValueError):
        problems.append(f"thickness={row.thickness!r} is not a number")
    return problems


def preflight(rows: list[WorkingTableRow]) -> tuple[
    list[tuple[WorkingTableRow, list[str]]], list[tuple[WorkingTableRow, list[str]]]
]:
    """Split `rows` into (blocked, advisory) with their reasons."""
    blocked = [(r, p) for r in rows if (p := blocking_problems(r))]
    advisory = [(r, p) for r in rows if not blocking_problems(r) and (p := advisory_problems(r))]
    return blocked, advisory


def format_preflight(
    blocked: list[tuple[WorkingTableRow, list[str]]],
    advisory: list[tuple[WorkingTableRow, list[str]]],
    *,
    n_selected: int,
    command: str = "/reduce",
) -> str:
    """Explain what is missing and exactly how to fix it."""
    lines: list[str] = []
    if blocked:
        lines.append(
            f"[red]✗ {len(blocked)} of {n_selected} selected row(s) cannot be reduced:[/red]"
        )
        for row, problems in blocked[:15]:
            lines.append(
                f"    Row {row.index}: {row.sample_name} (run {row.scattering_run or '—'}, "
                f"{row.configuration}) — {'; '.join(problems)}"
            )
        if len(blocked) > 15:
            lines.append(f"    ... and {len(blocked) - 15} more")

        missing_empty = [r for r, p in blocked if any("empty beam" in x for x in p)]
        if missing_empty:
            configs = sorted({r.configuration for r in missing_empty})
            lines.append("")
            lines.append(f"  Configurations without an empty beam: [bold]{', '.join(configs)}[/bold]")
            lines.append("  Fix one of these ways:")
            lines.append("    /show catalog                     find the empty-beam run (Class = EmpT)")
            lines.append("    /reclass <run> empty              if it exists but is misclassified,")
            lines.append("    /matchruns                        then re-match (assigns it per config)")
            lines.append(f"    /set --config <id> emp <run>      assign it to one configuration")
            lines.append("    /set <row> emp <run>              or just one row")
        lines.append("")
        lines.append(
            f"  [dim]{command} --skip-missing   reduce the {n_selected - len(blocked)} valid row(s) "
            f"and skip these[/dim]"
        )
        lines.append(
            f"  [dim]{command} --force          send them to drtsans anyway "
            f"(expect failures)[/dim]"
        )

    if advisory:
        if blocked:
            lines.append("")
        lines.append(f"[yellow]⚠ {len(advisory)} row(s) missing optional fields:[/yellow]")
        for row, problems in advisory[:10]:
            lines.append(
                f"    Row {row.index}: {row.sample_name} ({row.configuration}) — {', '.join(problems)}"
            )
        if len(advisory) > 10:
            lines.append(f"    ... and {len(advisory) - 10} more")
    return "\n".join(lines)


def parse_row_selection(selection: str, table: WorkingTable) -> list[int]:
    """Parse row selection: "1", "1-4", "1,3,5", "all" → list of 1-based indices.

    Accepts row index, run number, range, or "all".  For a single token that
    parses as an integer, tries row index first; if no row has that index,
    falls back to matching by scattering run number.
    """
    if selection.lower() == "all":
        return [r.index for r in table.rows]

    valid = {r.index for r in table.rows}
    run_to_index = {r.scattering_run: r.index for r in table.rows}

    indices: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        try:
            if "-" in part:
                start, end = part.split("-", 1)
                indices.extend(range(int(start), int(end) + 1))
            else:
                val = int(part)
                if val in valid:
                    indices.append(val)
                elif part in run_to_index:
                    indices.append(run_to_index[part])
                else:
                    indices.append(val)  # keep for "not found" feedback
        except ValueError:
            # Non-numeric token — try as run number
            if part in run_to_index:
                indices.append(run_to_index[part])
            continue

    return [i for i in indices if i in valid]
