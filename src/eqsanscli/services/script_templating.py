"""Fill a user's own reduction script with run numbers from the working table.

The user hands us an *example* script (their own style — how EQVar is set up, how
many configuration blocks, how stitching is done) and asks us to reproduce it for
the current reduction table, changing ONLY the input arrays: the scattering /
transmission / background run lists, the empty-beam numbers, the sample-name array
and thicknesses. Every other line — calibration parameters, arithmetic, mask
paths, the stitch overlaps — is kept byte-for-byte.

Design: **identify, then substitute deterministically.** We parse the example
with `ast`, decide which module-level assignments are the input arrays and which
physical configuration each belongs to (a heuristic that covers the common
`samscatt_0` + `# 9m 15A` style, with an optional LLM fallback for odd naming),
and then replace only the right-hand side of those assignments with values pulled
from the table. Because code — not a language model — performs the edit, the
"keep everything else verbatim" guarantee is exact and machine-checkable.

Nothing here imports Mantid/drtsans; it is pure text + ast, so it is testable
against a fixture script with a synthetic table.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from eqsanscli.models.config_id import normalize_config_id
from eqsanscli.models.working_table import WorkingTable

# Roles an input array can play. The value each maps to on a WorkingTableRow.
ROLE_FIELDS = {
    "samscatt": "scattering_run",
    "samtrans": "transmission_run",
    "bkgscatt": "background_scatt",
    "bkgtrans": "background_trans",
    "emptybeam": "empty_beam",
}

# Variable-name patterns → role. Tolerant of separators and common spellings so a
# user's own naming (samscatt_0, sam_scatt0, scatt_run_1, …) still resolves.
_ROLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("samtrans", re.compile(r"^(?:sam(?:ple)?[_]?trans|trans(?:mission)?[_]?run|samt)[_]?(\d+)$", re.I)),
    ("samscatt", re.compile(r"^(?:sam(?:ple)?[_]?scatt|scatt(?:ering)?[_]?run|sams)[_]?(\d+)$", re.I)),
    ("bkgtrans", re.compile(r"^(?:bkg|back(?:ground)?)[_]?trans[_]?(\d+)$", re.I)),
    ("bkgscatt", re.compile(r"^(?:bkg|back(?:ground)?)[_]?scatt[_]?(\d+)$", re.I)),
    ("emptybeam", re.compile(r"^(?:empty(?:beam)?|emp|eb)[_]?(\d+)$", re.I)),
]

_SAMPLE_NAMES_RE = re.compile(r"^(?:sample[_]?names?|samplenames|names)$", re.I)
_THICK_RE = re.compile(r"^(?:sample[_]?thick(?:ness)?|thick(?:ness)?)$", re.I)


@dataclass
class Assignment:
    """A module-level `name = <rhs>` in the example, with exact source spans."""
    name: str
    lineno: int
    end_lineno: int
    # Absolute character offsets of the RHS in the raw source (for line-precise
    # replacement without touching the name or the `=`).
    rhs_start: int
    rhs_end: int
    rhs_text: str
    rhs_is_scalar: bool
    comment_above: str = ""


@dataclass
class ExampleModel:
    source: str
    assignments: list[Assignment]
    # role → {config_index → Assignment}
    role_blocks: dict[str, dict[int, Assignment]] = field(default_factory=dict)
    sample_names: Assignment | None = None
    sample_thick: Assignment | None = None
    # config_index → normalized config hint from comment/mask (may be "")
    config_hint: dict[int, str] = field(default_factory=dict)


@dataclass
class ConfigData:
    """Per-sample table data for one physical config, keyed by sample name."""
    config_id: str
    by_sample: dict[str, dict]  # sample_name → {role: value, "thickness": float}
    order: list[str]            # sample names in table order


# --------------------------------------------------------------------------
# 1. Table → per-config data
# --------------------------------------------------------------------------

def extract_table_data(table: WorkingTable) -> dict[str, ConfigData]:
    """Group the working table by physical config into per-sample run data.

    Keyed by normalized physical config id (e.g. "9m15a"). Each sample maps to
    its scattering/transmission/background/empty-beam runs and thickness. This is
    the deterministic source of run numbers — no language model touches it.
    """
    out: dict[str, ConfigData] = {}
    for row in table.rows:
        cid = normalize_config_id(row.physical_configuration)
        cd = out.get(cid)
        if cd is None:
            cd = ConfigData(config_id=cid, by_sample={}, order=[])
            out[cid] = cd
        name = row.sample_name
        if name not in cd.by_sample:
            cd.order.append(name)
        cd.by_sample[name] = {
            "samscatt": row.scattering_run,
            "samtrans": row.transmission_run,
            "bkgscatt": row.background_scatt,
            "bkgtrans": row.background_trans,
            "emptybeam": row.empty_beam,
            "thickness": row.thickness,
        }
    return out


# --------------------------------------------------------------------------
# 2. Parse the example
# --------------------------------------------------------------------------

def _abs_offset(source_lines_cum: list[int], lineno: int, col: int) -> int:
    """Absolute char offset from a 1-based lineno and 0-based col."""
    return source_lines_cum[lineno - 1] + col


def parse_example(source: str) -> ExampleModel:
    """Parse module-level assignments and the comment above each."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    # cumulative char offset at the start of each line
    cum = [0]
    for ln in lines:
        cum.append(cum[-1] + len(ln))

    # Map lineno → comment text for lines that are pure comments.
    comment_on_line: dict[int, str] = {}
    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            comment_on_line[i] = stripped.lstrip("#").strip()

    assignments: list[Assignment] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        val = node.value
        rhs_start = _abs_offset(cum, val.lineno, val.col_offset)
        rhs_end = _abs_offset(cum, val.end_lineno, val.end_col_offset)
        rhs_is_scalar = isinstance(val, ast.Constant) and isinstance(val.value, (int, float))
        # Nearest comment line above (skipping blank lines).
        comment = ""
        j = node.lineno - 1
        while j >= 1:
            if j in comment_on_line:
                comment = comment_on_line[j]
                break
            if source.splitlines()[j - 1].strip() == "":
                j -= 1
                continue
            break
        assignments.append(Assignment(
            name=target.id, lineno=node.lineno, end_lineno=node.end_lineno,
            rhs_start=rhs_start, rhs_end=rhs_end, rhs_text=source[rhs_start:rhs_end],
            rhs_is_scalar=rhs_is_scalar, comment_above=comment,
        ))

    return ExampleModel(source=source, assignments=assignments)


