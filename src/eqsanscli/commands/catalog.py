from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.catalog_service import CatalogService
from eqsanscli.services.matching_service import (
    RUN_CLASS_SHORT,
    add_run_class_column,
    resolve_run_class,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

_catalog_service = CatalogService()


def _format_counts(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _build_catalog_rows(df) -> list[dict]:
    rows = []
    for _, row in df.iterrows():
        run_class = str(row.get("run_class", ""))
        class_label = RUN_CLASS_SHORT.get(run_class, run_class[:6])
        rows.append({
            "Run #": str(int(row["run_number"])),
            "Title": str(row["title"])[:40],
            "Class": class_label,
            "Dist (m)": f"{row['detector_distance']:.1f}",
            "λ (Å)": f"{row['wavelength']:.1f}",
            "Count": _format_counts(int(row["total_counts"])),
            "Time(s)": str(int(row["duration"])),
        })
    return rows


async def handle_show(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /show <target>\n"
            "  /show catalog              — Display loaded catalog\n"
            "  /show table                — Show working table (--rows 50-100, --name 0.25phr)\n"
            "  /show config 4m10a         — Show config parameters\n"
            "  /show outputdir            — Show output directory\n"
            "  /show ipts                 — Show current IPTS\n"
            "  /show presets              — List preset configs\n"
            "  /show preset <name>        — Show preset details",
        )

    first = args[0].lower()

    if first == "table":
        return await handle_show_table(args[1:], state)
    if first == "catalog":
        return await handle_show_catalog(args[1:], state)
    if first == "outputdir":
        return CommandResult(success=True, message=f"Output directory: {os.path.abspath(state.output_directory)}")
    if first == "ipts":
        return await handle_show_ipts(args[1:], state)

    return CommandResult(
        success=False,
        message=f"Unknown /show target: {first}\n"
        "  /show table | catalog | config | outputdir | ipts | presets | preset",
    )


def _ipts_from_cwd() -> int | None:
    """The IPTS number of the current working directory, if it is under
    /SNS/EQSANS/IPTS-NNNNN/... — matches with or without a trailing slash."""
    m = re.search(r"/IPTS-(\d+)(?:/|$)", os.path.abspath(os.getcwd()))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


async def handle_load_ipts(args: list[str], state: SessionState) -> CommandResult:
    inferred_note = ""
    if not args:
        # No number given: infer from the current IPTS folder, e.g. running from
        # /SNS/EQSANS/IPTS-39659/shared/ loads 39659.
        inferred = _ipts_from_cwd()
        if inferred is None:
            return CommandResult(
                success=False,
                message="Usage: /load ipts <number>\n"
                "  /load ipts        — use the IPTS of the current folder "
                "(only works under /SNS/EQSANS/IPTS-NNNNN/...)",
            )
        ipts = inferred
        inferred_note = f" [dim](inferred from current folder)[/dim]"
    else:
        try:
            ipts = int(args[0])
        except ValueError:
            return CommandResult(success=False, message=f"Invalid IPTS number: {args[0]}")

    try:
        df = _catalog_service.fetch(ipts)
    except ImportError as e:
        return CommandResult(success=False, message=str(e))
    except Exception as e:
        return CommandResult(success=False, message=f"ONCat error: {e}")

    if df.empty:
        return CommandResult(success=True, message=f"No runs found for IPTS-{ipts}.")

    add_run_class_column(df)
    state.ipts = ipts
    state.catalog = df

    rows = _build_catalog_rows(df)
    return CommandResult(
        success=True,
        message=f"Loaded IPTS-{ipts} catalog ({len(df)} runs){inferred_note}",
        data={"type": "catalog", "rows": rows, "ipts": ipts},
    )


async def handle_refresh_catalog(args: list[str], state: SessionState) -> CommandResult:
    """/refresh catalog — re-fetch catalog from ONCat, preserving any /reclass overrides.

    Use this mid-experiment when new runs have been collected. Existing run_class
    values (including manual overrides via /reclass) are preserved; only newly
    discovered runs get fresh classification from their titles.

    Follow with /matchruns --update to extend the working table without disrupting
    already-reduced rows.
    """
    if not state.ipts:
        return CommandResult(
            success=False,
            message="No IPTS loaded. Use /load ipts <number> first.",
        )

    try:
        fresh_df = _catalog_service.fetch(state.ipts)
    except ImportError as e:
        return CommandResult(success=False, message=str(e))
    except Exception as e:
        return CommandResult(success=False, message=f"ONCat error: {e}")

    if fresh_df.empty:
        return CommandResult(success=True, message=f"No runs returned from ONCat for IPTS-{state.ipts}.")

    # Build {run_number: run_class} from the existing catalog so manual /reclass overrides survive
    old_class: dict[int, str] = {}
    if state.catalog is not None and not state.catalog.empty and "run_class" in state.catalog.columns:
        for _, row in state.catalog.iterrows():
            try:
                rn = int(row["run_number"])
            except (ValueError, TypeError):
                continue
            cls = str(row.get("run_class", "") or "")
            if cls:
                old_class[rn] = cls

    old_runs = set(old_class.keys())
    new_runs = {int(r) for r in fresh_df["run_number"]} - old_runs

    # Seed run_class column from the old catalog; add_run_class_column fills in only blanks
    fresh_df["run_class"] = fresh_df["run_number"].map(lambda rn: old_class.get(int(rn), ""))
    add_run_class_column(fresh_df)

    state.catalog = fresh_df

    rows = _build_catalog_rows(fresh_df)
    summary = (
        f"Refreshed IPTS-{state.ipts} catalog from ONCat.\n"
        f"  Total runs: {len(fresh_df)}  (previously: {len(old_runs)})\n"
        f"  New runs:   {len(new_runs)}\n"
        f"  Preserved {len(old_runs)} existing run_class values"
    )
    if new_runs:
        new_run_list = ", ".join(str(r) for r in sorted(new_runs)[:20])
        if len(new_runs) > 20:
            new_run_list += f", ... (+{len(new_runs) - 20} more)"
        summary += f"\n  New run numbers: {new_run_list}"
        summary += "\n\nNext: /matchruns --update to add new rows to the working table without disrupting reduced ones."
    else:
        summary += "\n\nNo new runs to add."

    return CommandResult(
        success=True,
        message=summary,
        data={"type": "catalog", "rows": rows, "ipts": state.ipts},
    )


async def handle_show_catalog(args: list[str], state: SessionState) -> CommandResult:
    catalog = state.catalog
    if catalog is None or catalog.empty:
        return CommandResult(
            success=True,
            message="No catalog loaded. Use /load ipts <number> first.",
        )

    rows = _build_catalog_rows(catalog)
    return CommandResult(
        success=True,
        message=f"IPTS-{state.ipts} Catalog ({len(catalog)} runs)",
        data={"type": "catalog", "rows": rows, "ipts": state.ipts},
    )


async def handle_show_ipts(args: list[str], state: SessionState) -> CommandResult:
    if state.ipts:
        msg = f"Current IPTS: {state.ipts}"
    else:
        msg = "No IPTS loaded. Use /load ipts <number>"
    return CommandResult(success=True, message=msg)


def _build_title_lookup(state: SessionState) -> dict[str, str]:
    """Build a run_number (str) → title lookup from the catalog in state."""
    lookup: dict[str, str] = {}
    catalog = state.catalog
    if catalog is not None and not catalog.empty:
        for _, row in catalog.iterrows():
            lookup[str(int(row["run_number"]))] = str(row.get("title", ""))
    return lookup


def _run_cell(run_str: str, lookup: dict[str, str]) -> str:
    """Format a run number cell with title on second line.

    Handles:
    - "" (empty) → "—"
    - "172760" → "172760\\n[dim]T-porsil 4m 10A 20C[/dim]"
    - "172760, 172761" → "172760, 172761\\n[dim]multi-run[/dim]"
    """
    if not run_str:
        return "—"
    # For comma-separated multi-run, show "multi-run" as title
    if "," in run_str:
        return f"{run_str}\n[dim]multi-run[/dim]"
    # Single run — look up title
    title = lookup.get(run_str.strip(), "")
    if title:
        return f"{run_str}\n[dim]{title}[/dim]"
    return run_str


def build_working_table_display(state: SessionState) -> list[dict]:
    """Build display rows for the working table with two-line run cells.

    Column order: Idx, Sample, Config, Scatt, Trans, Bkg, BkgTr, Empty, Status
    Each run number column shows the title on a second line (dimmed).
    """
    table = state.current_table
    lookup = _build_title_lookup(state)

    rows = []
    for row in table.rows:
        rows.append(
            {
                "Idx": str(row.index),
                "Sample": row.sample_name,
                "Config": row.configuration,
                "Scatt": _run_cell(row.scattering_run, lookup),
                "Trans": _run_cell(row.transmission_run, lookup),
                "Thick": str(row.thickness),
                "Bkg": _run_cell(row.background_scatt, lookup),
                "BkgTr": _run_cell(row.background_trans, lookup),
                "Empty": _run_cell(row.empty_beam, lookup),
                "Status": row.status,
            }
        )
    return rows


async def handle_list_ipts(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /list ipts <search>\n"
            "  /list ipts *           — List all EQSANS experiments\n"
            "  /list ipts polymer     — Search by title or team member name\n"
            "  /list ipts Stanley     — Find experiments with team member\n"
            "  /list ipts refresh     — Re-fetch from ONCat (clears cache)",
        )

    refresh = args[0].lower() == "refresh"
    search = "" if refresh else " ".join(args)

    try:
        from eqsanscli.integrations.oncat import list_experiments
        experiments, from_cache = list_experiments(search, refresh=refresh)
    except ImportError as e:
        return CommandResult(success=False, message=str(e))
    except Exception as e:
        return CommandResult(success=False, message=f"ONCat error: {e}")

    if refresh and not search:
        header = f"EQSANS experiments ({len(experiments)} found) [dim][refreshed][/dim]:"
    elif from_cache:
        header = f"EQSANS experiments ({len(experiments)} found) [dim][from cache — /list ipts refresh to update][/dim]:"
    else:
        header = f"EQSANS experiments ({len(experiments)} found) [dim][cached for this session][/dim]:"

    if not experiments:
        return CommandResult(success=True, message=f"No EQSANS experiments matching '{search}'")

    lines = [header, ""]
    for exp in experiments:
        ipts = exp["ipts"]
        title = exp["title"][:60] if exp["title"] else "(no title)"
        runs = exp["runs"]
        dates = exp["dates"]
        members_str = ", ".join(exp["members"][:3])
        if len(exp["members"]) > 3:
            members_str += f" (+{len(exp['members']) - 3})"

        lines.append(f"  [bold cyan]IPTS-{ipts}[/bold cyan]  {title}")
        detail_parts = []
        if runs:
            detail_parts.append(f"{runs} runs")
        if dates:
            detail_parts.append(dates)
        if members_str:
            detail_parts.append(members_str)
        if detail_parts:
            lines.append(f"    [dim]{' · '.join(detail_parts)}[/dim]")

    return CommandResult(success=True, message="\n".join(lines))


def _parse_run_numbers(spec: str) -> list[int]:
    """Parse run number spec: '12345', '12345-12350', '12345,12346,12350'."""
    runs: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                runs.extend(range(int(start_s), int(end_s) + 1))
            except ValueError:
                pass
        else:
            try:
                runs.append(int(part))
            except ValueError:
                pass
    return runs


def _title_prefix_class(title: str) -> str:
    """Determine scattering or transmission from S-/T- title prefix."""
    t = title.strip().lower()
    if t.startswith("t-") or t.startswith("t "):
        return "transmission"
    return "scattering"


def _match_catalog_title(pattern: str, title: str) -> bool:
    """Match a pattern against a catalog title (case-insensitive).

    Strips the S-/T- prefix from the title before matching.
    Supports * wildcard (glob-style) or exact match.
    """
    import fnmatch
    p = pattern.lower().strip()
    # Strip S-/T- prefix from title for matching
    t = re.sub(r"^[sStT][-\s]+", "", title).strip().lower()
    if "*" in p or "?" in p:
        return fnmatch.fnmatch(t, p)
    return p in t


async def handle_reclass(args: list[str], state: SessionState) -> CommandResult:
    """/reclass <runs> <class> — override run classification in the catalog.

    Examples:
        /reclass 172804 scatt              — single run → scattering
        /reclass 172804-172810 scatt       — range → scattering
        /reclass 172804,172806 trans       — specific runs → transmission
        /reclass 172804-172810 sample      — treat as normal sample (S-→scatt, T-→trans)
        /reclass 172804 i                  — ignore this run (excluded from matching)
        /reclass 172804 n                  — same: 'n' (not used) is an alias of 'i'
        /reclass --sample BkgG sample      — all BkgG runs: S-BkgG→scatt, T-BkgG→trans
        /reclass --sample emptyticell bkg  — all emptyticell runs → background

    Valid classes: scatt, trans, bkg, bkgtrans, empty, emptyscatt, sample, ignore (i, n)
    "sample" respects S-/T- prefix: S-BkgG → scattering, T-BkgG → transmission.
    "ignore" (aliases: i, n) excludes runs from /matchruns entirely (label: N).
    """
    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /reclass <runs> <class>  |  /reclass --sample <name> <class>\n"
            "  <runs>   = run number, range (12345-12350), or comma-separated\n"
            "  <name>   = sample name (case-insensitive, matches title after S-/T- prefix)\n"
            "  <class>  = scatt, trans, bkg, bkgtrans, empty, emptyscatt, sample, ignore (i, n)\n\n"
            "  'sample' respects S-/T- prefix (S-BkgG → scatt, T-BkgG → trans)\n"
            "  'ignore' (aliases: i, n — 'not used') excludes runs from /matchruns entirely\n\n"
            "Examples:\n"
            "  /reclass 172804 scatt\n"
            "  /reclass 172804-172810 sample\n"
            "  /reclass 172804 i        (or: /reclass 172804 n)\n"
            "  /reclass --sample BkgG sample\n"
            "  /reclass --sample emptyticell bkg",
        )

    if state.catalog_data is None:
        return CommandResult(
            success=False,
            message="No catalog loaded. Use /load ipts <number> first.",
        )

    # Parse --sample mode vs run-number mode
    if args[0].lower() == "--sample":
        if len(args) < 3:
            return CommandResult(
                success=False,
                message="Usage: /reclass --sample <name> <class>",
            )
        sample_pattern = args[1]
        class_name = args[2]
        use_sample_filter = True
    else:
        sample_pattern = None
        run_spec = args[0]
        class_name = args[1]
        use_sample_filter = False

    is_sample_mode = class_name.lower().strip() == "sample"

    if not is_sample_mode:
        new_class = resolve_run_class(class_name)
        if new_class is None:
            valid = "scatt, trans, bkg, bkgtrans, empty, emptyscatt, sample, ignore (i, n)"
            return CommandResult(
                success=False,
                message=f"Unknown class: '{class_name}'. Valid classes: {valid}",
            )
    else:
        new_class = None  # determined per-run from title prefix

    if not use_sample_filter:
        requested_runs = set(_parse_run_numbers(run_spec))
        if not requested_runs:
            return CommandResult(success=False, message=f"Could not parse run numbers: {run_spec}")

    updated = 0
    changed_runs: list[str] = []
    for record in state.catalog_data:
        try:
            rn = int(record.get("run_number", 0))
        except (ValueError, TypeError):
            continue

        title = str(record.get("title", ""))

        if use_sample_filter:
            if not _match_catalog_title(sample_pattern, title):
                continue
        else:
            if rn not in requested_runs:
                continue

        old_class = record.get("run_class", "")
        if is_sample_mode:
            resolved = _title_prefix_class(title)
        else:
            resolved = new_class
        record["run_class"] = resolved
        old_short = RUN_CLASS_SHORT.get(old_class, old_class)
        new_short = RUN_CLASS_SHORT.get(resolved, resolved)
        changed_runs.append(f"  {rn}  {title[:30]}  {old_short} → {new_short}")
        updated += 1

    if updated == 0:
        target = f"sample '{sample_pattern}'" if use_sample_filter else run_spec
        return CommandResult(
            success=False,
            message=f"No runs in catalog matching: {target}",
        )

    detail = "\n".join(changed_runs)
    return CommandResult(
        success=True,
        message=f"Reclassified {updated} run(s):\n{detail}\n\n"
        "Run /matchruns to rebuild the working table with updated classes.",
    )


_SHOW_TABLE_USAGE = (
    "Usage: /show table [filters] — display the working table (read-only).\n"
    "  --rows <spec>    rows by index: 50-100, 1,3,5, or a run number\n"
    "  --name <text>    rows whose sample name CONTAINS <text> (case-insensitive)\n"
    "  --sample <pat>   rows whose sample name matches <pat> exactly, or as a glob\n"
    "                   with * (e.g. *0.25phr*). --name is the easy 'contains' form.\n"
    "  Filters combine (AND): /show table --rows 50-100 --name 0.25phr"
)


async def handle_show_table(args: list[str], state: SessionState) -> CommandResult:
    """Handle /show table [--rows <spec>] [--name <text>] [--sample <pat>].

    Read-only view of the working table, optionally filtered. Filters combine:
      --rows    index/range/run-number selection (parse_row_selection)
      --name    case-insensitive substring of the sample name
      --sample  exact match, or glob when the pattern contains '*'
    No rows are removed from the table.
    """
    from eqsanscli.services.reduction_service import parse_row_selection

    table = state.current_table
    if not table.rows:
        return CommandResult(
            success=True,
            message=f"Working table '{table.name}' is empty. Use /load ipts <number> then /matchruns.",
        )

    rows_spec: str | None = None
    name_substr: str | None = None
    sample_pat: str | None = None

    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--rows", "--row", "--index", "--idx", "--range") and i + 1 < len(args):
            rows_spec = args[i + 1]
            i += 2
        elif a in ("--name", "--contains") and i + 1 < len(args):
            name_substr = args[i + 1]
            i += 2
        elif a == "--sample" and i + 1 < len(args):
            sample_pat = args[i + 1]
            i += 2
        else:
            return CommandResult(
                success=False,
                message=f"Unrecognized argument: {args[i]}\n\n{_SHOW_TABLE_USAGE}",
            )

    rows = build_working_table_display(state)
    applied: list[str] = []

    if rows_spec is not None:
        selected = set(parse_row_selection(rows_spec, table))
        rows = [r for r in rows if int(r["Idx"]) in selected]
        applied.append(f"rows {rows_spec}")

    if name_substr is not None:
        needle = name_substr.lower()
        rows = [r for r in rows if needle in r["Sample"].lower()]
        applied.append(f"name contains '{name_substr}'")

    if sample_pat is not None:
        rows = [r for r in rows if sample_matches(sample_pat, r["Sample"])]
        applied.append(f"sample '{sample_pat}'")

    if applied:
        filt = ", ".join(applied)
        if not rows:
            return CommandResult(
                success=True,
                message=f"No rows in table '{table.name}' matching {filt}.",
            )
        label = f"Working Table: {table.name} — {len(rows)} of {len(table.rows)} row(s) [{filt}]"
    else:
        label = f"Working Table: {table.name} ({len(table.rows)} rows)"

    return CommandResult(
        success=True,
        message=label,
        data={"type": "working_table", "rows": rows},
    )
