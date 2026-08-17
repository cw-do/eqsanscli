from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.reduction_service import (
    format_preflight, parse_row_selection, preflight, reduce_row,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _summarize_error(out_file: str, err_file: str) -> str:
    for path in [out_file, err_file]:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                lines = f.readlines()
            for line in reversed(lines):
                stripped = line.strip()
                if any(kw in stripped.lower() for kw in ["error", "exception", "traceback", "failed", "cannot"]):
                    return stripped[:150]
        except Exception:
            continue
    return "unknown error (check .out and .err files)"


async def handle_reduce(args: list[str], state: SessionState) -> CommandResult:
    if not args or args[0].lower() == "help":
        return CommandResult(
            success=False,
            message="Usage: /reduce <row>\n"
            "       /reduce --sample <name>\n"
            "       /reduce --new\n"
            "  <row> = index, run number, range, or all\n"
            "  --new = reduce only rows whose status is not 'done' (new/error/modified)\n"
            "  Rows missing an empty beam are refused up front; add --skip-missing to\n"
            "  reduce the rest, or --force to send them to drtsans anyway.\n"
            "  Examples: /reduce 1  |  /reduce 172815  |  /reduce 1-4  |  /reduce all\n"
            "            /reduce --sample porsil  |  /reduce --sample *3b*  |  /reduce --new",
        )

    # Preflight modifiers, stripped before selection parsing.
    force = any(a.lower() in ("--force", "-f") for a in args)
    skip_missing = any(a.lower() in ("--skip-missing", "--skip") for a in args)
    args = [a for a in args if a.lower() not in ("--force", "-f", "--skip-missing", "--skip")]
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /reduce <row> [--skip-missing | --force]\n"
            "  Give rows to reduce, e.g. /reduce all --skip-missing",
        )

    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message="Working table is empty. Use /matchruns first.")

    if args[0] == "--sample":
        if len(args) < 2:
            return CommandResult(success=False, message="Usage: /reduce --sample <name>")
        pattern = args[1]
        indices = [r.index for r in table.rows if sample_matches(pattern, r.sample_name)]
        if not indices:
            return CommandResult(success=False, message=f"No rows with sample name matching: {pattern}")
    elif args[0] == "--new":
        indices = [r.index for r in table.rows if r.status != "done"]
        if not indices:
            return CommandResult(
                success=True,
                message="No rows to reduce — all rows are already 'done'.",
            )
    else:
        selection = args[0]
        indices = parse_row_selection(selection, table)
        if not indices:
            return CommandResult(success=False, message=f"No valid rows for selection: {selection}")

    # Preflight: an empty beam is mandatory (beam centre). Refuse rather than let
    # drtsans fail per row with an opaque error.
    selected = [r for r in table.rows if r.index in set(indices)]
    blocked, advisory = preflight(selected)
    report = format_preflight(blocked, advisory, n_selected=len(selected))

    if blocked and not (force or skip_missing):
        return CommandResult(success=False, message=report)

    if blocked and skip_missing:
        blocked_indices = {r.index for r, _ in blocked}
        indices = [i for i in indices if i not in blocked_indices]
        if not indices:
            return CommandResult(
                success=False,
                message=report + "\n\n[red]Nothing left to reduce — every selected row is "
                "missing something required.[/red]",
            )

    prefix = ""
    if blocked and force:
        prefix = (
            f"[yellow]⚠ --force: reducing {len(blocked)} row(s) that are missing required "
            f"fields — expect drtsans failures.[/yellow]\n"
        )
    elif blocked and skip_missing:
        prefix = (
            f"[yellow]⚠ Skipping {len(blocked)} row(s) missing required fields; "
            f"reducing {len(indices)}.[/yellow]\n"
        )
    elif advisory:
        prefix = report + "\n"

    return CommandResult(
        success=True,
        message=prefix,
        data={"type": "start_reduction", "indices": indices},
    )