# --------------------------------------------------------------------------
# 3. Identify roles + config hints (heuristic)
# --------------------------------------------------------------------------

def _normalize_config_hint(text: str) -> str:
    """Turn '9m 15A', '2p5m 2p5A', 'maskWS1p3m1A.nxs' → a normalized config id.

    Returns "" when no distance+wavelength pair is discernible.
    """
    if not text:
        return ""
    t = text.lower()
    # 2p5 → 2.5, 1p3 → 1.3 (p between digits is a decimal point in file names)
    t = re.sub(r"(\d)p(\d)", r"\1.\2", t)
    dist = re.search(r"(\d+(?:\.\d+)?)\s*m\b", t)
    wl = re.search(r"(\d+(?:\.\d+)?)\s*a\b", t)
    if not dist or not wl:
        return ""
    return normalize_config_id(f"{dist.group(1)}m{wl.group(1)}a")


def identify(model: ExampleModel) -> ExampleModel:
    """Fill role_blocks / sample_names / sample_thick / config_hint by heuristic."""
    role_blocks: dict[str, dict[int, Assignment]] = {}
    hint_by_index: dict[int, list[str]] = {}

    for a in model.assignments:
        if model.sample_names is None and _SAMPLE_NAMES_RE.match(a.name):
            model.sample_names = a
            continue
        if model.sample_thick is None and _THICK_RE.match(a.name):
            model.sample_thick = a
            continue
        for role, pat in _ROLE_PATTERNS:
            m = pat.match(a.name)
            if m:
                idx = int(m.group(1))
                role_blocks.setdefault(role, {})[idx] = a
                # Gather config hints from this assignment's own comment and any
                # mask filename in its RHS (e.g. maskWS9m15A.nxs).
                hints = hint_by_index.setdefault(idx, [])
                h = _normalize_config_hint(a.comment_above)
                if h:
                    hints.append(h)
                break

    model.role_blocks = role_blocks

    # Also mine the whole source for maskWS<config>.nxs tokens, associating the
    # order they appear with config indices when comments were absent.
    for idx, hints in hint_by_index.items():
        model.config_hint[idx] = hints[0] if hints else ""

    return model


