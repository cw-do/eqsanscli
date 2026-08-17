"""Autopilot — fully automated reduction pipeline.

Runs synchronously in a worker thread. Calls reduce_row directly
(not /reduce which is async background). Each step verifies completion
before proceeding.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import textwrap
import threading
import time

from eqsanscli.services.config_manager import ALL_CONFIGS_KEY
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Callable

logger = logging.getLogger(__name__)

_DEFAULT_WRAP_WIDTH = 100

_MP_BASE = "/SNS/EQSANS/shared/NeXusFiles/EQSANS"

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _write_wrapped(write: Callable, text: str, indent: str = "    ", wrap_width: int = 0) -> None:
    w = wrap_width or _DEFAULT_WRAP_WIDTH
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            write("")
            continue
        for line in textwrap.wrap(paragraph, width=w - len(indent)):
            write(f"{indent}{line}")


_DEFAULT_STANDARD_PATTERNS = ["porsil", "porasil"]


def _is_standard_sample(sample_name: str, standard_sample: str | None = None) -> bool:
    """Check if a sample name is the calibration standard.

    If standard_sample is given, matches by case-insensitive substring.
    Otherwise, matches against default patterns (porsil, porasil).
    """
    name_lower = sample_name.lower()
    if standard_sample:
        return standard_sample.lower() in name_lower
    return any(p in name_lower for p in _DEFAULT_STANDARD_PATTERNS)


def _fmt(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _reduce_phase(
    rows: list,
    state: SessionState,
    output_dir: str,
    write: Callable,
    cancel_event: threading.Event | None,
    max_workers: int = 1,
) -> tuple[int, int]:
    """Run reduce_row for a list of rows, sequentially or in parallel.

    Returns (n_success, n_fail). Stops early on cancellation.
    """
    from eqsanscli.services.reduction_service import reduce_row
    from eqsanscli.commands.reduction import _summarize_error

    total = len(rows)
    n_ok = 0
    n_fail = 0

    if max_workers <= 1:
        elapsed_times: list[float] = []
        for i, row in enumerate(rows):
            if cancel_event and cancel_event.is_set():
                write(f"  [yellow]⊘ Cancelled — stopping[/yellow]")
                return n_ok, n_fail
            remaining = total - i
            eta = f"  ETA ~{_fmt(sum(elapsed_times)/len(elapsed_times) * remaining)}" if elapsed_times else ""
            if row.background_scatt:
                bkg_title = state.run_title(row.background_scatt)
                bkg_info = f"  bkg={row.background_scatt}" + (f" [dim]({bkg_title})[/dim]" if bkg_title else "")
            else:
                bkg_info = "  [yellow]no bkg[/yellow]"
            write(f"  [{i+1}/{total}] [yellow]⟳[/yellow] {row.sample_name} ({row.configuration}){bkg_info}  [dim]{remaining} left{eta}[/dim]")
            result = reduce_row(row=row, ipts=state.ipts, user_configs=state.configurations, output_dir=output_dir, cancel_event=cancel_event, drtsans_version=state.drtsans_version)
            elapsed_times.append(result.elapsed_seconds)
            if result.cancelled:
                write(f"  [{i+1}/{total}] [yellow]⊘[/yellow] {row.sample_name} — cancelled")
                return n_ok, n_fail
            elif result.success:
                n_ok += 1
                state.reduced_files.append(result.output_file)
                write(f"  [{i+1}/{total}] [green]✓[/green] {row.sample_name} ({row.configuration}) — {_fmt(result.elapsed_seconds)}")
            else:
                n_fail += 1
                err = _summarize_error(result.log_file, result.err_file)
                write(f"  [{i+1}/{total}] [red]✗[/red] {row.sample_name} ({row.configuration}) — {err}")
    else:
        write(f"  [dim]Running {total} jobs on {max_workers} workers...[/dim]")
        completed = 0
        elapsed_times_p: list[float] = []

        def _do_reduce(row):
            return row, reduce_row(
                row=row, ipts=state.ipts,
                user_configs=state.configurations, output_dir=output_dir,
                cancel_event=cancel_event,
                drtsans_version=state.drtsans_version,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_do_reduce, row): row for row in rows}
            for future in as_completed(futures):
                completed += 1
                row, result = future.result()
                elapsed_times_p.append(result.elapsed_seconds)
                if result.cancelled:
                    write(f"  [{completed}/{total}] [yellow]⊘[/yellow] {row.sample_name} — cancelled")
                elif result.success:
                    n_ok += 1
                    state.reduced_files.append(result.output_file)
                    remaining = total - completed
                    eta = ""
                    if elapsed_times_p:
                        avg = sum(elapsed_times_p) / len(elapsed_times_p)
                        eta = f"  ETA ~{_fmt(avg * remaining / max_workers)}"
                    write(f"  [{completed}/{total}] [green]✓[/green] {row.sample_name} ({row.configuration}) — {_fmt(result.elapsed_seconds)}  [dim]{remaining} left{eta}[/dim]")
                else:
                    n_fail += 1
                    err = _summarize_error(result.log_file, result.err_file)
                    write(f"  [{completed}/{total}] [red]✗[/red] {row.sample_name} ({row.configuration}) — {err}")

    return n_ok, n_fail


def _llm_explain_missing_empty(
    missing_rows: list,
    all_rows: list,
    ipts: int,
    state: SessionState,
) -> str:
    """Use LLM to explain why empty beam is missing and what to do."""
    from eqsanscli.config.settings import AppSettings

    settings = AppSettings.load()
    if not settings.llm.is_configured:
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        return ""

    configs_missing = set()
    samples_missing = []
    for row in missing_rows:
        configs_missing.add(row.configuration)
        samples_missing.append(f"  - {row.sample_name} (run {row.scattering_run}, config {row.configuration})")

    configs_ok = set()
    for row in all_rows:
        if row.empty_beam:
            configs_ok.add(row.configuration)

    prompt = (
        f"IPTS-{ipts} autopilot found {len(missing_rows)} rows missing empty beam.\n"
        f"Configurations missing empty beam: {', '.join(sorted(configs_missing))}\n"
        f"Configurations with empty beam: {', '.join(sorted(configs_ok)) or 'none'}\n"
        f"Total rows: {len(all_rows)}, rows with empty beam: {len(all_rows) - len(missing_rows)}\n\n"
        f"Affected rows:\n" + "\n".join(samples_missing[:15]) + "\n\n"
        f"Explain concisely (3-5 sentences) why empty beam might be missing for these configurations "
        f"and what the impact is on data reduction if we proceed without them. "
        f"Be specific about SANS data reduction context."
    )

    client = OpenAI(base_url=settings.llm.base_url, api_key=settings.llm.api_key)
    try:
        response = client.chat.completions.create(
            model=settings.llm.model,
            messages=[
                {"role": "system", "content": "You are an expert in SANS (Small-Angle Neutron Scattering) data reduction at SNS/ORNL. Be concise and helpful."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        if response.usage:
            state.llm_tokens_used += response.usage.total_tokens
        state.llm_calls += 1
        text = response.choices[0].message.content
        return text.strip() if text else ""
    except Exception:
        return ""


def _discover_cycle_files(distance: float) -> dict[str, str]:
    """Find the latest cycle *_mp/ folder and return flood/dark/flux paths for a given distance."""
    base = Path(_MP_BASE)
    if not base.is_dir():
        return {}

    mp_dirs = sorted(base.glob("*_mp/"), reverse=True)
    if not mp_dirs:
        return {}

    mp = mp_dirs[0]
    result: dict[str, str] = {}

    # flood: pick by distance
    if distance <= 1.5:
        tag = "1o3m"
    elif distance <= 3.0:
        tag = "2o5m"
    else:
        tag = "4m"
    floods = sorted(mp.glob(f"Sensitivity_*_{tag}_*.nxs"))
    if floods:
        result["sensitivityfilename"] = str(floods[-1])

    # dark current
    darks = sorted(mp.glob("EQSANS_*.nxs.h5"))
    if darks:
        result["darkfilename"] = str(darks[-1])

    # beam flux
    fluxes = sorted(mp.glob("bl6_flux_*.txt"))
    if fluxes:
        result["beamfluxfilename"] = str(fluxes[-1])

    return result


def _llm_suggest_config(
    config_id: str,
    state: SessionState,
    write: Callable,
) -> list[tuple[str, str]]:
    """Ask LLM to suggest config parameters when no preset matches.

    Reads knowledge.md at runtime for domain expertise.
    Returns list of (param, value) pairs that the LLM suggested.
    """
    from eqsanscli.config.settings import AppSettings
    from eqsanscli.services.llm_handler import _load_knowledge, _parse_config_id

    settings = AppSettings.load()
    if not settings.llm.is_configured:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        return []

    meta = _parse_config_id(config_id)
    if not meta:
        return []

    knowledge = _load_knowledge()

    prompt = (
        f"I need reduction parameters for EQSANS configuration: {config_id}\n"
        f"  detector distance = {meta['distance']}m\n"
        f"  wavelength = {meta['wavelength']}A\n"
        f"  chopper frequency = {meta['frequency']}Hz\n\n"
        f"Based on the domain knowledge below, suggest values for these parameters:\n"
        f"  qmin, qmax, numqbins, cuttofmin, cuttofmax, qbintype, wavelengthstep,\n"
        f"  sampleaperturesize, fitinelasticincoh, selectminincoh,\n"
        f"  incohfit_qmin, incohfit_qmax, useerrorweighting\n\n"
        f"Return ONLY /set config commands, one per line. Example:\n"
        f"  /set config {config_id} qmin 0.006\n"
        f"  /set config {config_id} qmax 0.1\n\n"
        f"Do NOT include sensitivityfilename, darkfilename, beamfluxfilename, "
        f"or maskfilename — those are handled separately.\n"
        f"Do NOT include any explanation, just the /set config commands.\n"
    )

    system_msg = (
        "You are an EQSANS SANS instrument scientist at SNS/ORNL. "
        "Suggest reduction parameters based on the domain knowledge provided. "
        "Return ONLY /set config commands."
    )
    if knowledge:
        system_msg += "\n\n" + knowledge

    client = OpenAI(base_url=settings.llm.base_url, api_key=settings.llm.api_key)
    try:
        response = client.chat.completions.create(
            model=settings.llm.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )
        if response.usage:
            state.llm_tokens_used += response.usage.total_tokens
        state.llm_calls += 1
        text = response.choices[0].message.content
        if not text:
            return []

        suggestions: list[tuple[str, str]] = []
        for line in text.strip().split("\n"):
            line = line.strip()
            # parse: /set config <id> <param> <value>
            m = re.match(r"^/set\s+config\s+\S+\s+(\S+)\s+(.+)$", line, re.IGNORECASE)
            if m:
                suggestions.append((m.group(1).lower(), m.group(2).strip()))
        return suggestions
    except Exception as exc:
        logger.warning("LLM config suggestion failed: %s", exc)
        return []


AUTOPILOT_SESSION_FILE = "autopilot_session.json"


def _save_autopilot_session(state: SessionState, output_dir: str) -> str:
    """Save full session state to outputdir for --continue support."""
    path = os.path.join(output_dir, AUTOPILOT_SESSION_FILE)
    state.save(path)
    return path


def _load_autopilot_session(output_dir: str) -> SessionState | None:
    """Load saved autopilot session from outputdir. Returns None if not found."""
    path = os.path.join(output_dir, AUTOPILOT_SESSION_FILE)
    if not os.path.exists(path):
        return None
    try:
        return SessionState.load(path)
    except Exception:
        return None


def run_autopilot_sync(
    ipts: int,
    state: SessionState,
    dispatch_sync: Callable,
    write: Callable,
    cancel_event: threading.Event | None = None,
    prompt_user: Callable | None = None,
    sample_filter: list[str] | None = None,
    exclude_filter: list[str] | None = None,
    thickness: float | None = None,
    bkg_sample: str | None = None,
    config_filter: str | None = None,
    force: bool = False,
    continue_mode: bool = False,
    standard_sample: str | None = None,
    from_step: int = 1,
    fresh: bool = False,
) -> None:
    """Runs entirely in a thread. dispatch_sync wraps async dispatch via loop.run_until_complete."""

    t0 = time.time()

    # Snapshot anything the user set BEFORE autopilot started — these are
    # explicit overrides (maskfilename, sensitivityfilename, custom params, etc.)
    # that the user typed and must win over presets. Re-applied after Step 4.
    #
    # Filter out preset-derived values (a prior /matchruns auto-applies the
    # matching JSON preset, which leaves preset-equal values in
    # state.configurations). Only values that DIFFER from the preset are
    # considered "user-set" for Step 4b's restore + summary.
    from eqsanscli.models.config_id import normalize_config_id
    from eqsanscli.services.config_manager import _load_matching_preset
    user_param_snapshot: dict[str, dict] = {}
    for cfg, params in state.configurations.items():
        if cfg == ALL_CONFIGS_KEY:
            # /set config all values are always user intent — no preset filter
            user_param_snapshot[cfg] = dict(params)
            continue
        preset_for_cfg = _load_matching_preset(cfg)
        user_only = {
            k: v for k, v in params.items()
            if not (k in preset_for_cfg and preset_for_cfg[k] == v)
        }
        if user_only:
            user_param_snapshot[normalize_config_id(cfg)] = user_only

    # Validate --from
    if continue_mode and from_step > 1:
        write("[red]✗ --from cannot be combined with --continue[/red]")
        return
    if from_step >= 2:
        if state.catalog is None or state.catalog.empty:
            write(f"[red]✗ --from {from_step} requires a loaded catalog. Run /load ipts <N> first.[/red]")
            return
        if not state.current_table.rows:
            write(f"[red]✗ --from {from_step} requires a populated working table. Run /matchruns first.[/red]")
            return
        if not ipts:
            ipts = state.ipts

    label_parts = []
    if continue_mode:
        label_parts.append("continue")
    if from_step > 1:
        label_parts.append(f"from step {from_step}")
    if sample_filter:
        label_parts.append(f"samples: {', '.join(sample_filter)}")
    if exclude_filter:
        label_parts.append(f"exclude: {', '.join(exclude_filter)}")
    if config_filter:
        label_parts.append(f"config: {config_filter}")
    if bkg_sample:
        label_parts.append(f"bkg: {bkg_sample}")
    if thickness is not None:
        label_parts.append(f"thickness: {thickness} cm")
    if force:
        label_parts.append("force")
    if label_parts:
        write(f"[bold cyan]━━━ AUTOPILOT MODE ({'; '.join(label_parts)}) ━━━[/bold cyan]\n")
    else:
        write("[bold cyan]━━━ AUTOPILOT MODE ━━━[/bold cyan]\n")

    # === Continue mode: prefer live in-memory state; fall back to saved session ===
    saved_session: SessionState | None = None
    if continue_mode:
        output_dir = os.path.abspath(state.output_directory)

        # A live session is usable if catalog, working table, and configurations are all populated
        live_ok = (
            state.ipts
            and state.catalog is not None
            and not state.catalog.empty
            and state.current_table.rows
            and bool(state.configurations)
        )

        if live_ok:
            # Use the in-memory state directly — no disk load needed
            if ipts == 0:
                ipts = state.ipts
            elif state.ipts and state.ipts != ipts:
                write(f"[red]  ✗ IPTS mismatch: current session is IPTS-{state.ipts}, requested IPTS-{ipts}[/red]")
                write("    Use the same IPTS, or start a fresh autopilot.")
                return
            n_done = sum(1 for r in state.current_table.rows if r.status == "done")
            write(f"  [green]✓[/green] Continuing from current in-memory session")
            write(f"    IPTS-{ipts}, {len(state.configurations)} configs, "
                  f"{len(state.current_table.rows)} rows ({n_done} already 'done')\n")
        else:
            # Fall back to the saved autopilot session file
            saved_session = _load_autopilot_session(output_dir)
            if saved_session is None:
                write(f"[red]  ✗ No usable session state to continue from.[/red]")
                write("    Live state insufficient: need a loaded IPTS, catalog, working table, and configurations.")
                write(f"    No saved file either: {os.path.join(output_dir, AUTOPILOT_SESSION_FILE)}")
                write("    Either run /autopilot first (which saves a session), or set up state manually:")
                write("    /load ipts <N>  →  /matchruns  →  /apply preset auto  →  then /autopilot --continue.")
                return

            if ipts == 0:
                ipts = saved_session.ipts
                if not ipts:
                    write("[red]  ✗ Saved session has no IPTS number[/red]")
                    return
            if saved_session.ipts and saved_session.ipts != ipts:
                write(f"[red]  ✗ IPTS mismatch: saved session is IPTS-{saved_session.ipts}, requested IPTS-{ipts}[/red]")
                write("    Use the same IPTS or start a fresh autopilot.")
                return

            # Restore configurations (with calibrated scale factors) from saved session
            state.ipts = ipts
            state.configurations = saved_session.configurations
            state.calibration = saved_session.calibration
            state.drtsans_version = saved_session.drtsans_version
            if saved_session.catalog is not None and not saved_session.catalog.empty:
                state.catalog = saved_session.catalog
            write(f"  [green]✓[/green] Loaded saved autopilot session from {output_dir}")
            write(f"    IPTS-{ipts}, {len(saved_session.configurations)} configs, "
                  f"{sum(len(t.rows) for t in saved_session.tables.values())} previous rows\n")

    # === Step 1: Load IPTS ===
    # In continue mode, always refresh to discover new runs
    if from_step >= 2:
        write(f"[bold]Step 1/13:[/bold] Load catalog — [dim]Skipped (--from {from_step}, using session catalog)[/dim]")
        catalog = state.catalog
        write(f"  [green]✓[/green] Using existing catalog ({len(catalog)} runs)\n")
    elif continue_mode:
        write(f"[bold]Step 1/13:[/bold] Refreshing IPTS-{ipts} catalog...")
        # Pre-refresh size for the "was N" message
        if saved_session is not None and saved_session.catalog is not None:
            old_count = len(saved_session.catalog)
        elif state.catalog is not None:
            old_count = len(state.catalog)
        else:
            old_count = 0
        # /refresh catalog preserves /reclass overrides; /load ipts would wipe them
        r = dispatch_sync("/refresh catalog")
        if not r.success:
            write(f"[red]  ✗ Failed: {r.message}[/red]")
            return
        catalog = state.catalog
        if catalog is None or catalog.empty:
            write("[red]  ✗ Empty catalog.[/red]")
            return
        write(f"  [green]✓[/green] Refreshed catalog: {len(catalog)} runs (was {old_count})\n")
    else:
        already_loaded = (
            not fresh
            and state.ipts == ipts
            and state.catalog is not None
            and not state.catalog.empty
        )
        if already_loaded:
            write(f"[bold]Step 1/13:[/bold] Loading IPTS-{ipts}... [dim]already loaded[/dim]")
            catalog = state.catalog
            write(f"  [green]✓[/green] Using existing catalog ({len(catalog)} runs)\n")
        else:
            label = f"[bold]Step 1/13:[/bold] Loading IPTS-{ipts}..."
            if fresh:
                label += " [dim](--fresh: forcing reload)[/dim]"
            write(label)
            r = dispatch_sync(f"/load ipts {ipts}")
            if not r.success:
                write(f"[red]  ✗ Failed: {r.message}[/red]")
                return
            catalog = state.catalog
            if catalog is None or catalog.empty:
                write("[red]  ✗ Empty catalog.[/red]")
                return
            write(f"  [green]✓[/green] Loaded {len(catalog)} runs\n")

    # === Step 2: Match runs ===
    n_new_runs = 0
    new_config_ids: list[str] = []

    if from_step >= 3:
        write(f"[bold]Step 2/13:[/bold] Match runs — [dim]Skipped (--from {from_step}, using existing table)[/dim]")
        table = state.current_table
        write(f"  [green]✓[/green] Using existing table ({len(table.rows)} rows, {len(table.configurations)} configs: {', '.join(table.configurations)})\n")
    elif continue_mode:
        write("[bold]Step 2/13:[/bold] Merging new runs into existing table...")
        from eqsanscli.services.matching_service import merge_new_runs

        # Source table: saved session (if loaded from disk) or current in-memory table
        if saved_session is not None:
            saved_table_name = saved_session.active_table
            if saved_table_name in saved_session.tables:
                existing_table = saved_session.tables[saved_table_name]
            else:
                existing_table = list(saved_session.tables.values())[0]
        else:
            existing_table = state.current_table

        existing_table, merge_warnings, n_new_runs, new_config_ids = merge_new_runs(
            existing_table, catalog, ipts=ipts,
        )

        # Put the merged table into state
        state.tables[state.active_table] = existing_table
        existing_table.name = state.active_table
        table = existing_table

        n_done = sum(1 for r in table.rows if r.status == "done")
        write(f"  [green]✓[/green] {n_new_runs} new run(s) found, {n_done} already reduced, "
              f"{len(table.rows)} total rows")
        if new_config_ids:
            write(f"  [yellow]⚠[/yellow] New config(s): {', '.join(new_config_ids)}")
        for w in merge_warnings:
            write(f"  [yellow]⚠[/yellow] {w}")
        write("")

        if n_new_runs == 0:
            write("  [dim]No new scattering runs — will skip to stitching.[/dim]\n")
    else:
        table = state.current_table
        already_matched = (
            not fresh
            and table.rows
            and table.ipts == ipts
        )
        if already_matched:
            write(f"[bold]Step 2/13:[/bold] Matching runs... [dim]already matched[/dim]")
            write(f"  [green]✓[/green] Using existing table ({len(table.rows)} runs, {len(table.configurations)} configs: {', '.join(table.configurations)})\n")
        else:
            label = "[bold]Step 2/13:[/bold] Matching runs..."
            if fresh:
                label += " [dim](--fresh: forcing re-match)[/dim]"
            write(label)
            r = dispatch_sync("/matchruns")
            if not r.success:
                write(f"[red]  ✗ {r.message}[/red]")
                return
            table = state.current_table
            write(f"  [green]✓[/green] {len(table.rows)} runs, {len(table.configurations)} configs: {', '.join(table.configurations)}\n")

    # === Step 2b: Apply customizations ===
    # Order: thickness → bkg → samples → exclude → config
    # Setup (thickness, bkg) runs first on the full table so all rows get
    # correct values. Filters (samples, exclude, config) run after so they
    # can remove rows that already have proper assignments.

    if thickness is not None:
        for row in table.rows:
            row.thickness = thickness
        write(f"[bold]  Thickness:[/bold] set {thickness} cm for all {len(table.rows)} rows\n")

    if bkg_sample:
        write(f"[bold]  Background:[/bold] assigning {bkg_sample} as background...")
        r = dispatch_sync(f"/assign bkg {bkg_sample}")
        if r.success:
            write(f"  [green]✓[/green] {r.message}\n")
        else:
            write(f"  [yellow]⚠[/yellow] {r.message}\n")

    if sample_filter:
        filter_terms = [s.lower() for s in sample_filter]

        std_label = standard_sample or "porsil"

        def _matches_filter(sample_name: str) -> bool:
            if _is_standard_sample(sample_name, standard_sample):
                return True
            return any(term in sample_name.lower() for term in filter_terms)

        rows_before = len(table.rows)
        indices_to_remove = [
            row.index for row in table.rows
            if not _matches_filter(row.sample_name)
        ]
        for idx in sorted(indices_to_remove, reverse=True):
            table.remove_row(idx)

        kept_samples = sorted(set(row.sample_name for row in table.rows))
        removed_count = rows_before - len(table.rows)
        write(f"[bold]  Sample filter:[/bold] keeping {', '.join(sample_filter)} (+ {std_label} if present)")
        write(f"  [green]✓[/green] Removed {removed_count} rows, {len(table.rows)} remaining: {', '.join(kept_samples)}\n")

    if exclude_filter:
        exclude_terms = [s.lower() for s in exclude_filter]

        def _matches_exclude(sample_name: str) -> bool:
            name_lower = sample_name.lower()
            return any(term in name_lower for term in exclude_terms)

        rows_before = len(table.rows)
        indices_to_remove = [
            row.index for row in table.rows
            if _matches_exclude(row.sample_name)
        ]
        for idx in sorted(indices_to_remove, reverse=True):
            table.remove_row(idx)

        removed_count = rows_before - len(table.rows)
        kept_samples = sorted(set(row.sample_name for row in table.rows))
        write(f"[bold]  Exclude filter:[/bold] removed {', '.join(exclude_filter)}")
        write(f"  [green]✓[/green] Removed {removed_count} rows, {len(table.rows)} remaining: {', '.join(kept_samples)}\n")

    if config_filter:
        from eqsanscli.models.config_id import normalize_config_id
        norm_filter = normalize_config_id(config_filter)
        rows_before = len(table.rows)
        indices_to_remove = [
            row.index for row in table.rows
            if normalize_config_id(row.configuration) != norm_filter
        ]
        for idx in sorted(indices_to_remove, reverse=True):
            table.remove_row(idx)
        removed_count = rows_before - len(table.rows)
        write(f"[bold]  Config filter:[/bold] keeping only {config_filter}")
        write(f"  [green]✓[/green] Removed {removed_count} rows, {len(table.rows)} remaining\n")

    # === Step 3: Verify assignments — show the table ===
    if from_step >= 4:
        write(f"[bold]Step 3/13:[/bold] Verify assignments — [dim]Skipped (--from {from_step})[/dim]\n")
    else:
        write("[bold]Step 3/13:[/bold] Verifying assignments...")
        missing_empty = [row for row in table.rows if not row.empty_beam]
        missing_trans = [row for row in table.rows if not row.transmission_run]
        missing_bkg = [row for row in table.rows if not row.background_scatt]

        if missing_empty:
            configs_affected = sorted(set(row.configuration for row in missing_empty))
            write(f"  [yellow]⚠ {len(missing_empty)} rows missing empty beam[/yellow]")
            write(f"    Configurations without empty beam: [bold]{', '.join(configs_affected)}[/bold]")
            for row in missing_empty[:10]:
                write(f"    • {row.sample_name} (run {row.scattering_run}, {row.configuration})")
            if len(missing_empty) > 10:
                write(f"    ... and {len(missing_empty) - 10} more")

            explanation = _llm_explain_missing_empty(missing_empty, table.rows, ipts, state)
            if explanation:
                write(f"\n  [bold cyan]LLM Analysis:[/bold cyan]")
                _write_wrapped(write, explanation, wrap_width=state.wrap_width)

            rows_ok = [row for row in table.rows if row.empty_beam]
            if not rows_ok:
                write(f"\n  [red]✗ No rows have empty beam — cannot proceed[/red]")
                return

            write(f"\n  {len(rows_ok)} rows have valid empty beam and can be reduced.")

            if prompt_user:
                answer = prompt_user(
                    f"  [bold yellow]Proceed without the {len(missing_empty)} rows missing empty beam? (yes/no)[/bold yellow]"
                )
                if answer.lower() not in ("yes", "y"):
                    write("  [red]✗ Autopilot aborted by user[/red]")
                    return

                indices_to_remove = sorted([row.index for row in missing_empty], reverse=True)
                for idx in indices_to_remove:
                    table.remove_row(idx)
                write(f"  [green]✓[/green] Removed {len(missing_empty)} rows — continuing with {len(table.rows)} rows\n")
            else:
                write(f"  [red]✗ Cannot prompt for confirmation — aborting[/red]")
                return

        if missing_trans:
            write(f"  [yellow]⚠ {len(missing_trans)} rows missing transmission[/yellow]")
        if missing_bkg:
            write(f"  [yellow]⚠ {len(missing_bkg)} rows missing background[/yellow]")

        for cfg in table.configurations:
            rows_in_cfg = table.rows_by_config(cfg)
            samples = [row.sample_name for row in rows_in_cfg]
            write(f"  {cfg}: {len(rows_in_cfg)} rows — {', '.join(samples[:8])}{'...' if len(samples) > 8 else ''}")
        write(f"  [green]✓[/green] Assignments verified\n")

    # === Step 4: Apply presets ===
    if from_step >= 5:
        write(f"[bold]Step 4/13:[/bold] Apply presets — [dim]Skipped (--from {from_step}, using existing configurations)[/dim]")
        for cfg in table.configurations:
            scale = state.configurations.get(cfg, {}).get("standardabsolutescale", "?")
            write(f"  [dim]  {cfg}: standardabsolutescale = {scale}[/dim]")
        # Ensure outputdir is set on every config so step 9+ can use it
        for cfg in table.configurations:
            if cfg not in state.configurations:
                state.configurations[cfg] = {}
            state.configurations[cfg].setdefault("outputdir", os.path.abspath(state.output_directory))
        write("")
    elif continue_mode and not new_config_ids:
        write("[bold]Step 4/13:[/bold] Applying presets... [dim]Skipped (using saved configurations)[/dim]")
        for cfg in table.configurations:
            scale = state.configurations.get(cfg, {}).get("standardabsolutescale", "?")
            write(f"  [dim]  {cfg}: standardabsolutescale = {scale}[/dim]")

        # Ensure outputdir is set for all configs from saved state
        for cfg in table.configurations:
            if cfg not in state.configurations:
                state.configurations[cfg] = {}
            state.configurations[cfg].setdefault("outputdir", os.path.abspath(state.output_directory))
        write("")
    else:
        if continue_mode and new_config_ids:
            write(f"[bold]Step 4/13:[/bold] Applying presets for new config(s): {', '.join(new_config_ids)}...")
        else:
            write("[bold]Step 4/13:[/bold] Applying presets...")

        from eqsanscli.services.preset_service import list_presets
        from eqsanscli.services.llm_handler import _parse_config_id
        presets = list_presets()
        preset_names = [p["name"] for p in presets]

        configs_to_apply = new_config_ids if (continue_mode and new_config_ids) else table.configurations

        for cfg in configs_to_apply:
            best, match_type = _find_closest_preset(cfg, preset_names)
            if best:
                r = dispatch_sync(f"/apply preset {best} {cfg}")
                if match_type == "exact":
                    write(f"  [green]✓[/green] {cfg} ← {best}")
                elif match_type == "partial":
                    write(f"  [green]✓[/green] {cfg} ← {best} [dim](partial match)[/dim]")
                elif match_type == "distance":
                    write(f"  [yellow]~[/yellow] {cfg} ← {best} [dim](same distance, closest available)[/dim]")
            else:
                write(f"  [yellow]⚠[/yellow] {cfg} — no preset found, asking LLM...")

                meta = _parse_config_id(cfg)
                distance = meta.get("distance", 4.0) if meta else 4.0

                cycle_files = _discover_cycle_files(distance)
                for param, val in cycle_files.items():
                    dispatch_sync(f"/set config {cfg} {param} {val}")
                if cycle_files:
                    write(f"    [green]✓[/green] Applied cycle files: {', '.join(cycle_files.keys())}")

                ipts_mask = f"/SNS/EQSANS/IPTS-{ipts}/shared/mask_4m.nxs"
                cwd_mask = os.path.join(os.getcwd(), "mask_4m.nxs")
                fallback_mask = "/SNS/EQSANS/shared/script/eqsanstools/mask_4m.nxs"
                for mpath in [ipts_mask, cwd_mask, fallback_mask]:
                    if os.path.exists(mpath):
                        dispatch_sync(f"/set config {cfg} maskfilename {mpath}")
                        write(f"    [green]✓[/green] Mask: {mpath}")
                        break

                suggestions = _llm_suggest_config(cfg, state, write)
                if suggestions:
                    for param, val in suggestions:
                        dispatch_sync(f"/set config {cfg} {param} {val}")
                    param_list = ", ".join(f"{p}={v}" for p, v in suggestions)
                    write(f"    [green]✓[/green] LLM suggested: {param_list}")
                else:
                    write(f"    [dim]LLM returned no suggestions — using defaults[/dim]")
        write("")

    # === Step 4b: Re-apply user-set parameters (snapshot from before autopilot) ===
    # This guarantees that any /set config <id> <param> <val> the user typed
    # BEFORE invoking autopilot wins over preset values — even if config_id
    # normalization or preset-key collisions would otherwise drop them.
    #
    # Special handling: the "__all__" key holds params set via
    # "/set config all <param> <val>" — those apply to EVERY real config.
    if from_step < 5:
        # Track all user-set params per real config so we can print an explicit
        # summary at the end of Step 4b (so the user can verify their intent).
        user_set_by_config: dict[str, dict] = {}

        # Pull __all__ out of the snapshot so we can broadcast it
        all_snapshot_params: dict = {}
        for key in list(user_param_snapshot.keys()):
            if key == ALL_CONFIGS_KEY or key == normalize_config_id(ALL_CONFIGS_KEY):
                all_snapshot_params.update(user_param_snapshot.pop(key))

        # "Real" configs are the ones actually being reduced — NOT orphaned
        # entries in state.configurations from pre-autopilot /set config commands
        # that targeted nonexistent config IDs (e.g. LLM guessed wrong).
        real_configs: list[str] = list(table.configurations)
        real_by_norm: dict[str, str] = {normalize_config_id(c): c for c in real_configs}

        def _resolve_snapshot_target(snap_norm: str) -> tuple[list[str], str]:
            """Map a snapshot config_id (normalized) to one or more real configs.
            Returns (list_of_real_configs, match_kind):
                match_kind = "exact" | "substring" | "ambiguous" | "miss"
            """
            if snap_norm in real_by_norm:
                return [real_by_norm[snap_norm]], "exact"
            # Substring match in either direction (so '4m10a' matches '4m10a60hz'
            # and '4m10a60hz' matches '4m10a' — symmetric)
            subs = [
                real for real_norm, real in real_by_norm.items()
                if snap_norm in real_norm or real_norm in snap_norm
            ]
            if len(subs) == 1:
                return subs, "substring"
            if len(subs) > 1:
                return subs, "ambiguous"
            return [], "miss"

        restored_total = 0
        per_config: list[str] = []
        warnings: list[str] = []

        # 1) Per-config snapshot entries — apply to MATCHING REAL configs, not orphans
        for snap_cfg_norm, params in user_param_snapshot.items():
            targets, kind = _resolve_snapshot_target(snap_cfg_norm)

            if kind == "miss":
                warnings.append(
                    f"  [yellow]⚠[/yellow] '/set config {snap_cfg_norm}' didn't match any real "
                    f"config in the table — your override was DROPPED. Real configs: {', '.join(real_configs)}"
                )
                continue
            if kind == "ambiguous":
                warnings.append(
                    f"  [yellow]⚠[/yellow] '/set config {snap_cfg_norm}' is ambiguous — "
                    f"applying to all matches: {', '.join(targets)}"
                )

            for target_key in targets:
                target = state.configurations.setdefault(target_key, {})
                restored_here: list[str] = []
                for key, val in params.items():
                    if key == "outputdir":
                        continue
                    # Record this as user-set on the real config
                    user_set_by_config.setdefault(target_key, {})[key] = val
                    if target.get(key) != val:
                        target[key] = val
                        restored_here.append(f"{key}={val}")
                if restored_here:
                    restored_total += len(restored_here)
                    note = ""
                    if kind == "substring" and snap_cfg_norm != normalize_config_id(target_key):
                        note = f" [dim](fuzzy match: '{snap_cfg_norm}' → '{target_key}')[/dim]"
                    elif kind == "ambiguous":
                        note = f" [dim](one of {len(targets)} matches for '{snap_cfg_norm}')[/dim]"
                    per_config.append(f"  [green]✓[/green] {target_key}: {', '.join(restored_here)}{note}")

        # 2) "/set config all" defaults — broadcast to every real config
        if all_snapshot_params:
            for cfg in real_configs:
                target = state.configurations.setdefault(cfg, {})
                restored_here = []
                for key, val in all_snapshot_params.items():
                    if key == "outputdir":
                        continue
                    # Mark as user-set (per-config takes precedence if both apply)
                    user_set_by_config.setdefault(cfg, {}).setdefault(key, val)
                    if target.get(key) != val:
                        target[key] = val
                        restored_here.append(f"{key}={val}")
                if restored_here:
                    restored_total += len(restored_here)
                    per_config.append(
                        f"  [green]✓[/green] {cfg} [dim](from 'all')[/dim]: {', '.join(restored_here)}"
                    )

        # Clean up orphan entries in state.configurations that match neither a
        # real config nor __all__. They came from /set config commands that hit
        # nonexistent config IDs — leaving them around is just noise.
        #
        # Cloned configs (`/config clone`, e.g. "4m10a_v2") are NOT orphans even
        # when no row currently references them: the clone may be waiting for a
        # /set <row> cfg assignment, or its rows may have been filtered out of
        # this particular run by --samples/--exclude/--config. Deleting them
        # would silently discard the user's parameter set.
        from eqsanscli.models.config_id import is_derived_config_id
        dropped: list[str] = []
        for orphan in [
            k for k in list(state.configurations.keys())
            if k != ALL_CONFIGS_KEY and k not in real_configs
        ]:
            if is_derived_config_id(orphan):
                continue
            del state.configurations[orphan]
            dropped.append(orphan)

        if dropped:
            warnings.append(
                f"  [dim]Dropped {len(dropped)} config entr(y/ies) not present in the table: "
                f"{', '.join(sorted(dropped))}[/dim]"
            )

        if restored_total or warnings:
            write(f"[bold]Step 4b/13:[/bold] Re-applying user-set params (your settings win over presets)...")
            for line in per_config:
                write(line)
            for w in warnings:
                write(w)
        else:
            write(f"[bold]Step 4b/13:[/bold] Re-apply user-set params — [dim]nothing to restore[/dim]")

        # Explicit summary of ALL user-set parameters per config — so the user
        # can verify their intent landed correctly. This was requested because
        # the previous "key files only" summary hid non-file params (numqbins,
        # qmin, etc.) that the user might have set.
        if user_set_by_config:
            write("  [bold]User-set parameters per config:[/bold]")
            for cfg in sorted(user_set_by_config.keys()):
                params = user_set_by_config[cfg]
                lines = [f"{k} = {v}" for k, v in sorted(params.items())]
                write(f"    [bold cyan]{cfg}:[/bold cyan]")
                for ln in lines:
                    write(f"      {ln}")
        else:
            write("  [dim]No user-set params for any config (presets applied as-is).[/dim]")

        # Compact effective-config (key files) summary — keeps the file-path
        # audit at-a-glance even when files came from presets, not user.
        _KEY_FILE_PARAMS = [
            ("maskfilename",        "mask"),
            ("sensitivityfilename", "sens"),
            ("darkfilename",        "dark"),
            ("defaultmask",         "defmask"),
        ]
        write("  [dim]Effective configuration (key files, basename only):[/dim]")
        for cfg in sorted(c for c in state.configurations.keys() if c != ALL_CONFIGS_KEY):
            params = state.configurations[cfg]
            parts: list[str] = []
            for key, label in _KEY_FILE_PARAMS:
                v = params.get(key)
                if v:
                    parts.append(f"{label}={os.path.basename(str(v))}")
            if parts:
                write(f"    [dim]{cfg}:[/dim] {', '.join(parts)}")
            else:
                write(f"    [dim]{cfg}:[/dim] [yellow](no mask/sens/dark assigned)[/yellow]")
        write("")

    # === Step 5: Set output directory ===
    output_dir = os.path.abspath(state.output_directory)
    if from_step >= 6:
        write(f"[bold]Step 5/13:[/bold] Set output directory — [dim]Skipped (--from {from_step})[/dim]")
        write(f"  [green]✓[/green] {output_dir}\n")
    else:
        write("[bold]Step 5/13:[/bold] Setting output directory...")
        dispatch_sync(f"/set outputdir {output_dir}")
        if state.output_directory != "./output/":
            write(f"  [green]✓[/green] {output_dir} [dim](user-set)[/dim]\n")
        else:
            write(f"  [green]✓[/green] {output_dir}\n")

    # === Step 6: Reduce standard sample (scale=1.0) ===
    from eqsanscli.services.reduction_service import reduce_row

    std_label = standard_sample or "porsil"
    porsil_rows = [row for row in table.rows if _is_standard_sample(row.sample_name, standard_sample)]
    has_porsil = len(porsil_rows) > 0

    calibrated_configs: dict[str, float] = {}
    reference_config = None
    max_workers = state.max_workers

    # In continue mode, skip standard/calibrate — reuse saved scale factors
    if continue_mode:
        write(f"[bold]Step 6/13:[/bold] Reduce {std_label} — [dim]Skipped (using saved calibration)[/dim]")
        write("[bold]Step 7/13:[/bold] Calibrate — [dim]Skipped[/dim]")
        write("[bold]Step 8/13:[/bold] Apply scale factors — [dim]Skipped[/dim]")
        write("  Saved scale factors:")
        for cfg in sorted(c for c in state.configurations.keys() if c != ALL_CONFIGS_KEY):
            scale = state.configurations[cfg].get("standardabsolutescale", "?")
            write(f"    {cfg}: standardabsolutescale = {scale}")
            if reference_config is None and scale not in ("?", "1.0", 1.0):
                reference_config = cfg
        write("")
    elif has_porsil:
        if force:
            porsil_todo = porsil_rows
        else:
            porsil_todo = [row for row in porsil_rows if row.status != "done"]
        porsil_already_done = len(porsil_rows) - len(porsil_todo)

        if not porsil_todo:
            write(f"[bold]Step 6/13:[/bold] Reducing {std_label}... [dim]already done ({porsil_already_done} runs)[/dim]")
            write(f"  [green]✓[/green] All {porsil_already_done} {std_label} runs already reduced\n")
        else:
            parallel_label = f" [{max_workers} parallel]" if max_workers > 1 else ""
            if porsil_already_done:
                write(f"[bold]Step 6/13:[/bold] Reducing {len(porsil_todo)} remaining {std_label} runs (scale=1.0)...{parallel_label} ({porsil_already_done} already done)")
            else:
                write(f"[bold]Step 6/13:[/bold] Reducing {len(porsil_rows)} {std_label} runs (scale=1.0)...{parallel_label}")
            for cfg in table.configurations:
                dispatch_sync(f"/set config {cfg} standardabsolutescale 1.0")

            _reduce_phase(
                rows=porsil_todo,
                state=state,
                output_dir=output_dir,
                write=write,
                cancel_event=cancel_event,
                max_workers=max_workers,
            )

            if cancel_event and cancel_event.is_set():
                return

            done_porsil = sum(1 for row in porsil_rows if row.status == "done")
            write(f"  [green]✓[/green] {done_porsil}/{len(porsil_rows)} {std_label} completed\n")

        # === Step 7: Calibrate ===
        write("[bold]Step 7/13:[/bold] Calibrating absolute scale...")
        for row in porsil_rows:
            if row.status != "done":
                continue
            output_path = row.output_file or os.path.join(output_dir, f"{row.output_stem}_Iq.dat")
            if not os.path.exists(output_path):
                write(f"  [yellow]⚠[/yellow] {row.configuration}: output file not found")
                continue
            r = dispatch_sync(f"/calibrate {output_path}")
            if r.success and "Scale factor:" in r.message:
                try:
                    scale_line = [l for l in r.message.split("\n") if "Scale factor:" in l][0]
                    scale_val = float(scale_line.split(":")[1].strip().split("[")[0].strip())
                    calibrated_configs[row.configuration] = scale_val
                    write(f"  [green]✓[/green] {row.configuration}: scale = {scale_val:.7f}")
                except (IndexError, ValueError):
                    write(f"  [yellow]⚠[/yellow] {row.configuration}: could not parse scale")
            else:
                write(f"  [yellow]⚠[/yellow] {row.configuration}: calibration failed")
        write("")

        # === Step 8: Apply scales ===
        write("[bold]Step 8/13:[/bold] Applying absolute scale factors...")
        for cfg in table.configurations:
            if cfg in calibrated_configs:
                scale = calibrated_configs[cfg]
                r = dispatch_sync(f"/set config {cfg} standardabsolutescale {scale}")
                if not r.success:
                    write(f"  [red]✗[/red] {cfg}: failed to apply scale {scale:.7f} — {r.message}")
                else:
                    write(f"  [green]✓[/green] {cfg}: {scale:.7f}")
                    if reference_config is None:
                        reference_config = cfg
            else:
                r = dispatch_sync(f"/set config {cfg} standardabsolutescale 1.0")
                if not r.success:
                    write(f"  [red]✗[/red] {cfg}: failed to set scale 1.0 — {r.message}")
                else:
                    write(f"  [dim]  {cfg}: 1.0 (no {std_label} calibration)[/dim]")
        write("")
    else:
        write(f"[bold]Step 6/13:[/bold] Reduce {std_label} standard — [dim]Skipped[/dim]")
        write(f"    No {std_label} standard runs found in this IPTS.")
        write(f"    Standard sample is used as an absolute intensity calibration standard.")
        write(f"[bold]Step 7/13:[/bold] Calibrate absolute scale — [dim]Skipped (no {std_label})[/dim]")
        write(f"[bold]Step 8/13:[/bold] Apply scale factors — [dim]Skipped (no {std_label})[/dim]")
        # Report the standardabsolutescale that will actually be used (from preset)
        write("    Reduction will use standardAbsoluteScale from applied preset(s):")
        for cfg in table.configurations:
            scale = state.configurations.get(cfg, {}).get("standardabsolutescale", "not set")
            write(f"      {cfg}: standardabsolutescale = {scale}")
        write(f"    [dim]To calibrate, add a {std_label} sample and re-run, or use --standard <name> to specify a different standard.[/dim]\n")

    # === Step 9: Reduce all non-standard samples ===
    non_porsil = [row for row in table.rows if not _is_standard_sample(row.sample_name, standard_sample)]

    # In continue mode (or when not forced), skip already-done rows
    if continue_mode or not force:
        rows_to_reduce = [row for row in non_porsil if row.status != "done"]
    else:
        rows_to_reduce = non_porsil

    n_already_done = len(non_porsil) - len(rows_to_reduce)
    total_np = len(rows_to_reduce)
    parallel_label_s9 = f" [{max_workers} parallel]" if max_workers > 1 else ""

    if total_np == 0 and continue_mode:
        write(f"[bold]Step 9/13:[/bold] Reducing samples... [dim]all {n_already_done} already done[/dim]\n")
    else:
        if n_already_done > 0:
            write(f"[bold]Step 9/13:[/bold] Reducing {total_np} sample runs ({n_already_done} already done)...{parallel_label_s9}")
        else:
            write(f"[bold]Step 9/13:[/bold] Reducing {total_np} sample runs...{parallel_label_s9}")

    n_ok, n_fail = _reduce_phase(
        rows=rows_to_reduce,
        state=state,
        output_dir=output_dir,
        write=write,
        cancel_event=cancel_event,
        max_workers=max_workers,
    )

    if cancel_event and cancel_event.is_set():
        return

    write(f"  [green]✓[/green] {n_ok} succeeded, [red]{n_fail} failed[/red]\n")

    # === Step 10-12: Smart Stitch ===
    configs = table.configurations
    has_frame_skipping = any(getattr(row, "frequency", 60) == 30 for row in table.rows)
    can_stitch = len(configs) > 1 or has_frame_skipping
    if can_stitch:
        if has_frame_skipping and len(configs) == 1:
            write("[bold]Step 10/13:[/bold] Building stitch table (30Hz frame-skipping mode)...")
            write("    Frame-skipping data produces frame_0 (low-Q) and frame_1 (high-Q) per run.")
        else:
            write("[bold]Step 10/13:[/bold] Building stitch table with smart overlap analysis...")

        # Use smart stitching service
        from eqsanscli.services.smart_stitch import build_smart_stitch_table, SmartStitchService
        from eqsanscli.services.merge_service import build_stitch_table as _original_build_stitch_table

        # First build original stitch table to get sample_files
        groups = _original_build_stitch_table(state.current_table, output_dir)
        stitchable = [g for g in groups if g.status != "1 config"]

        if not stitchable:
            write("  [yellow]⚠[/yellow] No stitchable groups found\n")
        else:
            write(f"  [green]✓[/green] Found {len(stitchable)} stitchable groups")

            # Get LLM handler from state if available
            llm_handler = getattr(state, "llm_handler", None)

            # Build smart stitch table for each sample
            # Look up (distance, wavelength) from working table rows by config ID
            from eqsanscli.models.config_id import config_ids_match, parse_config_id

            # Stitch groups are labelled by the PHYSICS config (see
            # WorkingTableRow.output_stem), so key the metadata the same way.
            _config_meta: dict[str, tuple[float, float]] = {}
            for row in state.current_table.rows:
                _config_meta[row.physical_configuration] = (row.detector_distance, row.wavelength)

            sample_files: dict[str, list[tuple[str, str, float, float]]] = {}
            for g in stitchable:
                entries = []
                for fpath, cfg in zip(g.files, g.configs):
                    dist, wl = _config_meta.get(cfg, (0.0, 0.0))
                    if dist == 0.0:
                        dist, wl, _freq = parse_config_id(cfg)
                    entries.append((fpath, cfg, dist, wl))
                sample_files[g.sample_name] = entries

            smart_groups = build_smart_stitch_table(
                sample_files, output_dir, llm_handler=llm_handler, use_llm=True
            )

            # Update stitch_groups with smart selection
            state.stitch_groups = []
            from eqsanscli.services.merge_service import StitchGroup

            for sg in smart_groups:
                if sg["status"] == "1 config":
                    continue

                # Create StitchGroup with selected configs only
                group = StitchGroup(
                    sample_name=sg["sample_name"],
                    files=sg["files"],
                    configs=sg["configs"],
                    overlaps=[round(v, 6) for pair in sg["overlaps"] for v in pair],
                    target_profile_index=0,
                    output_file=sg.get("output_file", ""),
                    status="ready",
                )

                # Set target profile index if reference_config available
                if reference_config and reference_config in group.configs:
                    group.target_profile_index = group.configs.index(reference_config)
                else:
                    # Default priority: 4m10a > 8m* > 4m2.5a > 2.5m2.5a > first
                    from eqsanscli.services.merge_service import _default_target_index
                    group.target_profile_index = _default_target_index(group.configs)

                state.stitch_groups.append(group)

            # Display smart analysis results
            write("\n[bold]Step 11/13:[/bold] Smart overlap analysis...")
            for sg in smart_groups:
                if sg["status"] != "ready":
                    continue

                sample = sg["sample_name"]
                all_cfgs = sg.get("all_configs", sg["configs"])
                selected = sg["configs"]
                removed = sg.get("removed_configs", [])

                if removed:
                    write(f"  [bold]{sample}:[/bold]")
                    write(f"    Available: {', '.join(all_cfgs)}")
                    write(f"    Selected: {', '.join(selected)}")
                    write(f"    [yellow]Removed:[/yellow] {', '.join(r['config'] for r in removed)}")
                    for r in removed:
                        write(f"      • {r['config']}: {r['reason']}")
                else:
                    write(f"  [bold]{sample}:[/bold] {', '.join(selected)} (no redundancy)")

                # Show quality metrics
                quality = sg.get("quality_metrics", [])
                for q in quality:
                    status_icon = "[green]✓[/green]" if q.get("is_good") else "[yellow]~[/yellow]"
                    write(f"    {status_icon} Overlap Q=[{q['start_q']:.4f}, {q['end_q']:.4f}]: "
                          f"{q['n_points']} pts, score={q['score']:.1f}")

                # Show LLM advice if present
                llm_advice = sg.get("llm_advice", "")
                if llm_advice and llm_advice != "LLM advisory failed":
                    confidence = sg.get("confidence", 0)
                    write(f"    [dim]LLM confidence: {confidence:.0%}[/dim]")
                    _write_wrapped(write, llm_advice, wrap_width=state.wrap_width)

            write("")

            write("[bold]Step 12/13:[/bold] Smart stitching...")
            if reference_config:
                write(f"  Reference config: {reference_config}")

            from eqsanscli.services.smart_stitch import StitchPlan, StitchConfig, centered_overlap
            from eqsanscli.services.plotting_service import load_iq_native
            import numpy as np

            stitch_service = SmartStitchService(llm_handler)
            n_stitched = 0
            n_failed = 0

            _N_POINTS_SEQUENCE = [6, 8, 10, 14, 20]

            for sg in smart_groups:
                if sg["status"] != "ready":
                    continue

                sample = sg["sample_name"]
                files = sg["files"]
                configs = sg["configs"]
                target_id = sg.get("target_config", configs[0])
                target_idx = configs.index(target_id) if target_id in configs else 0
                current_overlaps = list(sg["overlaps"])
                succeeded = False

                for attempt, n_pts in enumerate(_N_POINTS_SEQUENCE):
                    if attempt > 0:
                        # Recompute overlaps with wider window
                        try:
                            new_overlaps = []
                            for fi in range(len(files) - 1):
                                qa = load_iq_native(files[fi]).mod_q
                                qb = load_iq_native(files[fi + 1]).mod_q
                                qa = qa[np.isfinite(load_iq_native(files[fi]).intensity)]
                                qb = qb[np.isfinite(load_iq_native(files[fi + 1]).intensity)]
                                s, e = centered_overlap(qa, qb, n_pts)
                                new_overlaps.append((round(s, 6), round(e, 6)))
                            current_overlaps = new_overlaps
                            write(f"    [yellow]↺[/yellow] retry n={n_pts}: {current_overlaps}")
                        except Exception as re:
                            write(f"    [red]✗[/red] overlap recompute failed: {re}")
                            break

                    try:
                        selected_configs = [
                            StitchConfig(config_id=c, file_path=f, distance=4.0, q_range=(0.0, 0.0), n_points=0)
                            for c, f in zip(configs, files)
                        ]
                        plan = StitchPlan(
                            sample_name=sample,
                            all_configs=[],
                            selected_configs=selected_configs,
                            overlaps=current_overlaps,
                            target_config=selected_configs[target_idx],
                            quality_metrics=[],
                            removed_configs=[],
                        )
                        output_file = stitch_service.execute_plan(plan)
                        n_stitched += 1
                        label = f"n={n_pts}" if attempt > 0 else "n=6"
                        write(f"  [green]✓[/green] {sample} → {os.path.basename(output_file)} [{label}]")
                        succeeded = True
                        break

                    except Exception as e:
                        if attempt == 0:
                            write(f"  [yellow]~[/yellow] {sample}: failed (n=6), retrying with wider overlap...")
                        elif attempt < len(_N_POINTS_SEQUENCE) - 1:
                            write(f"    still failing at n={n_pts}: {e}")

                if not succeeded:
                    n_failed += 1
                    write(f"  [red]✗[/red] {sample}: failed at all overlap widths {_N_POINTS_SEQUENCE}")

            write(f"  [green]✓[/green] {n_stitched} stitched, [red]{n_failed} failed[/red]\n")
    else:
        write("[bold]Step 10/13:[/bold] Build stitch table — [dim]Skipped[/dim]")
        write("[bold]Step 11/13:[/bold] Smart overlap analysis — [dim]Skipped[/dim]")
        write("[bold]Step 12/13:[/bold] Stitch profiles — [dim]Skipped[/dim]")
        write("    Only 1 configuration (60Hz) — stitching requires 2+ configs or 30Hz")
        write("    frame-skipping mode to merge overlapping Q-ranges.\n")

    # === Step 13: Plot ===
    write("[bold]Step 13/13:[/bold] Plotting results...")
    merged = sorted(glob.glob(os.path.join(output_dir, "merged_*_Iq.txt")))
    merged += sorted(glob.glob(os.path.join(output_dir, "merged_*_Iq.dat")))
    if merged:
        r = dispatch_sync(f"/plot {' '.join(merged)}")
        write(f"  [green]✓[/green] Plotted {len(merged)} merged files")
        if r.message:
            write(f"  {r.message}")
    else:
        iq_files = sorted(glob.glob(os.path.join(output_dir, "*_Iq.dat")))
        if iq_files:
            r = dispatch_sync(f"/plot {' '.join(iq_files[:20])}")
            write(f"  [green]✓[/green] Plotted {len(iq_files)} files")
            if r.message:
                write(f"  {r.message}")
        else:
            write("  [yellow]⚠[/yellow] No output files found to plot")

    # === Summary ===
    total = time.time() - t0
    total_reduced = sum(1 for row in table.rows if row.status == "done")
    total_failed = sum(1 for row in table.rows if row.status == "error")
    write(
        f"\n[bold cyan]━━━ AUTOPILOT COMPLETE ━━━[/bold cyan]\n"
        f"  IPTS-{ipts} | {total_reduced} reduced | {total_failed} failed | {len(configs)} configs\n"
        f"  Output: {output_dir}\n"
        f"  Total time: {_fmt(total)}"
    )

    # Save autopilot session to outputdir for --continue support
    try:
        session_path = _save_autopilot_session(state, output_dir)
        write(f"  [dim]Session saved: {session_path}[/dim]")
    except Exception as e:
        write(f"  [yellow]⚠ Failed to save autopilot session: {e}[/yellow]")

    # Confirm data reduction status
    if total_reduced > 0:
        from eqsanscli.commands.export import run_confirm_data
        comment = f"eqsanscli autopilot: {total_reduced} reduced, {total_failed} failed"
        ok, msg = run_confirm_data(ipts, comment=comment)
        if ok:
            write(f"  [green]✓[/green] {msg}")
        else:
            write(f"  [yellow]⚠[/yellow] {msg}")


def _find_closest_preset(config_id: str, preset_names: list[str]) -> tuple[str | None, str]:
    """Find the preset for a config, resolving clone names to their physics ID.

    "4m10a_v2" must match the 4m10a preset exactly rather than falling through
    to find_closest_preset's loose "same distance" tier.
    """
    from eqsanscli.models.config_id import base_config_id
    from eqsanscli.services.preset_service import find_closest_preset
    return find_closest_preset(base_config_id(config_id) or config_id, preset_names)
