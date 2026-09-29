"""Commands the app tells the user to type must work (field report 2026-09-29).

`/session load` listed sessions under "Usage: /load session <name>", and
`/load session <name>` then refused with "Use /session load <name> …" — a loop.
An audit of every /command mention in the code, SKILL.md, README, knowledge/
and docs/pages then found README's `/save session …` (also refused) and /help's
`/confirm … --status`, an option that never existed and was silently dropped —
so `/confirm --status No` would have confirmed the IPTS as reduced (Yes).

    python -m pytest -q tests/test_command_forms.py
"""

from __future__ import annotations

import ast
import asyncio
import glob
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands import export as export_cmd
from eqsanscli.commands.router import CommandRouter
from eqsanscli.commands.registry import register_all
from eqsanscli.models.session_state import SessionState


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _router():
    r = CommandRouter()
    register_all(r)
    return r


def test_session_listing_hint_is_a_working_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    r, st = _router(), SessionState()
    saved = _run(r.dispatch("/session save mysess", st))
    assert saved.success, saved.message
    listing = _run(r.dispatch("/session load", SessionState()))
    hint = re.search(r"Usage: (/[^\[\n]+?) <name>", listing.message).group(1)
    assert hint == "/session load"
    loaded = _run(r.dispatch(f"{hint} mysess", SessionState()))
    assert loaded.success, loaded.message


def test_load_and_save_session_spellings_forward(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    r = _router()
    assert _run(r.dispatch("/save session other", SessionState())).success
    res = _run(r.dispatch("/load session other", SessionState()))
    assert res.success, res.message
    assert "instead" not in res.message


def test_confirm_refuses_what_it_does_not_understand(monkeypatch):
    called = []
    monkeypatch.setattr(export_cmd, "run_confirm_data",
                        lambda *a, **k: called.append(a) or (True, "confirmed"))
    st = SessionState()
    st.ipts = 37681
    r = _router()
    res = _run(r.dispatch("/confirm --status No", st))
    assert not res.success and "--status" in res.message
    assert not called                                  # nothing was written
    assert _run(r.dispatch('/confirm 37681 --comment "done"', st)).success
    assert called


def _documented_texts():
    for f in glob.glob(str(REPO / "src/eqsanscli/**/*.py"), recursive=True):
        for n in ast.walk(ast.parse(open(f).read())):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                for line in n.value.splitlines():
                    yield f, n.lineno, line
    docs = ["SKILL.md", "README.md", *glob.glob(str(REPO / "knowledge/*.md")),
            *glob.glob(str(REPO / "docs/pages/*.md"))]
    for f in docs:
        for i, line in enumerate(open(REPO / f), 1):
            yield f, i, line


def test_every_documented_flag_exists_in_code():
    """A `--flag` written after a /command anywhere we document it is parsed somewhere."""
    code = "".join(open(f).read() for f in
                   glob.glob(str(REPO / "src/eqsanscli/**/*.py"), recursive=True))
    known = set(re.findall(r"""["'](--[a-z][\w-]*)["'=]""", code))
    missing = set()
    for f, ln, line in _documented_texts():
        for m in re.finditer(r"(?<![\w/.])/([a-z][a-z-]*)\b([^`|\n]*)", line):
            for flag in re.findall(r"(?<![\w-])(--[a-z][\w-]*)", m.group(2)):
                if flag not in known:
                    missing.add(f"/{m.group(1)} {flag}  ({Path(f).name}:{ln})")
    assert not missing, "documented flags nobody parses:\n" + "\n".join(sorted(missing))