# --------------------------------------------------------------------------
# 3b. LLM fallback for odd variable naming (structured identification only)
# --------------------------------------------------------------------------
#
# When the heuristic finds no input arrays (a user names them
# scatt_run_first / etc.), an optional language-model pass can *identify* which
# assignment plays which role. It returns structured JSON — never code — which we
# apply the same way the heuristic does, so the deterministic substitute/validate
# path (and its verbatim guarantee) is unchanged.

def summarize_assignments(model: ExampleModel) -> list[dict]:
    """Compact description of each module-level assignment, for an LLM prompt."""
    out = []
    for a in model.assignments:
        preview = a.rhs_text.replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        out.append({
            "name": a.name,
            "comment": a.comment_above,
            "rhs": preview,
            "is_scalar": a.rhs_is_scalar,
        })
    return out


def apply_llm_mapping(model: ExampleModel, mapping: dict) -> bool:
    """Populate role_blocks / sample_names / sample_thick / config_hint from a
    structured mapping (see llm_identify_structure for the shape). Returns True
    if at least one input array was identified. Unknown variable names are
    ignored rather than trusted."""
    by_name = {a.name: a for a in model.assignments}

    sn = mapping.get("sample_names")
    if isinstance(sn, str) and sn in by_name:
        model.sample_names = by_name[sn]
    stk = mapping.get("sample_thick")
    if isinstance(stk, str) and stk in by_name:
        model.sample_thick = by_name[stk]

    role_blocks: dict[str, dict[int, Assignment]] = {}
    for block in mapping.get("blocks", []):
        if not isinstance(block, dict):
            continue
        try:
            idx = int(block.get("index"))
        except (TypeError, ValueError):
            continue
        cfg = str(block.get("config", "") or "")
        hint = normalize_config_id(cfg) or _normalize_config_hint(cfg)
        if hint:
            model.config_hint[idx] = hint
        for role in ROLE_FIELDS:
            name = block.get(role)
            if isinstance(name, str) and name in by_name:
                role_blocks.setdefault(role, {})[idx] = by_name[name]

    model.role_blocks = role_blocks
    return bool(role_blocks)


def llm_identify_structure(model: ExampleModel) -> bool:
    """Real LLM identification pass. Returns False (a no-op) when the LLM is not
    configured or the call fails — the caller then keeps the heuristic result.
    Isolated so the rest of the module stays pure and testable offline."""
    try:
        from eqsanscli.config.settings import AppSettings
        settings = AppSettings.load()
        if not settings.llm.is_configured:
            return False
        from openai import OpenAI
    except Exception:
        return False

    import json

    prompt = (
        "You are labelling the INPUT variables of an EQSANS reduction script so a "
        "tool can refill them from a run table. Below is every top-level assignment "
        "(name, the comment above it, a preview of its value). Identify: the array "
        "of sample names; the array of sample thicknesses; and, per detector "
        "configuration block, the variables holding the sample scattering runs "
        "(samscatt), sample transmission runs (samtrans), background scattering "
        "(bkgscatt), background transmission (bkgtrans) and empty-beam run "
        "(emptybeam). Give each block an integer index (0,1,2,... in file order) and "
        "a config string from its comment/mask if any (e.g. '9m15a', '2.5m2.5a'). "
        "Reply with ONLY JSON: {\"sample_names\": name|null, \"sample_thick\": "
        "name|null, \"blocks\": [{\"index\": int, \"config\": str, \"samscatt\": "
        "name, \"samtrans\": name, \"bkgscatt\": name, \"bkgtrans\": name, "
        "\"emptybeam\": name}]}. Use only names that appear in the list; omit a "
        "field if there is no matching variable.\n\nAssignments:\n"
        + json.dumps(summarize_assignments(model), indent=1)
    )

    try:
        client = OpenAI(base_url=settings.llm.base_url, api_key=settings.llm.api_key,
                        timeout=120.0)
        for mdl in [settings.llm.model, settings.llm.fallback_model]:
            try:
                resp = client.chat.completions.create(
                    model=mdl,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=4000,
                )
                text = resp.choices[0].message.content.strip()
                text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
                mapping = json.loads(text)
                return apply_llm_mapping(model, mapping)
            except Exception:
                continue
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
# 4. Align example config indices → table config ids
# --------------------------------------------------------------------------

@dataclass
class Alignment:
    index_to_config: dict[int, str]     # example config index → table config id
    reference_order: list[str]          # sample names, the shared array order
    warnings: list[str] = field(default_factory=list)


