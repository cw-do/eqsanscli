from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.reduction_service import parse_row_selection, reduce_row

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
            "  <row> = index, run number, range, or all\n"
            "  Examples: /reduce 1  |  /reduce 172815  |  /reduce 1-4  |  /reduce all\n"
            "            /reduce --sample porsil  |  /reduce --sample *3b*",
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
    else:
        selection = args[0]
        indices = parse_row_selection(selection, table)
        if not indices:
            return CommandResult(success=False, message=f"No valid rows for selection: {selection}")

    return CommandResult(
        success=True,
        message="",
        data={"type": "start_reduction", "indices": indices},
    )
