"""Where eqsanscli's data folders live: knowledge/, preset_configs/,
absscale_reference/ and the shared .env.

In the development tree they sit at the repo root, four levels above the
modules that read them. In the stable release (`eqsanscli-safe`, a non-editable
install) the package lives in the venv's site-packages, so walking up from
`__file__` lands inside the venv — the launcher therefore exports
EQSANSCLI_ROOT pointing at the release folder, which holds copies of those
folders extracted from the same tag as the code.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def app_root() -> Path:
    """EQSANSCLI_ROOT when set to an existing folder, else the repo root."""
    env = os.environ.get("EQSANSCLI_ROOT", "").strip()
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return _REPO_ROOT
