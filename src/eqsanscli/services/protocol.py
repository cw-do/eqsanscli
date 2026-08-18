"""The reduction protocol, made executable.

`knowledge/protocol.md` is the authority on what a reduction must satisfy: each
rule carries an id, a severity and whether code enforces it. Until now nothing
read that file — it was injected into LLM context as prose, so "13 rules
unenforced" was a number no build could act on.

This module does two things:

1. **Parses the rules** out of `protocol.md` into `Rule` objects, so the ids,
   severities and enforcement claims are data.
2. **Holds the validators** for rules that are checkable against session state
   alone — no filesystem, no Mantid, no network. `check(state)` runs them and
   returns findings, blocking first.

The pairing is kept honest by `tests/test_protocol.py`: a rule with a validator
here must be marked `enforced (services/protocol.py)` in the document, and a rule
the document claims this file enforces must have a validator. Neither side can
drift without a test failing.

Rules needing a run's metadata, the reduced output, or a judgement call stay
`unenforced` and are listed by :func:`unenforced_rules` — that is the backlog,
readable from code rather than only by eye.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

SEVERITIES = ("blocking", "warning", "info")
_RULE_RE = re.compile(
    r"^\*\*([A-Z]{3}-\d{2})\*\*\s*·\s*(\w+)\s*·\s*(\w+)(?:\s*\(([^)]*)\))?\s*$", re.M
)


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str          # blocking | warning | info
    enforcement: str       # enforced | advisory | unenforced
    enforced_by: str       # what the document names, "" when nothing
    text: str              # the rule itself, as written

    @property
    def prefix(self) -> str:
        return self.id.split("-")[0]


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule} ({self.severity}): {self.message}"


def protocol_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.path.join(here, "knowledge", "protocol.md")


_CACHE: dict[tuple[str, float], dict[str, Rule]] = {}


def load_rules(path: Optional[str] = None) -> dict[str, Rule]:
    """Every rule in protocol.md, by id. Cached on the file's mtime."""
    path = path or protocol_path()
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return {}
    if key in _CACHE:
        return _CACHE[key]

    text = open(path).read()
    matches = list(_RULE_RE.finditer(text))
    rules: dict[str, Rule] = {}
    for i, m in enumerate(matches):
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():body_end].strip()
        body = body.split("\n---")[0].split("\n## ")[0].strip()
        rules[m.group(1)] = Rule(id=m.group(1), severity=m.group(2),
                                 enforcement=m.group(3), enforced_by=m.group(4) or "",
                                 text=body)
    _CACHE[key] = rules
    return rules


# --------------------------------------------------------------------------
# Validators — pure functions over session state. Each returns human-readable
# violations, empty when the rule holds. Register one only when the rule can be
# decided from state alone; anything needing a file, a run's metadata or a
# judgement stays unenforced and shows up in the backlog.
# --------------------------------------------------------------------------

def _rows(state) -> list:
    table = state.tables.get(state.active_table)
    return list(table.rows) if table else []


def _tbl_04(state) -> list[str]:
    """A background needs its own transmission, as the sample has one."""
    return [f"row {r.index} ({r.sample_name}): background {r.background_scatt} has no "
            f"background transmission"
            for r in _rows(state) if r.background_scatt and not r.background_trans]


def _tbl_06(state) -> list[str]:
    """One run, one role per configuration."""
    seen: dict[tuple[str, str], set[str]] = {}
    for r in _rows(state):
        for role, run in (("sample", r.scattering_run),
                          ("transmission", r.transmission_run),
                          ("background", r.background_scatt),
                          ("background transmission", r.background_trans),
                          ("empty beam", r.empty_beam)):
            for one in (part.strip() for part in str(run).split(",") if part.strip()):
                seen.setdefault((r.configuration, one), set()).add(role)
    out = []
    for (config, run), roles in sorted(seen.items()):
        # A background cell legitimately serves as its own sample row, and an
        # empty beam is routinely both empty-beam and transmission reference.
        if len(roles) > 1 and roles != {"empty beam", "transmission"}:
            out.append(f"{config}: run {run} is used as {' and '.join(sorted(roles))}")
    return out


def _bkg_01(state) -> list[str]:
    """A background must come from the row's own configuration."""
    by_run: dict[str, str] = {}
    for row in state.catalog_data or []:
        run = str(row.get("run_number") or row.get("Run") or "").strip()
        config = str(row.get("config") or row.get("Config") or "").strip()
        if run and config:
            by_run[run] = config
    if not by_run:
        return []                      # no catalog loaded: nothing to check against
    out = []
    for r in _rows(state):
        run = str(r.background_scatt).split(",")[0].strip()
        config = by_run.get(run)
        if run and config and config != r.physical_configuration:
            out.append(f"row {r.index} ({r.sample_name}) is {r.physical_configuration} "
                       f"but its background {run} is {config}")
    return out


def _bkg_02(state) -> list[str]:
    """A row cannot be its own background."""
    out = []
    for r in _rows(state):
        own = {p.strip() for p in str(r.scattering_run).split(",") if p.strip()}
        bkg = {p.strip() for p in str(r.background_scatt).split(",") if p.strip()}
        if own & bkg:
            out.append(f"row {r.index} ({r.sample_name}): background "
                       f"{', '.join(sorted(own & bkg))} is the row's own scattering run")
    return out


def _cfg_01(state) -> list[str]:
    """qmin < qmax wherever both are set."""
    out = []
    for config, params in sorted((state.configurations or {}).items()):
        qmin, qmax = params.get("qmin"), params.get("qmax")
        try:
            if qmin is not None and qmax is not None and float(qmin) >= float(qmax):
                out.append(f"{config}: qmin {qmin} is not below qmax {qmax}")
        except (TypeError, ValueError):
            out.append(f"{config}: qmin/qmax are not numbers ({qmin!r}, {qmax!r})")
    return out


VALIDATORS: dict[str, Callable[[object], list[str]]] = {
    "TBL-04": _tbl_04,
    "TBL-06": _tbl_06,
    "BKG-01": _bkg_01,
    "BKG-02": _bkg_02,
    "CFG-01": _cfg_01,
}


def check(state, *, only: Optional[list[str]] = None) -> list[Finding]:
    """Run every registered validator against `state`, blocking findings first."""
    rules = load_rules()
    findings: list[Finding] = []
    for rule_id, validator in VALIDATORS.items():
        if only and rule_id not in only:
            continue
        severity = rules[rule_id].severity if rule_id in rules else "warning"
        try:
            messages = validator(state)
        except Exception as exc:                      # never break a caller
            findings.append(Finding(rule_id, "info", f"check failed to run: {exc}"))
            continue
        findings.extend(Finding(rule_id, severity, m) for m in messages)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(findings, key=lambda f: (order.get(f.severity, 9), f.rule))


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "Protocol checks passed."
    marks = {"blocking": "✗", "warning": "⚠", "info": "·"}
    return "\n".join(f"  {marks.get(f.severity, '·')} {f}" for f in findings)


def unenforced_rules() -> list[Rule]:
    """The backlog: rules the document declares nothing checks yet."""
    return [r for r in load_rules().values() if r.enforcement == "unenforced"]
