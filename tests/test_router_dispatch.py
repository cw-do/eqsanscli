"""Router dispatch, especially compound commands via natural language.

Regression cover for the bug where `/export script` and `/apply preset ...`
were recognised by the direct path but not by the natural-language path, so the
LLM's command was echoed back as chat prose and silently never run.

    python tests/test_router_dispatch.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.router import CommandResult, CommandRouter
from eqsanscli.headless import _register_commands
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _router(state=None):
    router = CommandRouter()
    _register_commands(router, state or SessionState())
    return router


# --- _is_valid_command ----------------------------------------------------

def test_compound_commands_are_valid():
    router = _router()
    # Registered as two-word keys whose first word is NOT a bare command.
    assert router._is_valid_command("/export script")
    assert router._is_valid_command("/apply preset auto")
    assert router._is_valid_command("/apply preset conf_4m_10a_60hz 4m10a")


def test_bare_and_first_word_commands_are_valid():
    router = _router()
    for text in ("/matchruns", "/show table", "/show catalog", "/set config all numqbins 33",
                 "/list iq", "/refresh catalog", "/instrument show", "/reduce all"):
        assert router._is_valid_command(text), text


def test_aliases_are_valid():
    router = _router()
    assert router._is_valid_command("/quit")
    assert router._is_valid_command("/dir")


def test_unknown_and_non_commands_are_invalid():
    router = _router()
    for text in ("/nonsense", "not a command", "", "/", "/export nonsense-sub"):
        # "/export nonsense-sub" is invalid: neither "export" nor "export
        # nonsense-sub" is registered.
        assert not router._is_valid_command(text), text


# --- natural-language dispatch actually runs compounds --------------------

def test_nl_path_executes_a_compound_command(monkeypatch=None):
    """The reported failure: NL produced /export script and nothing ran."""
    import eqsanscli.services.llm_handler as llm

    state = SessionState()
    router = _router(state)

    async def fake_parse(user_input, st):
        return ["/export script"]

    original = llm.parse_natural_language
    llm.parse_natural_language = fake_parse
    try:
        result = _run(router.dispatch("make reduction script for me", state))
    finally:
        llm.parse_natural_language = original

    # It must have RUN the command (failing on the empty table with guidance),
    # not echoed "/export script" back as prose.
    assert "Nothing to export" in result.message, result.message
    assert result.success is False
    assert "→ /export script" in result.message  # the dim echo of what it ran


def test_nl_path_still_passes_prose_through():
    import eqsanscli.services.llm_handler as llm

    state = SessionState()
    router = _router(state)

    async def fake_parse(user_input, st):
        return ["Empty beam runs characterise the direct beam; they are not backgrounds."]

    original = llm.parse_natural_language
    llm.parse_natural_language = fake_parse
    try:
        result = _run(router.dispatch("what is an empty beam run?", state))
    finally:
        llm.parse_natural_language = original

    assert result.success is True
    assert "direct beam" in result.message


# --- /export script guidance ---------------------------------------------

def test_export_guidance_without_catalog():
    from eqsanscli.commands.export import handle_export_script

    msg = _run(handle_export_script([], SessionState())).message
    assert "no catalog is loaded" in msg
    assert "/load ipts" in msg and "/matchruns" in msg


def test_export_guidance_with_catalog_but_no_table():
    import pandas as pd

    from eqsanscli.commands.export import handle_export_script

    state = SessionState()
    state.ipts = 38773
    state.catalog = pd.DataFrame([{
        "run_number": 186510, "title": "S-A 4m 10a", "detector_distance": 4.0,
        "wavelength": 10.0, "frequency": 60, "run_class": "scattering",
    }])
    msg = _run(handle_export_script([], state)).message
    assert "/matchruns" in msg
    assert "1 run)" in msg          # singular
    assert "38773" in msg


def test_export_guidance_points_at_the_table_that_has_rows():
    from eqsanscli.commands.export import handle_export_script

    state = SessionState()
    state.tables["samples"] = WorkingTable("samples")
    state.tables["samples"].add_row(
        WorkingTableRow(index=0, scattering_run="1", sample_name="A")
    )
    msg = _run(handle_export_script([], state)).message
    assert "/table samples" in msg


# --- LLM context states prerequisites ------------------------------------

def test_context_states_empty_table_and_missing_catalog():
    from eqsanscli.services.llm_handler import _build_context

    context = _build_context(SessionState())
    assert "EMPTY" in context
    assert "NOT LOADED" in context


def test_context_names_other_tables_with_rows():
    from eqsanscli.services.llm_handler import _build_context

    state = SessionState()
    state.tables["samples"] = WorkingTable("samples")
    state.tables["samples"].add_row(
        WorkingTableRow(index=0, scattering_run="1", sample_name="A")
    )
    assert "samples" in _build_context(state)


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - standalone runner
            print(f"  FAIL  {name}: {exc}")
            failures.append(name)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed"
          + (f" — FAILED: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)