def align(model: ExampleModel, table_data: dict[str, ConfigData]) -> Alignment:
    """Map each example config block to a table config and pick a sample order."""
    indices = sorted({i for blk in model.role_blocks.values() for i in blk})
    table_ids = list(table_data.keys())
    used: set[str] = set()
    index_to_config: dict[int, str] = {}
    warnings: list[str] = []

    # First pass: match by config hint.
    for idx in indices:
        hint = model.config_hint.get(idx, "")
        match = next((c for c in table_ids if c not in used and normalize_config_id(c) == hint), "")
        if match:
            index_to_config[idx] = match
            used.add(match)

    # Second pass: fill unmatched indices by position, in order.
    leftover = [c for c in table_ids if c not in used]
    for idx in indices:
        if idx not in index_to_config:
            if leftover:
                c = leftover.pop(0)
                index_to_config[idx] = c
                used.add(c)
                warnings.append(
                    f"config block {idx} had no usable hint — aligned to '{c}' by order; verify."
                )
            else:
                warnings.append(f"config block {idx} has no table configuration to fill it.")

    for c in table_ids:
        if c not in used:
            warnings.append(f"table configuration '{c}' has no matching block in the example.")

    # Reference sample order: the aligned config with the most samples.
    aligned_cfgs = [table_data[c] for c in index_to_config.values()]
    reference_order: list[str] = []
    if aligned_cfgs:
        ref = max(aligned_cfgs, key=lambda cd: len(cd.order))
        reference_order = list(ref.order)
        # Warn on non-rectangular data (a sample missing from some config).
        for cd in aligned_cfgs:
            missing = [s for s in reference_order if s not in cd.by_sample]
            extra = [s for s in cd.order if s not in reference_order]
            if missing or extra:
                warnings.append(
                    f"config '{cd.config_id}' sample set differs from the reference "
                    f"({len(missing)} missing, {len(extra)} extra) — arrays would not line up."
                )

    return Alignment(index_to_config=index_to_config, reference_order=reference_order,
                     warnings=warnings)


# --------------------------------------------------------------------------
# 5. Substitute run-lists into the source verbatim
# --------------------------------------------------------------------------

def _as_literal(run):
    """A pure-integer run string renders as an int (matching the example's
    numeric arrays); anything else (multi-run "111, 112", blank) stays a string.
    Non-strings (a float thickness, an int) pass through unchanged."""
    if not isinstance(run, str):
        return run
    s = run.strip()
    if s.isdigit():
        return int(s)
    return s


def _render_rhs(values: list, scalar: bool) -> tuple[str, bool]:
    """Render a replacement RHS. Returns (text, ok). Not-ok means the scalar form
    was asked for but the values are not all identical."""
    lits = [_as_literal(v) for v in values]
    if scalar:
        uniq = set(map(repr, lits))
        if len(uniq) > 1:
            return repr(lits), False
        return repr(lits[0]) if lits else "None", True
    return repr(lits), True


@dataclass
class Substitution:
    new_source: str
    emitted: dict[str, list]                 # assignment name → emitted values
    replaced_lines: set[int]                 # 1-based line numbers whose text changed
    warnings: list[str] = field(default_factory=list)


