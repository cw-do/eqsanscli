"""Coherence of the knowledge/ base.

These checks exist because the file this folder replaced
(`preset_configs/knowledge.md`) drifted into contradicting itself and the code:
it named 2025B cycle files as current three cycles late, described a mask
fallback that had been removed, and stated `--sample` matching was substring
based two sections after correctly stating it was exact-unless-wildcard.

    python tests/test_knowledge.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from eqsanscli.services import knowledge as kb

KNOWLEDGE_DIR = ROOT / "knowledge"
DOCS = sorted(KNOWLEDGE_DIR.glob("*.md"))
VALID_LOAD = {"always", "on-demand", "never"}
RULE_ID_RE = re.compile(r"\b([A-Z]{3})-(\d{2})\b")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- structure ------------------------------------------------------------

def test_knowledge_directory_exists_and_is_found():
    assert DOCS, f"no .md files in {KNOWLEDGE_DIR}"
    assert kb.knowledge_dir() == KNOWLEDGE_DIR


def test_every_doc_has_a_complete_header():
    for doc in kb.load_docs():
        assert doc.topic, doc.path
        assert doc.load in VALID_LOAD, f"{doc.path}: load={doc.load!r}"
        assert doc.summary, f"{doc.path}: missing summary"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc.updated), \
            f"{doc.path}: updated={doc.updated!r}"


def test_topics_are_unique():
    topics = [d.topic for d in kb.load_docs()]
    assert len(topics) == len(set(topics)), topics


def test_exactly_one_always_loaded_doc_and_it_is_the_protocol():
    always = [d for d in kb.load_docs() if d.load == "always"]
    assert [d.topic for d in always] == ["protocol"], [d.topic for d in always]


def test_always_loaded_text_stays_small():
    """Paid for on every natural-language command — keep it lean."""
    text = kb.load_knowledge()
    assert text, "protocol.md is not being loaded"
    assert len(text) < 20000, f"{len(text)} chars on every LLM call"


def test_on_demand_docs_are_only_included_when_asked():
    always = kb.load_knowledge()
    assert "incoherent inelastic correction is normally" not in always.lower()
    asked = kb.load_knowledge(["configurations"])
    assert "numqbins" in asked.lower()


def test_index_is_never_auto_loaded():
    assert "Editing rules" not in kb.load_knowledge()
    assert "Editing rules" not in kb.load_knowledge(["protocol", "configurations"])


# --- protocol rules -------------------------------------------------------

def test_protocol_rule_ids_are_unique():
    text = _text(KNOWLEDGE_DIR / "protocol.md")
    ids = re.findall(r"^\*\*([A-Z]{3}-\d{2})\*\*", text, re.M)
    assert ids, "no rules found in protocol.md"
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]


def test_every_protocol_rule_declares_severity_and_enforcement():
    text = _text(KNOWLEDGE_DIR / "protocol.md")
    severities = {"blocking", "warning", "info"}
    enforcement = {"enforced", "advisory", "unenforced"}
    for line in text.splitlines():
        if not line.startswith("**") or "·" not in line:
            continue
        parts = [p.strip() for p in line.split("·")]
        rule = parts[0].strip("* ")
        assert parts[1] in severities, f"{rule}: severity {parts[1]!r}"
        assert parts[2].split()[0] in enforcement, f"{rule}: enforcement {parts[2]!r}"


def test_rule_references_in_other_docs_resolve():
    defined = set(re.findall(r"^\*\*([A-Z]{3}-\d{2})\*\*",
                             _text(KNOWLEDGE_DIR / "protocol.md"), re.M))
    for path in DOCS:
        if path.name == "protocol.md":
            continue
        for prefix, number in RULE_ID_RE.findall(_text(path)):
            rule = f"{prefix}-{number}"
            assert rule in defined, f"{path.name} cites undefined rule {rule}"


def test_files_named_as_enforcing_a_rule_exist():
    """`enforced (services/foo.py)` must point at something real."""
    text = _text(KNOWLEDGE_DIR / "protocol.md")
    for match in re.findall(r"enforced \(([^)]+)\)", text):
        for token in re.findall(r"[\w/]+\.py", match):
            assert (ROOT / "src" / "eqsanscli" / token).exists() or (ROOT / token).exists(), \
                f"protocol.md names a non-existent file: {token}"


# --- the specific drifts this folder was created to stop ------------------

def test_no_doc_hardcodes_a_current_cycle_file_as_a_constant():
    """The old file defined MP_DIR/FLOOD_4m/DARK_FILE and went stale."""
    for path in DOCS:
        text = _text(path)
        for banned in ("MP_DIR =", "FLOOD_4m =", "DARK_FILE =", "FLUX_FILE ="):
            assert banned not in text, f"{path.name} contains {banned!r}"


def test_no_doc_points_at_a_concrete_ipts_folder():
    """`IPTS-<current>` as a pattern is fine; a real IPTS number is not — that is
    how a mask from someone else's experiment ends up in a preset."""
    concrete = re.compile(r"/SNS/EQSANS/IPTS-\d+")
    for path in DOCS:
        found = concrete.findall(_text(path))
        assert not found, f"{path.name}: {found}"


