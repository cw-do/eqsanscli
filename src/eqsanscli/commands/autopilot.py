from __future__ import annotations

import re
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_autopilot(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /autopilot <ipts_number> [--samples <name1,name2,...>]\n"
            "  /autopilot 35884                    — Full automated reduction\n"
            "  /autopilot 35884 --samples Bi1      — Only reduce Bi1 samples\n"
            "  /autopilot 35884 --samples Bi1,Bi2  — Only reduce Bi1 and Bi2\n\n"
            "  Or in natural language:\n"
            "  'autopilot 35884'\n"
            "  'run autopilot for ipts 34648 only for Bi1 samples'",
        )

    ipts = None
    samples: list[str] = []

    # Parse args: extract IPTS number and --samples flag
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--samples" and i + 1 < len(args):
            # Next arg is comma-separated sample names
            raw = args[i + 1]
            samples = [s.strip() for s in raw.split(",") if s.strip()]
            i += 2
            continue
        if ipts is None:
            try:
                ipts = int(a)
            except ValueError:
                pass
        i += 1

    if not ipts:
        return CommandResult(success=False, message="Please provide an IPTS number: /autopilot <number>")

    data: dict = {"type": "start_autopilot", "ipts": ipts}
    if samples:
        data["samples"] = samples

    return CommandResult(
        success=True,
        message="",
        data=data,
    )
