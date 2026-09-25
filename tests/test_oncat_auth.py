"""ONCat per-user authentication (Device Authorization Grant).

Access is per-user: a data call with no cached token and no env credentials must
refuse with OncatAuthRequired rather than silently using shared app creds. These
cover the non-interactive plumbing; the interactive browser sign-in itself is
exercised by hand (see the prototype), not here.

    python -m pytest -q tests/test_oncat_auth.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.integrations import oncat
from eqsanscli.commands.registry import register_all
from eqsanscli.commands.router import CommandRouter
from eqsanscli.models.session_state import SessionState


def _tok(monkeypatch) -> str:
    path = os.path.join(tempfile.mkdtemp(), "oncat_token.json")
    monkeypatch.setenv("EQSANSCLI_ONCAT_TOKEN", path)
    for var in ("ONCAT_USERNAME", "ONCAT_PASSWORD", "ONCAT_CLIENT_ID", "ONCAT_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    return path


def _run(router, cmd, state):
    return asyncio.new_event_loop().run_until_complete(router.dispatch(cmd, state))


def test_no_secret_in_source():
    src = Path(oncat.__file__).read_text()
    assert "client_secret=CLIENT_SECRET" not in src
    assert "3027a2b1" not in src            # the leaked m2m secret is gone
    assert oncat.PUBLIC_CLIENT_ID           # public device-flow client id present


def test_is_signed_in_reflects_token_file(monkeypatch):
    path = _tok(monkeypatch)
    assert oncat.is_signed_in() is False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text("{}")
    assert oncat.is_signed_in() is True
    assert oncat.sign_out() is True
    assert oncat.is_signed_in() is False


def test_data_call_without_token_raises_auth_required(monkeypatch):
    _tok(monkeypatch)
    try:
        oncat.fetch_catalog(38151)
        assert False, "expected OncatAuthRequired"
    except oncat.OncatAuthRequired as e:
        assert "sign" in str(e).lower() or "oncat login" in str(e).lower()


def test_load_ipts_surfaces_auth_message(monkeypatch):
    _tok(monkeypatch)
    router = CommandRouter(); register_all(router)
    res = _run(router, "/load ipts 38151", SessionState())
    assert res.success is False
    assert "Not signed in to ONCat" in res.message


def test_oncat_status_login_logout(monkeypatch):
    _tok(monkeypatch)
    router = CommandRouter(); register_all(router)
    st = SessionState()
    assert "oncat" in router.commands
    assert "Not signed in" in _run(router, "/oncat status", st).message
    res = _run(router, "/oncat login", st)                 # TUI worker trigger
    assert res.success and res.data.get("type") == "oncat_login"
    assert "No cached" in _run(router, "/oncat logout", st).message


def test_env_credentials_select_password_grant(monkeypatch):
    _tok(monkeypatch)
    monkeypatch.setenv("ONCAT_USERNAME", "u")
    monkeypatch.setenv("ONCAT_PASSWORD", "p")
    monkeypatch.setenv("ONCAT_CLIENT_ID", "c")
    monkeypatch.setenv("ONCAT_CLIENT_SECRET", "s")
    assert oncat._env_password_credentials() == ("u", "p", "c", "s")
    # builds without a browser even with no cached token (network login is lazy)
    client = oncat._make_client(interactive=False)
    assert client is not None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