def substitute(model: ExampleModel, table_data: dict[str, ConfigData],
               alignment: Alignment) -> Substitution:
    """Replace only the RHS of the identified input assignments; keep all else."""
    order = alignment.reference_order
    edits: list[tuple[int, int, str, str]] = []  # (start, end, new_rhs, name)
    emitted: dict[str, list] = {}
    warnings: list[str] = list(alignment.warnings)

    def _values_for(role: str, cfg_id: str) -> list:
        cd = table_data[cfg_id]
        return [cd.by_sample.get(s, {}).get(role, "") for s in order]

    # Per-config input arrays.
    for role, blocks in model.role_blocks.items():
        for idx, a in blocks.items():
            cfg_id = alignment.index_to_config.get(idx)
            if cfg_id is None:
                continue  # unmatched block — leave the example's own values
            vals = _values_for(role, cfg_id)
            text, ok = _render_rhs(vals, a.rhs_is_scalar)
            if not ok:
                warnings.append(
                    f"{a.name}: empty-beam differs between samples in '{cfg_id}'; "
                    f"emitted a list instead of a scalar — check the example's downstream use."
                )
            emitted[a.name] = [_as_literal(v) for v in vals]
            edits.append((a.rhs_start, a.rhs_end, text, a.name))

    # Shared arrays: sample_names and sample_thick, from the reference order.
    if model.sample_names is not None and order:
        text = repr(list(order))
        emitted[model.sample_names.name] = list(order)
        edits.append((model.sample_names.rhs_start, model.sample_names.rhs_end, text,
                      model.sample_names.name))
    if model.sample_thick is not None and order and alignment.index_to_config:
        ref_cfg = max((table_data[c] for c in alignment.index_to_config.values()),
                      key=lambda cd: len(cd.order))
        thick = [ref_cfg.by_sample.get(s, {}).get("thickness", "") for s in order]
        text, ok = _render_rhs(thick, model.sample_thick.rhs_is_scalar)
        emitted[model.sample_thick.name] = thick
        edits.append((model.sample_thick.rhs_start, model.sample_thick.rhs_end, text,
                      model.sample_thick.name))

    # Apply edits back-to-front so earlier offsets stay valid.
    src = model.source
    replaced_lines: set[int] = set()
    for start, end, text, _name in sorted(edits, key=lambda e: e[0], reverse=True):
        # Which 1-based lines does this span cover?
        pre = src[:start]
        first_line = pre.count("\n") + 1
        last_line = first_line + src[start:end].count("\n")
        replaced_lines.update(range(first_line, last_line + 1))
        src = src[:start] + text + src[end:]

    return Substitution(new_source=src, emitted=emitted,
                        replaced_lines=replaced_lines, warnings=warnings)


# --------------------------------------------------------------------------
# 6. Validate the result (fail closed)
# --------------------------------------------------------------------------

def validate(model: ExampleModel, sub: Substitution, table: WorkingTable,
             alignment: Alignment) -> list[str]:
    """Return a list of hard errors. Empty list means the script is safe to write."""
    errors: list[str] = []

    # (1) It must still parse.
    try:
        ast.parse(sub.new_source)
    except SyntaxError as e:
        errors.append(f"generated script does not parse: {e}")
        return errors  # nothing else is meaningful

    # (2) Every emitted run number must exist in the table.
    table_runs: set[str] = set()
    for row in table.rows:
        for field_name in ("scattering_run", "transmission_run", "background_scatt",
                            "background_trans", "empty_beam"):
            v = getattr(row, field_name, "")
            for part in str(v).replace("+", ",").split(","):
                part = part.strip()
                if part:
                    table_runs.add(part)
    for name, vals in sub.emitted.items():
        if name in (getattr(model.sample_names, "name", None),
                    getattr(model.sample_thick, "name", None)):
            continue
        for v in vals:
            s = str(v).strip()
            if not s:
                continue
            for part in s.replace("+", ",").split(","):
                part = part.strip()
                if part and part not in table_runs:
                    errors.append(f"{name}: run {part} is not in the working table.")

    # (3) Per-config list lengths must match the shared sample count.
    n = len(alignment.reference_order)
    for role, blocks in model.role_blocks.items():
        for a in blocks.values():
            if a.name in sub.emitted and not a.rhs_is_scalar:
                got = len(sub.emitted[a.name])
                if got != n:
                    errors.append(f"{a.name}: {got} values but {n} samples.")

    # (4) Substitution must actually have happened where a config was aligned.
    aligned_names = {a.name for role, blk in model.role_blocks.items()
                     for i, a in blk.items() if i in alignment.index_to_config}
    for a in model.assignments:
        if a.name in aligned_names and a.name in sub.emitted:
            new_rhs = repr(sub.emitted[a.name]) if not a.rhs_is_scalar else None
            if new_rhs is not None and new_rhs == a.rhs_text:
                errors.append(f"{a.name}: RHS unchanged — substitution did not run.")

    # (5) Only identified-assignment lines may differ from the example.
    allowed = set(sub.replaced_lines)
    for role, blk in model.role_blocks.items():
        for a in blk.values():
            allowed.update(range(a.lineno, a.end_lineno + 1))
    for a in (model.sample_names, model.sample_thick):
        if a is not None:
            allowed.update(range(a.lineno, a.end_lineno + 1))
    old_lines = model.source.splitlines()
    new_lines = sub.new_source.splitlines()
    # Compare line-by-line up to the shorter length; a length change is itself a
    # red flag unless it is inside a replaced multi-line span.
    for i, (o, nw) in enumerate(zip(old_lines, new_lines), start=1):
        if o != nw and i not in allowed:
            errors.append(f"line {i} changed outside an input array: {o!r} → {nw!r}")
    if len(old_lines) != len(new_lines):
        errors.append("line count changed — a multi-line array likely reformatted; "
                      "review before running.")

    return errors


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

