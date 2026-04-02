from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.catalog_service import CatalogService

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
        rows.append({
            "Run #": str(int(row["run_number"])),
            "Title": str(row["title"])[:40],
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
            "  /show table                — Show working table\n"
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


async def handle_load_ipts(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /load ipts <number>")

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

    state.ipts = ipts
    state.catalog = df

    rows = _build_catalog_rows(df)
    return CommandResult(
        success=True,
        message=f"Loaded IPTS-{ipts} catalog ({len(df)} runs)",
        data={"type": "catalog", "rows": rows, "ipts": ipts},
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


async def handle_show_table(args: list[str], state: SessionState) -> CommandResult:
    """Handle /show table [--sample <name>] — display current working table.

    With --sample, filters to rows whose sample_name contains <name> (case-insensitive).
    This is read-only — no rows are removed.
    """
    table = state.current_table
    if not table.rows:
        return CommandResult(
            success=True,
            message=f"Working table '{table.name}' is empty. Use /load ipts <number> then /matchruns.",
        )

    sample_filter = None
    if args and args[0].lower() == "--sample" and len(args) >= 2:
        sample_filter = " ".join(args[1:])

    rows = build_working_table_display(state)

    if sample_filter:
        rows = [r for r in rows if sample_matches(sample_filter, r["Sample"])]
        if not rows:
            return CommandResult(
                success=True,
                message=f"No rows matching sample '{args[1]}' in table '{table.name}'.",
            )
        label = f"Working Table: {table.name} — {len(rows)} row(s) matching '{args[1]}'"
    else:
        label = f"Working Table: {table.name} ({len(table.rows)} rows)"

    return CommandResult(
        success=True,
        message=label,
        data={"type": "working_table", "rows": rows},
    )
