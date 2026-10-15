"""What is running: eqsanscli version and commit, and the drtsans/Mantid it reduces with.

`/version` returns this as data so a caller (sansbook) can record provenance and
feature-detect (sansbook review B7). The drtsans and Mantid versions are asked of
drtsans itself — slow, it imports Mantid — so they are probed only on
`/version --probe` and cached in ~/.eqsanscli/drtsans_versions.json per channel.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from eqsanscli import __version__
from eqsanscli.paths import app_root

_CACHE = Path.home() / ".eqsanscli" / "drtsans_versions.json"


def commit() -> str:
    """The commit this build came from: the release's VERSION file, else git."""
    root = app_root()
    vf = root / "VERSION"
    if vf.is_file():
        for line in vf.read_text().splitlines():
            if line.startswith("commit:"):
                return line.split(":", 1)[1].strip()
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _read_cache() -> dict:
    try:
        return json.loads(_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def probe_drtsans(channel: str = "default", timeout: int = 240) -> dict:
    """Ask drtsans (through its conda wrapper) for its and Mantid's versions; cache them."""
    from eqsanscli.integrations.drtsans_runner import get_drtsans_cmd
    script = ("import json, drtsans, mantid\n"
              "print('EQSANSCLI_VERSIONS ' + json.dumps({'drtsans': drtsans.__version__, "
              "'mantid': mantid.__version__}))\n")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.run(get_drtsans_cmd(channel) + [path], capture_output=True,
                             text=True, timeout=timeout)
        for line in out.stdout.splitlines():
            if line.startswith("EQSANSCLI_VERSIONS "):
                found = json.loads(line.split(" ", 1)[1])
                found["probed"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                cache = _read_cache()
                cache[channel] = found
                _CACHE.parent.mkdir(parents=True, exist_ok=True)
                _CACHE.write_text(json.dumps(cache, indent=2))
                return found
        return {"error": (out.stderr or out.stdout).strip()[-300:]}
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e)}
    finally:
        os.unlink(path)


def version_info(channel: str = "default", probe: bool = False) -> dict:
    """{"eqsanscli", "commit", "root", "drtsans_channel", "drtsans", "mantid", …}.

    Shape is a contract for headless callers: change it only additively."""
    d = probe_drtsans(channel) if probe else _read_cache().get(channel, {})
    return {
        "type": "version",
        "eqsanscli": __version__,
        "commit": commit(),
        "root": str(app_root()),
        "drtsans_channel": channel,
        "drtsans": d.get("drtsans"),
        "mantid": d.get("mantid"),
        "drtsans_probed": d.get("probed"),
        "drtsans_error": d.get("error"),
    }


def version_message(info: dict) -> str:
    s = f"eqsanscli v{info['eqsanscli']}"
    if info.get("commit"):
        s += f" ({info['commit']})"
    if info.get("drtsans"):
        s += (f"\n  drtsans {info['drtsans']}, Mantid {info['mantid']} "
              f"[{info['drtsans_channel']}, checked {info['drtsans_probed']}]")
    elif info.get("drtsans_error"):
        s += f"\n  drtsans version: could not ask ({info['drtsans_error'][-120:]})"
    else:
        s += "\n  drtsans version not checked yet — /version --probe asks it (slow: imports Mantid)"
    return s