@dataclass
class TemplateResult:
    ok: bool
    new_source: str
    alignment: Alignment
    warnings: list[str]
    errors: list[str]
    changed_vars: list[str] = field(default_factory=list)   # input arrays refilled
    review_required: bool = False                            # True for LLM --adapt output
    attn: list[str] = field(default_factory=list)            # human-review notes


def _mismatch(model: ExampleModel, alignment: Alignment,
              table_data: dict) -> tuple[list[int], list[str], list[int]]:
    """(unmatched example blocks, uncovered table configs, mis-hinted blocks)."""
    all_idx = {i for blk in model.role_blocks.values() for i in blk}
    matched = set(alignment.index_to_config.values())
    unmatched = sorted(all_idx - set(alignment.index_to_config))
    uncovered = [c for c in table_data if c not in matched]
    mishinted = [
        i for i, c in alignment.index_to_config.items()
        if model.config_hint.get(i) and normalize_config_id(c) != model.config_hint[i]
    ]
    return unmatched, uncovered, mishinted


def fill_from_example(source: str, table: WorkingTable,
                      llm_identify=None) -> TemplateResult:
    """Full pipeline: parse → identify → align → substitute → validate.

    `llm_identify` is an optional callable `(ExampleModel) -> bool` tried only when
    the heuristic finds no input arrays (unusual variable naming). It mutates the
    model in place and returns True on success. Passing None (the default) keeps
    the pipeline fully offline and deterministic.
    """
    model = identify(parse_example(source))
    used_llm = False
    if not model.role_blocks and llm_identify is not None:
        try:
            used_llm = bool(llm_identify(model))
        except Exception:
            used_llm = False
    if not model.role_blocks:
        hint = (" The LLM fallback did not recognise them either." if used_llm
                else " (An LLM fallback can be enabled for unusual variable names.)")
        return TemplateResult(
            ok=False, new_source="", alignment=Alignment({}, []),
            warnings=[],
            errors=["No input arrays (samscatt_N / samtrans_N / … ) were found in "
                    "the example. Is it an EQVar-style reduction script?" + hint],
        )
    table_data = extract_table_data(table)
    if not table_data:
        return TemplateResult(
            ok=False, new_source="", alignment=Alignment({}, []),
            warnings=[], errors=["The working table is empty — nothing to fill in."],
        )
    alignment = align(model, table_data)

    # Fail closed on a configuration mismatch. Silently writing a script whose
    # unmatched blocks still carry the EXAMPLE experiment's run numbers — and
    # whose stitch step still combines every block — is worse than refusing.
    unmatched, uncovered, mishinted = _mismatch(model, alignment, table_data)
    if unmatched or uncovered or mishinted:
        all_idx = {i for blk in model.role_blocks.values() for i in blk}
        errs: list[str] = [
            f"Configuration mismatch: the example has {len(all_idx)} config block(s) "
            f"but the table has {len(table_data)} ({', '.join(sorted(table_data))}). "
            f"Nothing was written."
        ]
        if unmatched:
            labels = ", ".join(
                f"block {i}" + (f" ({model.config_hint[i]})" if model.config_hint.get(i) else "")
                for i in unmatched
            )
            errs.append(
                f"  ✗ {len(unmatched)} example block(s) have no matching table config: "
                f"{labels}. They would keep the example's own run numbers and still be stitched."
            )
        if mishinted:
            errs.append(
                "  ✗ block(s) " + ", ".join(str(i) for i in mishinted) +
                " would be aligned to a config that disagrees with their comment/mask hint."
            )
        if uncovered:
            errs.append(
                f"  ✗ {len(uncovered)} table config(s) have no block in the example: "
                f"{', '.join(uncovered)} — their samples would not be reduced."
            )
        errs.append(
            "  Use an example whose configurations match the table, trim one to fit, "
            "or retry with --adapt to let the LLM revise the script (structural edits "
            "only, with the stitch call flagged for review)."
        )
        return TemplateResult(ok=False, new_source="", alignment=alignment,
                              warnings=alignment.warnings, errors=errs)

    sub = substitute(model, table_data, alignment)
    errors = validate(model, sub, table, alignment)
    return TemplateResult(
        ok=not errors, new_source=sub.new_source, alignment=alignment,
        warnings=sub.warnings, errors=errors, changed_vars=sorted(sub.emitted),
    )


