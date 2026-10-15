"""NOTE.md — per-outputdir reproducibility log.

Records commands the user runs and explicit `/note add` entries with timestamps.
The file lives at `{state.output_directory}/NOTE.md` so each experiment travels
with its own log.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


NOTE_FILENAME = "NOTE.md"

# Commands NOT auto-logged (read-only views, settings, the note command itself, etc.)
_LOG_DENYLIST = {
    "show", "list", "help", "settings", "note", "clear", "exit", "quit",
    "history", "model", "fast",
}

_HEADER_TEMPLATE = """# eqsanscli session log

Created: {created}

This NOTE.md is an automatic log of commands run with eqsanscli, plus any
manual notes added via `/note add "..."`. Replaying the listed commands in
order should reproduce the data reduction workflow recorded here.

Format: each entry is timestamped (HH:MM:SS). Lines starting with `>` are
commands; lines starting with `**NOTE**` are user-authored annotations.

---

"""


def note_path(state: SessionState) -> str:
    """Return the absolute path of NOTE.md for the current output directory."""
    return os.path.abspath(os.path.join(state.output_directory, NOTE_FILENAME))


def _ensure_note_file(path: str) -> None:
    """Create NOTE.md with header if it doesn't exist."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w") as f:
        f.write(_HEADER_TEMPLATE.format(created=created))


def _today_header() -> str:
    return datetime.now().strftime("## %Y-%m-%d\n")


def _append_with_day_header(path: str, line: str) -> None:
    """Append a line, inserting a `## YYYY-MM-DD` header on day boundaries."""
    today = _today_header()
    needs_header = True
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
        if today in content:
            # Find the last day header and check if it's today
            last_day_idx = content.rfind("\n## ")
            if last_day_idx >= 0:
                last_header_line = content[last_day_idx + 1 :].split("\n", 1)[0]
                if last_header_line == today.rstrip("\n"):
                    needs_header = False

    with open(path, "a") as f:
        if needs_header:
            f.write("\n" + today + "\n")
            try:
                from eqsanscli.version_info import commit
                from eqsanscli import __version__
                c = commit()
                f.write(f"_eqsanscli {__version__}{' (' + c + ')' if c else ''}_\n\n")
            except Exception:
                pass
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def append_user_note(state: SessionState, text: str) -> str:
    """Add a manual note. Returns the path."""
    path = note_path(state)
    _ensure_note_file(path)
    ts = datetime.now().strftime("%H:%M:%S")
    ipts_tag = f" [IPTS-{state.ipts}]" if state.ipts else ""
    line = f"- {ts}{ipts_tag}  **NOTE:** {text}"
    _append_with_day_header(path, line)
    return path


def maybe_log_command(state: SessionState, cmd_name: str, full_command: str) -> None:
    """Auto-log a command if it's not in the denylist. Silent on failure."""
    if cmd_name in _LOG_DENYLIST:
        return
    try:
        path = note_path(state)
        _ensure_note_file(path)
        ts = datetime.now().strftime("%H:%M:%S")
        ipts_tag = f" [IPTS-{state.ipts}]" if state.ipts else ""
        line = f"- {ts}{ipts_tag}  `> {full_command}`"
        _append_with_day_header(path, line)
    except Exception:
        # Never let logging break dispatch
        pass


def read_note(state: SessionState) -> str | None:
    """Return NOTE.md contents, or None if missing."""
    path = note_path(state)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return f.read()


def tail_note(state: SessionState, n_lines: int) -> str | None:
    """Return the last `n_lines` non-empty entries of NOTE.md, or None if missing."""
    content = read_note(state)
    if content is None:
        return None
    lines = [ln for ln in content.splitlines() if ln.strip()]
    return "\n".join(lines[-n_lines:])


def _plain(text: str) -> str:
    import re
    return re.sub(r"\[/?[a-zA-Z0-9 #_.,=-]*\]", "", text)


def result_summary(cmd_name: str, result) -> str | None:
    """One line saying what a command produced — NOTE.md was a list of commands
    with no numbers (sansbook review B3). None when there is nothing to add."""
    d = result.data if isinstance(getattr(result, "data", None), dict) else {}
    kind = d.get("type")
    if kind == "calibration":
        s = (f"f={d['factor']:.6g} over {d['qmin']}–{d['qmax']} ({d['n_points']} pts, "
             f"spread {d['std_rel']:.1%}) vs {os.path.basename(d['reference'])}")
        if d.get("applied"):
            s += f"; applied {d['new_scale']:.6g} (= s0 {d['porsil_scale']:.6g} × f) to {d['config']}"
        return s
    if kind == "stitch_result":
        parts = []
        for g in d.get("groups", []):
            if g.get("status") != "done":
                parts.append(f"{g['sample']}: FAILED")
                continue
            ovl = "; ".join(f"{p['overlap'][0]:.4g}–{p['overlap'][1]:.4g} ×{p['factor']:.4g}"
                            for p in g["pairs"])
            parts.append(f"{g['sample']} (target {g['target_config']}, {g['unit']}): {ovl}")
        return " | ".join(parts) if parts else None
    if kind == "trim":
        ok = [f for f in d.get("files", []) if "output" in f]
        spec = ", ".join(f"{k} {v}" for k, v in (d.get("spec") or {}).items())
        return (f"trimmed {spec} on {len(ok)} file(s): "
                + "; ".join(f"{os.path.basename(f['output'])} {f['n_before']}→{f['n_after']}" for f in ok[:6]))
    if kind == "check":
        f = d.get("findings", [])
        nb = sum(x["severity"] == "blocking" for x in f)
        rules = sorted({x["rule"] for x in f})
        return f"{len(f)} finding(s), {nb} blocking: {', '.join(rules) or 'none'}"
    if kind == "working_table" and cmd_name == "matchruns":
        rep = d.get("transmission_report") or {}
        return (f"{len(d.get('rows', []))} rows; {len(rep.get('rows_without', []))} without "
                f"transmission; {len(rep.get('unused', []))} transmission run(s) unused")
    if kind == "reduction_complete":
        failed = [r["sample"] for r in d.get("results", []) if r.get("status") == "error"]
        return (f"{d.get('success', 0)} done, {d.get('failed', 0)} failed"
                + (f": {', '.join(failed[:10])}" if failed else ""))
    for line in (result.message or "").splitlines():
        if "Absolute scale:" in line:
            return _plain(line.strip())
    return None


def log_result(state: SessionState, text: str | None) -> None:
    """Append `    → text` under the last logged command. Silent on failure."""
    if not text:
        return
    try:
        path = note_path(state)
        _ensure_note_file(path)
        _append_with_day_header(path, f"    → {_plain(text)}")
    except Exception:
        pass
