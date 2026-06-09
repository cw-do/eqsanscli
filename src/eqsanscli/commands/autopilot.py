from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _infer_ipts_from_cwd() -> int | None:
    """If the current working directory is under /SNS/EQSANS/IPTS-NNNNN/...,
    return NNNNN. Otherwise return None."""
    cwd = os.path.abspath(os.getcwd())
    m = re.search(r"/IPTS-(\d+)(?:/|$)", cwd)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


_USAGE = (
    "Usage: /autopilot <ipts_number> [options]\n"
    "  /autopilot 35884                              — Full automated reduction\n"
    "  /autopilot current                            — Use current IPTS/catalog from session\n"
    "  /autopilot 35884 --continue                   — Reduce only NEW runs (reuse saved calibration)\n"
    "  /autopilot --continue                         — Continue from saved session in outputdir\n"
    "  /autopilot current --from 5                   — Start from step 5 (skip catalog/match/presets)\n"
    "  /autopilot 35884 --standard porsilb1          — Use porsilb1 as calibration standard\n"
    "  /autopilot 35884 --samples Bi1                — Only reduce Bi1 samples\n"
    "  /autopilot 35884 --exclude Y5                 — Reduce all except Y5\n"
    "  /autopilot 35884 --thickness 0.2              — Set thickness to 0.2 cm\n"
    "  /autopilot 35884 --bkg banjo                  — Use banjo as background\n"
    "  /autopilot 35884 --config 8m12a               — Reduce only 8m12a config\n"
    "  /autopilot 35884 --exclude Y5 --bkg emptyticell --thickness 0.15  — Combined\n"
    "  /autopilot 35884 --force                      — Re-reduce all (ignore done status)\n"
    "  /autopilot 35884 --fresh                      — Force reload of catalog + re-match table (ignore in-memory state)\n"
    "\n"
    "Autopilot steps (13 total):\n"
    "   1. Load catalog from ONCat\n"
    "   2. Match runs (build working table: trans/bkg/empty assignments)\n"
    "   3. Verify assignments\n"
    "   4. Apply presets to each configuration\n"
    "   5. Set output directory\n"
    "   6. Reduce standard sample (porsil, scale=1.0)\n"
    "   7. Calibrate absolute scale factors from standard\n"
    "   8. Apply scale factors to each config\n"
    "   9. Reduce all sample runs\n"
    "  10. Build stitch table\n"
    "  11. Smart overlap analysis\n"
    "  12. Stitch profiles\n"
    "  13. Plot results\n"
    "\n"
    "--from N: skip steps 1..(N-1) and start at step N. Requires catalog + working\n"
    "  table already in session (e.g. from prior /load ipts + /matchruns + /apply preset).\n"
    "  Examples:\n"
    "    --from 5  — skip load/match/verify/presets; set outputdir and proceed to porsil\n"
    "                (use when match table + configs are already set up the way you want)\n"
    "    --from 6  — skip outputdir too; jump straight to porsil reduction\n"
    "    --from 9  — skip standard/calibrate/apply-scale; reduce samples with existing scales\n"
    "    --from 10 — only stitch and plot (reductions are already done)\n"
    "    --from 13 — only plot\n"
    "  Cannot be combined with --continue."
)


async def handle_autopilot(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message=_USAGE)

    ipts = None
    samples: list[str] = []
    excludes: list[str] = []
    thickness: float | None = None
    bkg_sample: str | None = None
    config_filter: str | None = None
    force: bool = False
    use_current = False
    continue_mode = False
    standard_sample: str | None = None
    from_step: int = 1
    fresh: bool = False

    i = 0
    while i < len(args):
        a = args[i]
        if a.lower() == "current":
            use_current = True
            i += 1
            continue
        if a in ("--help", "-h", "help"):
            return CommandResult(success=False, message=_USAGE)
        if a == "--continue":
            continue_mode = True
            i += 1
            continue
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
        if a == "--standard" and i + 1 < len(args):
            standard_sample = args[i + 1]
            i += 2
            continue
        if a == "--from" and i + 1 < len(args):
            try:
                from_step = int(args[i + 1])
            except ValueError:
                return CommandResult(success=False, message=f"Invalid step number for --from: {args[i + 1]}")
            if from_step < 1 or from_step > 13:
                return CommandResult(success=False, message=f"--from must be between 1 and 13 (got {from_step})")
            i += 2
            continue
        if a == "--force":
            force = True
            i += 1
            continue
        if a == "--fresh":
            fresh = True
            i += 1
            continue
        if ipts is None:
            try:
                ipts = int(a)
            except ValueError:
                pass
        i += 1

    inferred_note = ""
    if use_current and not ipts:
        if state.ipts:
            ipts = state.ipts
        else:
            inferred = _infer_ipts_from_cwd()
            if inferred:
                ipts = inferred
                inferred_note = f"[dim]No IPTS in session — inferred IPTS-{inferred} from cwd.[/dim]"
            else:
                return CommandResult(
                    success=False,
                    message=(
                        "No IPTS in current session and cwd doesn't look like an "
                        "IPTS folder (expected /SNS/EQSANS/IPTS-NNNNN/...).\n"
                        "Use /load ipts <number> first, or pass /autopilot <number>."
                    ),
                )

    # Same inference for bare /autopilot (no 'current', no ipts arg)
    if not use_current and not ipts and not continue_mode:
        inferred = _infer_ipts_from_cwd()
        if inferred:
            ipts = inferred
            inferred_note = f"[dim]Inferred IPTS-{inferred} from cwd.[/dim]"

    # --continue without IPTS: will infer from saved session in outputdir
    if continue_mode and not ipts:
        ipts = 0  # sentinel — autopilot will load IPTS from saved session

    # --from N (N >= 2): can infer IPTS from existing session state
    if from_step >= 2 and not ipts:
        if state.ipts:
            ipts = state.ipts
        else:
            return CommandResult(
                success=False,
                message="--from requires IPTS in session. Use /load ipts <N> first or pass an IPTS.",
            )

    if not ipts and not continue_mode:
        return CommandResult(
            success=False,
            message=f"Please provide an IPTS number or use 'current'.\n\n{_USAGE}",
        )

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
    if continue_mode:
        data["continue_mode"] = True
    if standard_sample is not None:
        data["standard_sample"] = standard_sample
    if from_step > 1:
        data["from_step"] = from_step
    if fresh:
        data["fresh"] = True

    return CommandResult(
        success=True,
        message=inferred_note,
        data=data,
    )