# --------------------------------------------------------------------------
# 7. --adapt: LLM revises the script for a configuration mismatch
# --------------------------------------------------------------------------
#
# When the example has more configuration blocks than the table has configs, the
# deterministic path fails closed. --adapt instead: (1) fills the MATCHED blocks
# deterministically (code, not the model, touches run numbers), then (2) asks the
# LLM to perform ONLY the structural surgery it is good at — comment out the
# surplus blocks and rewire the stitch call. The result is validated hard and the
# un-verifiable part (the stitch overlaps/target) is marked "# attn." for review.

_ATTN = "# attn."


def build_adapt_prompt(partial_source: str, model: ExampleModel,
                       alignment: Alignment, removed: list[int]) -> str:
    """Careful prompt: fill is already done; the model only removes blocks and
    rewires the stitch, and must not touch anything else."""
    removed_desc = []
    for i in removed:
        hint = model.config_hint.get(i, "?")
        vars_ = [blk[i].name for blk in model.role_blocks.values() if i in blk]
        removed_desc.append(f"  - block {i} (config {hint}): input vars {', '.join(sorted(vars_))}")
    kept = ", ".join(f"{i}->{c}" for i, c in sorted(alignment.index_to_config.items()))

    return (
        "You are adapting an EQSANS reduction script. Its input run arrays for the "
        "KEPT configurations are ALREADY filled correctly — do not change any run "
        "number, sample name, thickness, calibration parameter, mask path, or "
        "arithmetic. Your ONLY job:\n"
        "  1. Remove the surplus configuration block(s) listed below — comment out "
        "(prefix with '# ') every line that belongs to each: its input-array "
        "assignments, its in-loop EQVar block (from `eq = EQVar()` through "
        "`reduceNow(eq)`, including the `print('... config N')` and "
        "`iqnameN = ...` lines), and its stitch lines (`iqN_fn = ...`, "
        "`iqN = load_iqmod(...)`).\n"
        "  2. Rewire the stitch call so it combines ONLY the surviving profiles, "
        "with the correct overlap slice and target_profile_index. The overlap list "
        "holds two values per junction between consecutive profiles, in order; "
        "keep only the junctions between surviving profiles, and set "
        "target_profile_index to the position of the former target within the new "
        "profile list.\n"
        f"  3. Append ' {_ATTN} verify stitch overlaps/target' to the rewired "
        "stitch line, and add a '" + _ATTN + " ...' comment on any other line a "
        "human should double-check.\n"
        "Rules: only COMMENT OUT lines or change the single stitch_profiles(...) "
        "line. Do NOT add, delete, or edit any other active line. Reply with the "
        "COMPLETE revised script and nothing else.\n\n"
        f"KEEP these blocks (index->config): {kept}\n"
        f"REMOVE these blocks:\n" + "\n".join(removed_desc) + "\n\n"
        "SCRIPT:\n" + partial_source
    )


def validate_adapt(partial_source: str, revised: str, model: ExampleModel,
                   table: WorkingTable, alignment: Alignment,
                   removed: list[int], sub: "Substitution") -> tuple[list[str], list[str]]:
    """Return (errors, attn_notes). Empty errors → safe to present for review."""
    errors: list[str] = []

    try:
        ast.parse(revised)
    except SyntaxError as e:
        return [f"LLM output does not parse: {e}"], []

    def _active(text: str) -> set[str]:
        return {l.rstrip() for l in text.splitlines()
                if l.strip() and not l.lstrip().startswith("#")}

    partial_active = _active(partial_source)
    revised_active = _active(revised)

    # (1) The model may only remove (comment) lines or change the stitch call.
    #     Any new active line that is not a stitch call means it altered something.
    new_active = revised_active - partial_active
    stray = [l.strip() for l in new_active if "stitch_profiles(" not in l]
    if stray:
        errors.append("LLM changed code outside the stitch call: "
                      + "; ".join(stray[:3]) + (" …" if len(stray) > 3 else ""))

    # (2) No active reference to any removed block's variables or original runs.
    removed_tokens: set[str] = set()
    removed_runs: set[str] = set()
    for i in removed:
        removed_tokens |= {f"iq{i}", f"iqname{i}"}
        for role, blk in model.role_blocks.items():
            if i in blk:
                removed_tokens.add(blk[i].name)
                for tok in re.findall(r"\d{3,}", blk[i].rhs_text):
                    removed_runs.add(tok)
    for line in revised_active:
        for tok in removed_tokens:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                errors.append(f"removed config still referenced: {line.strip()}")
                break

    # (3) The deterministically-filled arrays must survive unchanged.
    for name, vals in sub.emitted.items():
        want = f"{name}" 
        present = any(re.match(rf"\s*{re.escape(name)}\s*=", l) for l in revised_active)
        if not present:
            errors.append(f"filled array '{name}' was dropped by the LLM.")

    # (4) The stitch call must be active, reference no removed profile.
    stitch_lines = [l for l in revised_active if "stitch_profiles(" in l]
    if not stitch_lines:
        errors.append("no active stitch_profiles(...) call in the LLM output.")
    else:
        for i in removed:
            if any(re.search(rf"\biq{i}\b", l) for l in stitch_lines):
                errors.append(f"stitch call still includes removed profile iq{i}.")

    # attn notes: surface every '# attn.' line, and ensure the stitch line has one.
    attn = [l.strip() for l in revised.splitlines() if _ATTN in l]
    if stitch_lines and not any(_ATTN in l for l in revised.splitlines()
                                if "stitch_profiles(" in l):
        attn.append("stitch_profiles(...) — verify overlaps/target index (not marked by LLM)")

    return errors, attn


