"""`knowledge/protocol.md` and `services/protocol.py`, kept in agreement.

The document is the authority; this module is the part of it code can decide.
These checks make either side drifting a test failure: a rule with a validator
must say so in the document, and a rule the document says this file enforces must
have one.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from eqsanscli.models.session_state import SessionState              # noqa: E402
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow  # noqa: E402
from eqsanscli.services import protocol                             # noqa: E402


def _state(rows=(), configurations=None, catalog=None) -> SessionState:
    state = SessionState()
    table = WorkingTable("default")
    table.rows = list(rows)
    state.tables = {"default": table}
    state.active_table = "default"
    state.configurations = configurations or {}
    state.catalog_data = catalog
    return state


def _row(index=1, **kw) -> WorkingTableRow:
    fields = dict(index=index, scattering_run="100", sample_name="S",
                  detector_distance=4.0, wavelength=10.0, frequency=60)
    fields.update(kw)
    return WorkingTableRow(**fields)


# --- the document parses -------------------------------------------------

def test_every_rule_parses_with_a_severity_and_an_enforcement():
    rules = protocol.load_rules()
    assert len(rules) >= 48, len(rules)
    for rule in rules.values():
        assert rule.severity in protocol.SEVERITIES, rule
        assert rule.enforcement in ("enforced", "advisory", "unenforced"), rule
        assert rule.text, f"{rule.id} has no text"


def test_every_prefix_in_the_document_is_a_real_section():
    prefixes = {r.prefix for r in protocol.load_rules().values()}
    assert {"CAT", "EMP", "TBL", "BKG", "CAL", "MSK", "CFG", "SCL", "STC"} <= prefixes


# --- the document and this module agree ----------------------------------

def test_a_rule_with_a_validator_says_so_in_the_document():
    rules = protocol.load_rules()
    for rule_id in protocol.VALIDATORS:
        assert rule_id in rules, f"{rule_id} has a validator but no rule"
        rule = rules[rule_id]
        assert rule.enforcement == "enforced", f"{rule_id} is checked but marked {rule.enforcement}"
        assert "protocol.py" in rule.enforced_by, f"{rule_id}: enforced by {rule.enforced_by!r}"


def test_a_rule_the_document_gives_this_module_has_a_validator():
    for rule in protocol.load_rules().values():
        if "protocol.py" in rule.enforced_by:
            assert rule.id in protocol.VALIDATORS, \
                f"protocol.md says {rule.id} is enforced here, but nothing checks it"


def test_the_backlog_is_readable_from_code():
    backlog = {r.id for r in protocol.unenforced_rules()}
    assert backlog, "nothing unenforced — did the document lose its status column?"
    assert not (backlog & set(protocol.VALIDATORS))


# --- the validators actually catch what their rule describes -------------

def test_tbl_04_background_without_its_own_transmission():
    bad = _state([_row(background_scatt="200")])
    assert any(f.rule == "TBL-04" for f in protocol.check(bad))
    ok = _state([_row(background_scatt="200", background_trans="201")])
    assert not [f for f in protocol.check(ok) if f.rule == "TBL-04"]


def test_tbl_06_one_run_one_role():
    clash = _state([_row(scattering_run="100", background_scatt="100")])
    assert any(f.rule == "TBL-06" for f in protocol.check(clash))
    # an empty beam doubling as the transmission reference is normal, not a clash
    fine = _state([_row(transmission_run="300", empty_beam="300")])
    assert not [f for f in protocol.check(fine) if f.rule == "TBL-06"]


def test_bkg_01_background_from_another_configuration():
    catalog = [{"run_number": "100", "config": "4m10a"},
               {"run_number": "900", "config": "8m12a"}]
    bad = _state([_row(background_scatt="900")], catalog=catalog)
    findings = [f for f in protocol.check(bad) if f.rule == "BKG-01"]
    assert findings and "8m12a" in findings[0].message
    good = _state([_row(background_scatt="100")], catalog=catalog)
    assert not [f for f in protocol.check(good) if f.rule == "BKG-01"]


def test_bkg_01_is_silent_without_a_catalog():
    assert not [f for f in protocol.check(_state([_row(background_scatt="900")]))
                if f.rule == "BKG-01"]


def test_bkg_02_a_row_is_not_its_own_background():
    bad = _state([_row(scattering_run="100", background_scatt="100")])
    assert any(f.rule == "BKG-02" for f in protocol.check(bad))


def test_cfg_01_q_range():
    bad = _state(configurations={"4m10a": {"qmin": 0.05, "qmax": 0.01}})
    assert any(f.rule == "CFG-01" for f in protocol.check(bad))
    ok = _state(configurations={"4m10a": {"qmin": 0.01, "qmax": 0.05}})
    assert not protocol.check(ok)
    unset = _state(configurations={"4m10a": {"qmin": None, "qmax": None}})
    assert not protocol.check(unset)


# --- shape of the output --------------------------------------------------

def test_findings_are_blocking_first_and_format_cleanly():
    state = _state([_row(scattering_run="100", background_scatt="100")],
                   configurations={"4m10a": {"qmin": 0.05, "qmax": 0.01}})
    findings = protocol.check(state)
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda s: protocol.SEVERITIES.index(s))
    text = protocol.format_findings(findings)
    assert "BKG-02" in text and text.startswith("  ")
    assert protocol.format_findings([]) == "Protocol checks passed."


def test_a_broken_validator_never_breaks_the_caller():
    protocol.VALIDATORS["CFG-01"], original = (lambda s: 1 / 0), protocol.VALIDATORS["CFG-01"]
    try:
        findings = protocol.check(_state())
        assert any("check failed to run" in f.message for f in findings)
    finally:
        protocol.VALIDATORS["CFG-01"] = original
