"""Loads the instrument knowledge base from `knowledge/`.

Each file carries a small header::

    ---
    topic: protocol
    summary: one line
    load: always | on-demand | never
    updated: YYYY-MM-DD
    ---

`load: always` files go into every LLM call; everything else is included only
when a caller names its topic. Keep `always` to `protocol.md` alone — the rest is
paid for in tokens on every natural-language command.

Read fresh from disk each time so edits take effect without a restart; parsed
headers are cached on file mtime.

See `knowledge/README.md` for what belongs in which file. `protocol.md` is
authoritative: if code or a preset disagrees with it, the other thing is a bug.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

#: Directories searched for the knowledge base, in order. The repo copy is the
#: shared one; a `knowledge/` folder in the working directory lets a user try
#: local edits without touching the install.
_SEARCH_DIRS = (
    Path(__file__).resolve().parent.parent.parent.parent / "knowledge",
    Path.cwd() / "knowledge",
)

#: The pre-0.13 single-file location. Warned about once if it still exists, so a
#: leftover copy is not silently ignored.
_LEGACY_PATHS = (
    Path(__file__).resolve().parent.parent.parent.parent / "preset_configs" / "knowledge.md",
    Path.cwd() / "preset_configs" / "knowledge.md",
)

_HEADER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

_PREAMBLE = (
    "EQSANS REDUCTION KNOWLEDGE (from knowledge/ — authoritative for physics and "
    "protocol decisions; protocol.md wins over any other source):\n\n"
)

_legacy_warned = False


@dataclass(frozen=True)
class Doc:
    topic: str
    summary: str
    load: str
    updated: str
    path: str
    body: str


_CACHE: dict[tuple, list[Doc]] = {}


def knowledge_dir() -> Optional[Path]:
    """First existing knowledge directory, or None."""
    for directory in _SEARCH_DIRS:
        if directory.is_dir():
            return directory
    return None


def _parse(path: Path) -> Optional[Doc]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return None

    fields: dict[str, str] = {}
    match = _HEADER_RE.match(text)
    body = text
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip().lower()] = value.strip()
        body = text[match.end():]

    return Doc(
        topic=fields.get("topic", path.stem),
        summary=fields.get("summary", ""),
        load=fields.get("load", "on-demand").lower(),
        updated=fields.get("updated", ""),
        path=str(path),
        body=body.strip(),
    )


def load_docs() -> list[Doc]:
    """Every knowledge document, cached on directory + file mtimes."""
    directory = knowledge_dir()
    if directory is None:
        _warn_legacy_once(missing_dir=True)
        return []

    files = sorted(directory.glob("*.md"))
    signature = (str(directory),) + tuple(
        (str(f), f.stat().st_mtime if f.exists() else 0.0) for f in files
    )
    if signature in _CACHE:
        return _CACHE[signature]

    docs = [d for d in (_parse(f) for f in files) if d is not None]
    _CACHE.clear()
    _CACHE[signature] = docs
    _warn_legacy_once()
    return docs


def _warn_legacy_once(*, missing_dir: bool = False) -> None:
    global _legacy_warned
    if _legacy_warned:
        return
    for legacy in _LEGACY_PATHS:
        if legacy.exists():
            logger.warning(
                "%s is no longer read — knowledge now lives in knowledge/ "
                "(see knowledge/README.md). Migrate anything still needed, then "
                "delete it so the two cannot drift.", legacy,
            )
            _legacy_warned = True
    if missing_dir and not _legacy_warned:
        logger.warning(
            "No knowledge/ directory found in %s — LLM calls will run without "
            "instrument knowledge.",
            " or ".join(str(d) for d in _SEARCH_DIRS),
        )
        _legacy_warned = True


def load_knowledge(topics: Optional[Sequence[str]] = None) -> str:
    """Knowledge text for an LLM call.

    `topics=None` returns the `load: always` documents. Naming topics adds those
    documents on top (`load: never` files, like the index, are only ever included
    when named explicitly).
    """
    docs = load_docs()
    if not docs:
        return ""

    wanted = {t.strip().lower() for t in (topics or ())}
    selected = [
        d for d in docs
        if d.load == "always" or (wanted and d.topic.lower() in wanted)
    ]
    if not selected:
        return ""

    parts = [
        f"## {doc.topic} — {doc.summary}\n\n{doc.body}" if doc.summary else f"## {doc.topic}\n\n{doc.body}"
        for doc in selected
    ]
    return _PREAMBLE + "\n\n---\n\n".join(parts)


def available_topics() -> list[tuple[str, str, str]]:
    """(topic, load, summary) for each document — for /help and diagnostics."""
    return [(d.topic, d.load, d.summary) for d in load_docs()]


def clear_cache() -> None:
    _CACHE.clear()
    global _legacy_warned
    _legacy_warned = False
