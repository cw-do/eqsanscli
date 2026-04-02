from __future__ import annotations

import fnmatch


def sample_matches(pattern: str, sample_name: str) -> bool:
    """Match a sample name against a pattern. Case-insensitive.

    - No wildcard: exact match. "empty" matches only "empty".
    - With *: glob-style. "empty*" matches "empty", "emptycupbox".
      "*3b*" matches "S-3b", "S-3b-2".
    """
    p = pattern.lower()
    s = sample_name.lower()
    if "*" in p or "?" in p:
        return fnmatch.fnmatch(s, p)
    return p == s