def test_no_doc_repeats_the_stale_substring_claim():
    """--sample matching is exact unless * is used (models/sample_match.py)."""
    for path in DOCS:
        assert "case-insensitive substring" not in _text(path), path.name


def test_no_doc_claims_the_bkg_sample_gets_the_empty_beam():
    """Changed in 2026-06-09: the bkg sample gets NO background."""
    for path in DOCS:
        assert "empty beam as its background" not in _text(path), path.name


def test_no_doc_carries_a_natural_language_command_reference():
    """Editing rule 2: command routing lives in llm_handler, not here."""
    for path in DOCS:
        assert "NATURAL LANGUAGE → COMMAND" not in _text(path), path.name


def test_knowledge_agrees_with_the_code_on_flood_distance_mapping():
    from eqsanscli.services.instrument_files import flood_distance_for

    tags = [1.3, 2.5, 4.0]
    assert flood_distance_for(1.3, tags) == 1.3
    assert flood_distance_for(2.5, tags) == 2.5
    assert flood_distance_for(8.0, tags) == 4.0     # instrument-files.md table
    text = _text(KNOWLEDGE_DIR / "instrument-files.md")
    assert "beyond 4 m" in text and "1o3m" in text


def test_knowledge_agrees_with_the_code_on_mandatory_empty_beam():
    from eqsanscli.models.working_table import WorkingTableRow
    from eqsanscli.services.reduction_service import blocking_problems

    row = WorkingTableRow(index=1, scattering_run="1", sample_name="x", empty_beam="")
    assert any("empty beam" in p for p in blocking_problems(row))
    assert "EMP-01" in _text(KNOWLEDGE_DIR / "protocol.md")


def test_knowledge_agrees_with_the_code_on_the_band_floor():
    """MSK-05: measured, then floored at the 11-pixel convention."""
    import numpy as np

    from eqsanscli.services import detector as det
    from eqsanscli.services import mask_service as ms

    counts = np.ones((det.N_TUBES, det.N_PIXELS)) * 100.0
    counts[:, :3] = 0.0                      # a run whose ends fall off early
    plan = ms.build_plan(counts)
    assert plan.bottom == ms.DEFAULT_MIN_BAND == 11
    assert "11-pixel" in _text(KNOWLEDGE_DIR / "protocol.md")


def test_knowledge_agrees_with_the_code_that_a_bad_beam_stop_is_refused():
    """MSK-02: refuse rather than emit a wrong circle."""
    import numpy as np

    from eqsanscli.services import mask_service as ms

    from eqsanscli.services import detector as det

    noise = np.random.default_rng(0).poisson(4.0, size=(det.N_TUBES, det.N_PIXELS))
    beam, why = ms.find_beam_stop(noise.astype(float), *_synthetic_positions())
    assert beam is None and why
    assert "MSK-02" in _text(KNOWLEDGE_DIR / "protocol.md")


def test_knowledge_agrees_with_the_code_that_leaks_are_masked_below_only():
    """MSK-06: neutrons fall, so --leak covers what fell past the stop."""
    from eqsanscli.services import mask_service as ms

    source = (ROOT / "src" / "eqsanscli" / "services" / "mask_service.py").read_text()
    assert "if yc < plan.beam.yc:" in source, "leak masking is no longer below-only"
    assert ms.LEAK_CONTRAST > 1.0


def _synthetic_positions():
    """Real layout: y linear in pixel index, x interleaved in packs of four."""
    import numpy as np

    from eqsanscli.services import detector as det

    order = np.empty(det.N_TUBES, dtype=int)
    slot = 0
    for block in range(0, det.N_TUBES, 8):
        for offset in range(det.TUBE_PACK):
            for pack in (0, 1):
                tube = block + pack * det.TUBE_PACK + offset
                if tube < det.N_TUBES:
                    order[tube] = slot
                    slot += 1
    x = (order - (det.N_TUBES - 1) / 2.0) * 5.49
    y = (np.arange(det.N_PIXELS) - (det.N_PIXELS - 1) / 2.0) * 4.09
    return (np.repeat(x[:, None], det.N_PIXELS, axis=1),
            np.repeat(y[None, :], det.N_TUBES, axis=0))


# --- migration ------------------------------------------------------------

def test_legacy_single_file_is_gone():
    assert not (ROOT / "preset_configs" / "knowledge.md").exists(), \
        "preset_configs/knowledge.md is back — it is no longer read and will drift"


def test_loader_survives_a_missing_directory():
    import os
    import tempfile

    original = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)
            kb.clear_cache()
            # Repo copy is still found via the module path, so this must not raise.
            assert isinstance(kb.load_knowledge(), str)
        finally:
            os.chdir(original)
            kb.clear_cache()


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - standalone runner
            print(f"  FAIL  {name}: {exc}")
            failures.append(name)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed"
          + (f" — FAILED: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)
