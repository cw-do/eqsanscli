"""/trim — remove the first N / last N points (or points outside a Q range) of I(Q) files.

For finished files: a reduced `_Iq.dat` or a merged/stitched `merged_*_Iq.txt`.
To trim a configuration's curve *before* stitching, use
`/stitch set <sample|all> trim <config> --first N --last N` instead.
"""

from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.trim_service import TrimSpec, trim_file

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

USAGE = (
    "Usage: /trim <file|pattern> [...] [--first N] [--last N] [--qmin Q] [--qmax Q]\n"
    "             [-o <out> | --inplace]\n"
    "  Removes the first N / last N real points (NaN/empty edge rows don't count)\n"
    "  and/or points below --qmin / above --qmax. Writes <name>_trim<ext> beside the\n"
    "  original unless -o (one file) or --inplace (original kept as <name>.untrimmed).\n"
    "  Examples:\n"
    "    /trim merged_s1_8m12a_4m2.5a_Iq.txt --first 3 --last 5\n"
    "    /trim merged_*_Iq.txt --last 4\n"
    "    /trim s1_4m2.5a_Iq.dat --qmin 0.006 --qmax 0.4\n"
    "  Before stitching, per configuration: /stitch set <sample|all> trim <config> --last 5"
)


def parse_trim_flags(args: list[str]) -> tuple[TrimSpec, list[str], dict, str | None]:
    """(spec, positional, extra{out, inplace}, error)."""
    spec = TrimSpec()
    pos: list[str] = []
    extra = {"out": None, "inplace": False}
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--first", "--last", "--qmin", "--qmax", "-o", "--out", "--output"):
            if i + 1 >= len(args):
                return spec, pos, extra, f"{args[i]} needs a value"
            v = args[i + 1]
            try:
                if a == "--first":
                    spec.first = int(v)
                elif a == "--last":
                    spec.last = int(v)
                elif a == "--qmin":
                    spec.qmin = float(v)
                elif a == "--qmax":
                    spec.qmax = float(v)
                else:
                    extra["out"] = v
            except ValueError:
                return spec, pos, extra, f"{args[i]} needs a number, got '{v}'"
            i += 2
            continue
        if a == "--inplace":
            extra["inplace"] = True
        elif a.startswith("--"):
            return spec, pos, extra, f"Unknown option: {args[i]}"
        else:
            pos.append(args[i])
        i += 1
    if spec.first < 0 or spec.last < 0:
        return spec, pos, extra, "--first/--last must be ≥ 0"
    if spec.qmin is not None and spec.qmax is not None and spec.qmin >= spec.qmax:
        return spec, pos, extra, "--qmin must be below --qmax"
    return spec, pos, extra, None


async def handle_trim(args: list[str], state: SessionState) -> CommandResult:
    spec, patterns, extra, err = parse_trim_flags(args)
    if err or not patterns:
        return CommandResult(success=False, message=(f"{err}\n\n" if err else "") + USAGE)
    if spec.is_empty():
        return CommandResult(success=False,
                             message="Nothing to trim: give --first, --last, --qmin or --qmax.\n\n" + USAGE)

    files: list[str] = []
    for pat in patterns:
        hits = sorted(glob.glob(pat)) or sorted(glob.glob(os.path.join(state.output_directory, pat)))
        files.extend(h for h in hits if os.path.isfile(h))
    files = list(dict.fromkeys(os.path.abspath(f) for f in files))
    # Never re-trim our own outputs or backups when a pattern sweeps them up.
    files = [f for f in files if not f.endswith(".untrimmed")
             and not os.path.splitext(f)[0].endswith("_trim")]
    if not files:
        return CommandResult(success=False, message=(
            f"No files matched: {' '.join(patterns)} (searched . and {state.output_directory})"))
    if extra["out"] and len(files) > 1:
        return CommandResult(success=False, message="-o works with one file; omit it to write <name>_trim beside each.")

    lines, results, n_fail = [], [], 0
    for f in files:
        try:
            r = trim_file(f, spec, output=extra["out"], inplace=extra["inplace"])
            results.append(r)
            ends = []
            if r["removed_low"]:
                ends.append(f"low-Q {r['removed_low'][0]:.4g}–{r['removed_low'][1]:.4g}")
            if r["removed_high"]:
                ends.append(f"high-Q {r['removed_high'][0]:.4g}–{r['removed_high'][1]:.4g}")
            lines.append(f"  [green]✓[/green] {os.path.basename(f)} → {os.path.basename(r['output'])}  "
                         f"[dim]({r['n_before']} → {r['n_after']} points; removed {', '.join(ends) or 'none'})[/dim]")
        except (OSError, ValueError) as e:
            n_fail += 1
            results.append({"input": f, "error": str(e)})
            lines.append(f"  [red]✗[/red] {os.path.basename(f)} — {e}")

    head = f"Trimmed {len(files) - n_fail} file(s) ({spec.describe()})"
    if extra["inplace"]:
        head += " in place; originals kept as <name>.untrimmed"
    return CommandResult(success=n_fail == 0, message=head + ":\n" + "\n".join(lines),
                         data={"type": "trim", "spec": spec.to_dict(), "files": results})
