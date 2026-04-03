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
            message="Usage: /autopilot <ipts_number> [options]\n"
            "  /autopilot 35884                              — Full automated reduction\n"
            "  /autopilot 35884 --samples Bi1                — Only reduce Bi1 samples\n"
            "  /autopilot 35884 --exclude Y5                 — Reduce all except Y5\n"
            "  /autopilot 35884 --thickness 0.2              — Set thickness to 0.2 cm\n"
            "  /autopilot 35884 --bkg banjo                  — Use banjo as background\n"
            "  /autopilot 35884 --config 8m12a               — Reduce only 8m12a config\n"
            "  /autopilot 35884 --exclude Y5 --bkg emptyticell --thickness 0.15  — Combined\n"
            "  /autopilot 35884 --force                        — Re-reduce all (ignore done status)",
        )

    ipts = None
    samples: list[str] = []
    excludes: list[str] = []
    thickness: float | None = None
    bkg_sample: str | None = None
    config_filter: str | None = None
    force: bool = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--samples" and i + 1 < len(args):
            raw = args[i + 1]
            samples = [s.strip() for s in raw.split(",") if s.strip()]
            i += 2
            continue
        if a == "--exclude" and i + 1 < len(args):
            raw = args[i + 1]
            excludes = [s.strip() for s in raw.split(",") if s.strip()]
            i += 2
            continue
        if a == "--thickness" and i + 1 < len(args):
            try:
                thickness = float(args[i + 1])
            except ValueError:
                return CommandResult(success=False, message=f"Invalid thickness: {args[i + 1]}")
            i += 2
            continue
        if a == "--bkg" and i + 1 < len(args):
            bkg_sample = args[i + 1]
            i += 2
            continue
        if a == "--config" and i + 1 < len(args):
            config_filter = args[i + 1]
            i += 2
            continue
        if a == "--force":
            force = True
            i += 1
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
    if excludes:
        data["excludes"] = excludes
    if thickness is not None:
        data["thickness"] = thickness
    if bkg_sample is not None:
        data["bkg_sample"] = bkg_sample
    if config_filter is not None:
        data["config_filter"] = config_filter
    if force:
        data["force"] = True

    return CommandResult(
        success=True,
        message="",
        data=data,
    )
