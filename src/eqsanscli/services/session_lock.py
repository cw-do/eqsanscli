"""One writer per folder's session (sansbook review B5).

Two eqsanscli processes on one working folder both autosave, and the last to exit
wins — a `/show` started during a long `/reduce` could overwrite that reduction's
row statuses. The first process takes `.eqsanscli/sessions/_autosave.lock`
({pid, host, started}); a second one finds it held and runs read-only (no
autosave). A lock is honoured while its holder is alive on this host, or for
24 h when it was taken on another node (liveness cannot be checked there).
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import time
from pathlib import Path

STALE_FOREIGN_SECONDS = 24 * 3600
_held: Path | None = None


def lock_path() -> Path:
    from eqsanscli.models.session_state import SessionState
    return Path(SessionState.auto_save_path()).with_name("_autosave.lock")


def _alive(info: dict) -> bool:
    if info.get("host") != socket.gethostname():
        return time.time() - float(info.get("started", 0)) < STALE_FOREIGN_SECONDS
    try:
        os.kill(int(info.get("pid", 0)), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:          # alive, owned by someone else
        return True


def holder() -> dict | None:
    """The live holder of this folder's lock, or None."""
    p = lock_path()
    try:
        info = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if int(info.get("pid", -1)) == os.getpid() and info.get("host") == socket.gethostname():
        return None
    return info if _alive(info) else None


def acquire(kind: str = "tui") -> tuple[bool, dict | None]:
    """(True, None) when this process now holds the lock; (False, holder) when
    another live process does. Released automatically at exit."""
    global _held
    other = holder()
    if other:
        return False, other
    p = lock_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                                 "started": time.time(), "kind": kind}))
        _held = p
        atexit.register(release)
    except OSError:
        pass            # an unwritable folder cannot autosave either; nothing to guard
    return True, None


def release() -> None:
    global _held
    if _held is None:
        return
    try:
        info = json.loads(_held.read_text())
        if int(info.get("pid", -1)) == os.getpid():
            _held.unlink()
    except (OSError, ValueError):
        pass
    _held = None


def describe(info: dict) -> str:
    age = time.time() - float(info.get("started", time.time()))
    return (f"pid {info.get('pid')} on {info.get('host')} ({info.get('kind', '?')}, "
            f"started {int(age // 60)} min ago)")