def llm_adapt_default(prompt: str) -> str | None:
    """Real LLM call for --adapt. Returns None when unconfigured or on failure."""
    try:
        from eqsanscli.config.settings import AppSettings
        settings = AppSettings.load()
        if not settings.llm.is_configured:
            return None
        from openai import OpenAI
    except Exception:
        return None
    try:
        client = OpenAI(base_url=settings.llm.base_url, api_key=settings.llm.api_key,
                        timeout=180.0)
        for mdl in [settings.llm.model, settings.llm.fallback_model]:
            try:
                resp = client.chat.completions.create(
                    model=mdl, messages=[{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=8000,
                )
                text = resp.choices[0].message.content.strip()
                # Strip a ```python fence if the model added one.
                text = re.sub(r"^```(?:python)?\s*|\s*```$", "", text, flags=re.S).strip()
                if text:
                    return text
            except Exception:
                continue
    except Exception:
        return None
    return None


def adapt_from_example(source: str, table: WorkingTable, llm_call,
                       llm_identify=None) -> TemplateResult:
    """--adapt: fill matched blocks deterministically, then let the LLM remove the
    surplus blocks and rewire stitch. `llm_call(prompt) -> str|None` is injectable
    for testing. Output is review-required, never trusted blindly."""
    model = identify(parse_example(source))
    if not model.role_blocks and llm_identify is not None:
        try:
            llm_identify(model)
        except Exception:
            pass
    if not model.role_blocks:
        return TemplateResult(False, "", Alignment({}, []), [],
                              ["No input arrays found in the example."])
    table_data = extract_table_data(table)
    if not table_data:
        return TemplateResult(False, "", Alignment({}, []), [],
                              ["The working table is empty — nothing to fill in."])

    alignment = align(model, table_data)
    unmatched, uncovered, _ = _mismatch(model, alignment, table_data)
    if uncovered:
        return TemplateResult(
            False, "", alignment, alignment.warnings,
            [f"--adapt cannot fabricate blocks for table config(s) with no example "
             f"block: {', '.join(uncovered)}. Extend the example instead."])
    if not unmatched:
        # Nothing to adapt — the deterministic path handles it exactly.
        return fill_from_example(source, table, llm_identify=llm_identify)

    # Fill the matched blocks deterministically (code owns the run numbers).
    sub = substitute(model, table_data, alignment)

    prompt = build_adapt_prompt(sub.new_source, model, alignment, unmatched)
    revised = None
    try:
        revised = llm_call(prompt) if llm_call else None
    except Exception:
        revised = None
    if not revised:
        return TemplateResult(
            False, "", alignment, alignment.warnings,
            ["--adapt needs a configured LLM (settings.llm) and it did not return a "
             "revision. Nothing was written."])

    errors, attn = validate_adapt(sub.new_source, revised, model, table,
                                  alignment, unmatched, sub)
    return TemplateResult(
        ok=not errors, new_source=("" if errors else revised), alignment=alignment,
        warnings=sub.warnings, errors=errors, changed_vars=sorted(sub.emitted),
        review_required=True, attn=attn,
    )
