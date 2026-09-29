"""Data folders follow EQSANSCLI_ROOT (v0.47.3).

The stable release is a non-editable install: the package lives in the venv's
site-packages, so the old `Path(__file__).parent×4` lookups for knowledge/,
preset_configs/, absscale_reference/ and .env landed inside the venv and found
nothing — silently: no presets, no protocol, no LLM. The release launcher sets
EQSANSCLI_ROOT to the release folder; without it the repo root is used.

    python -m pytest -q tests/test_paths.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.paths import app_root


def test_default_is_the_repo_root(monkeypatch):
    monkeypatch.delenv("EQSANSCLI_ROOT", raising=False)
    assert app_root() == REPO
    for d in ("knowledge", "preset_configs", "absscale_reference"):
        assert (app_root() / d).is_dir()


def test_env_root_wins_when_it_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("EQSANSCLI_ROOT", str(tmp_path))
    assert app_root() == tmp_path.resolve()
    from eqsanscli.services.protocol import protocol_path
    assert protocol_path() == str(tmp_path.resolve() / "knowledge" / "protocol.md")


def test_missing_env_root_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("EQSANSCLI_ROOT", str(tmp_path / "nope"))
    assert app_root() == REPO


def test_no_module_walks_up_from_its_own_file():
    """Every data lookup goes through app_root(), or a release install breaks."""
    offenders = []
    for f in (REPO / "src/eqsanscli").rglob("*.py"):
        if f.name == "paths.py":
            continue
        s = f.read_text()
        if "parent.parent.parent.parent" in s or s.count("os.path.dirname(os.path.dirname") :
            offenders.append(str(f.relative_to(REPO)))
    assert not offenders, offenders
