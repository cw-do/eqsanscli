"""The documentation surface, checked mechanically.

Two hand-maintained agent docs drifted apart in both directions before they were
merged (each had gained commands the other never learned). These checks make the
same drift fail a test instead of surviving into someone's session.

Run: python3 -m pytest -q tests/test_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _text(name: str) -> str:
    return (ROOT / name).read_text()


def _registered() -> set[str]:
    source = _text("src/eqsanscli/commands/registry.py")
    return set(re.findall(r'router\.register\("([^"]+)"', source))


def test_there_is_exactly_one_agent_skill_document():
    """SKILL.md is the single agent-facing document; AGENT_SKILL.md is a stub
    pointing at it, kept only so old references land somewhere correct."""
    stub = _text("AGENT_SKILL.md")
    assert len(stub.splitlines()) < 30, "AGENT_SKILL.md is growing content again"
    assert "SKILL.md" in stub
    assert "Merged into" in stub


def test_every_registered_command_is_documented():
    """The reference must list every command the router registers — this is the
    exact drift that split the two documents."""
    skill = _text("SKILL.md")
    missing = sorted(c for c in _registered() if f"/{c}" not in skill)
    assert not missing, f"commands registered but undocumented in SKILL.md: {missing}"


def test_skill_documents_both_front_ends():
    skill = _text("SKILL.md")
    assert "Headless" in skill and "stdin" in skill      # JSON protocol
    assert "python -m eqsanscli" in skill                # the TUI
    assert "/autopilot" in skill


def test_skill_does_not_claim_presets_need_applying_by_hand():
    """`/matchruns` auto-applies the matching preset and resolves the
    machine-physics files; the old headless copy still called it mandatory."""
    skill = _text("SKILL.md")
    assert "MANDATORY, DO NOT SKIP" not in skill
    assert "already applied" in skill


def test_entry_point_commands_are_not_claimed_by_the_registry():
    """/help, /exit and friends belong to the front ends, not registry.py."""
    from eqsanscli.commands.registry import ENTRY_POINT_COMMANDS

    assert not (_registered() & set(ENTRY_POINT_COMMANDS))
