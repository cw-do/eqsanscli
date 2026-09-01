# CLAUDE.md — Development Context for eqsanscli

## Project Overview

Interactive CLI tool for EQSANS neutron scattering data reduction at SNS/ORNL.
Built with Python, Textual TUI framework, Rich for formatting.

### Architecture

```
src/eqsanscli/
  app.py              — Textual TUI entry point
  headless.py         — JSON-over-stdin/stdout entry point (agent integration)
  commands/           — Slash-command handlers (dispatched by router.py)
  services/           — Business logic (matching, reduction, calibration, stitch, etc.)
    detector.py       — detector geometry and image primitives (no policy)
    run_files.py      — locating a run's file from its number alone
    protocol.py       — parses knowledge/protocol.md; validators for the rules
                        decidable from session state
  models/             — Data models (session_state, working_table, run_metadata, config_id)
  integrations/       — External interfaces (oncat, drtsans_runner, json_builder)
  config/             — App settings (preset content lives in preset_configs/ at repo root)
  tui/widgets/        — TUI components
preset_configs/       — Preset JSON configs for known instrument configurations
```

### Key patterns

- Commands are registered ONCE in `commands/registry.py` (`register_all`), which both
  `app.py` and `headless.py` call. Only front-end-specific commands (`/help`, `/exit`,
  `/version`, `/list`, `/guide`) are registered in the entry points themselves.
- Also update the LLM command reference in `services/llm_handler.py` for natural language routing.
- Config identity is two-layered: `row.configuration` (may be a cloned config —
  drives *parameters*) vs `row.physical_configuration` (drives *file naming* and
  stitch grouping; see `row.output_stem`). Physics heuristics resolve clone names
  via `config_id.base_config_id()`.
- Config parameters resolve in four tiers: drtsans template defaults < JSON preset
  < machine-physics instrument files (run-aware, `services/instrument_files.py`)
  < explicit `/set config`. The six cycle-specific calibration params
  (`sensitivityfilename`, `darkfilename`, `beamfluxfilename`, `detectoroffset`,
  `scalecomponents.detector1`, `sampleoffset`) belong to the third tier — don't
  hand-edit them in presets.
- `app.py` has a `_render_data` method with hardcoded column lists per data type — update when adding columns.
- Session state auto-saves after every command. `catalog_data` is stored as list-of-dicts.
- `docs/` is a generated documentation site (GitHub Pages, main branch `/docs`).
  `python3 docs/generate.py` rebuilds it; reference pages are generated from the
  code, prose lives in `docs/pages/*.md`. See `docs/README.md` for which source
  owns what, and regenerate in the same commit as a change that affects it.
- `SKILL.md` is the **single** agent-facing document, covering both the TUI and
  the headless JSON protocol. `AGENT_SKILL.md` is a stub pointing at it —
  the two copies had drifted in both directions before they were merged.
  `tests/test_docs.py` asserts every registered command appears in it.

### Knowledge base

`knowledge/` holds instrument knowledge — physics and protocol, **not** command
reference. `knowledge/protocol.md` is authoritative: numbered rules with a
severity and an enforcement status. Code that contradicts it is a bug; a rule
that nothing checks yet is marked `unenforced` and is backlog for the `/review`
validators.

- Loaded by `services/knowledge.py:load_knowledge(topics)`. Only `protocol.md` is
  `load: always` (paid for on every natural-language call); everything else is
  `on-demand` and requested by topic.
- Command syntax and natural-language routing stay in
  `services/llm_handler.py:_SYSTEM_PROMPT` — exactly one home, because the two
  copies drifted before.
- `tests/test_knowledge.py` enforces structure: headers, unique rule ids, rule
  cross-references resolving, no hardcoded cycle constants, no concrete IPTS
  paths, and agreement with the code on the rules it can check.
- When you change behaviour that a rule describes, update the rule in the same
  commit.
- Rule prefixes: `CAT` catalog · `EMP` empty beam · `TBL` table completeness ·
  `BKG` background · `CAL` calibration files · `MSK` mask building · `CFG` config
  parameters · `SCL` absolute scale · `STC` stitching. A new algorithm gets a new
  prefix; ids are permanent.

### Versioning

**Bump the version with every revision** — the user relies on `/version` and the
TUI banner to tell which build is running.

- `src/eqsanscli/__init__.py:__version__` is the single source of truth.
  `pyproject.toml` reads it via `[tool.hatch.version] path`, so edit it in one
  place only. (They had drifted: `__init__` was `0.9.0` while `pyproject` said
  `0.1.0`.)
**Bump whenever code changes**, in the same commit as the change:

- **Small change → +0.0.1** (`0.10.0` → `0.10.1`): bug fix, message wording, a
  flag added to an existing command.
- **New command or behaviour change → +0.1.0** (`0.10.1` → `0.11.0`).
- Never leave a code revision unbumped, even a one-line fix.
- Documentation that only records an already-released version (e.g. filling in
  this Change Log after the fact) does **not** bump.

#### Version history

| Version | Date | Contents |
|---|---|---|
| 0.33.0 | 2026-08-31 | Fix: `emptyBeam`/`empty_beam`/`emptybeam` (camelCase or joined) titles were classified as plain transmissions, so empty beam was never assigned (IPTS-38659 `T-emptyBeam_4m 10A`). The empty-beam regex now matches `empty`/`emp`/`emt` joined to `beam` by any separator or none, using letter-boundary lookarounds (a trailing `\b` failed before `_`); background cells (`emptycell`/`emptyticell`) are still excluded. Also: `/show preset stitch_overlaps` now renders the overlap pairs and a how-to-edit hint instead of an empty table. |
| 0.32.0 | 2026-08-31 | `/export script --like … --adapt`: opt-in LLM revision for the config-mismatch case. Hybrid, not fully-LLM — code fills the matched configs' run arrays (exact, never the model), the LLM only removes surplus config blocks and rewires the stitch call, and `validate_adapt()` enforces that the model may **only comment lines out or change the stitch call** (any other altered active line is rejected), plus no active references to removed configs and the filled arrays survive. The un-verifiable stitch overlaps/target get a `# attn.` marker and the output is labelled review-required. Deterministic `--like` output also gains a header stating what was refilled vs kept verbatim. LLM call is injectable for offline testing. |
| 0.31.0 | 2026-08-31 | `/export script --like` now **fails closed on a configuration mismatch** instead of silently emitting a wrong script. Found in testing: a 4-block example against a 2-config table wrote a file that kept the example experiment's own run numbers in the two unmatched blocks (and still stitched all four). It now refuses when any example block has no matching table config, any table config has no block, or a block's comment/mask hint disagrees with its aligned config — with a message naming the mismatch. Auto-commenting/re-wiring the extra blocks is a planned follow-up. |
| 0.30.0 | 2026-08-31 | `/apply preset <file.json> <config>` now accepts a path to the user's own reduction JSON, not just a `preset_configs/` name — an existing `.json` (absolute, or relative to cwd/outputdir) wins over a same-named preset, and all its non-null configuration parameters are copied to the config (user-set values preserved unless `--force`). Also: the `--like` templated export gains an optional LLM fallback (`llm_identify_structure`) for unusual variable naming — the model returns a structured JSON mapping only (never code), applied through the same deterministic substitute/validate path; the heuristic still covers the common style offline. |
| 0.29.0 | 2026-08-31 | `/export script --like <example.py>` reproduces a user's own reduction script: it keeps every line of the example verbatim (EQVar setup, per-config loops, calibration params, arithmetic, mask paths, stitching) and refills only the input arrays — scattering/transmission/background/empty-beam run lists, sample names, thickness — from the current table. Deterministic "identify then substitute": `ast` parses the example, a heuristic maps `samscatt_N`/`# 9m 15A` blocks to table configs, code replaces only those RHS spans, and a validator fails closed (parse, runs exist in table, list lengths, no leftover example runs, non-input lines byte-identical). New `services/script_templating.py`. |
| 0.28.0 | 2026-08-28 | `/show table` gains filters that combine (AND): `--rows <spec>` (index range/list/run number, e.g. `50-100`), `--name <text>` (case-insensitive substring of the sample name, e.g. `0.25phr`), and `--sample <pat>` (exact or glob with `*`). Unknown args are rejected with usage. Read-only — no rows removed. |
| 0.27.1 | 2026-08-28 | Long sample names (and run titles) in the working/stitch tables now wrap onto more lines instead of being ellipsis-truncated: every free-text column gets `overflow="fold"`. Rich's default column overflow is `ellipsis`; the run columns only looked like they wrapped because their cell text carries an embedded newline. |
| 0.27.0 | 2026-08-28 | Cancel stops the whole parallel batch on one click. `reduce_row` now returns at once when the cancel event is already set — before, a freed worker launched the next queued drtsans (killed ~1s later) so a single click drained a 15-job batch only slowly, job by job. The executor loop also drops queued futures on cancel. Both front ends (`/reduce`, autopilot). |
| 0.26.0 | 2026-08-25 | `/autopilot --to N` (aliases `--till`/`--until`) stops after step N with a resumable summary; `--to 8` = reduce the standard, calibrate and apply the scale factor, then stop ("find the scale factor"). Unknown `--flags` are now rejected instead of the following number being parsed as the IPTS (which silently ran the whole pipeline). |
| 0.25.0 | 2026-08-24 | `/matchruns` matches a displacement series (`_d0`, `_d2`, …) to its single transmission — the `_dX` suffix is ignored, and a config with one transmission assigns it to every sample (warns "matched by configuration"). `/set <row> trans,emp <run>` sets several run fields at once (`,`/`+`, run fields only). |
| 0.20.1 | 2026-08-18 | Fix: `/mask create` crashed without `--dry-run` — a local named `state` shadowed the SessionState parameter. Coordinate system documented. |
| 0.20.0 | 2026-08-18 | Beam mask is a plain disc again; gravity leaks are reported and masked only on `--leak`, as one disc per lobe. Replaces 0.19.0's capsule. |
| 0.19.0 | 2026-08-18 | The beam mask covers direct beam that fell under gravity: a capsule spanning the vertical streak, not just the shadow. |
| 0.18.0 | 2026-08-18 | `/mask --disc <x>,<y>,<r>` masks an arbitrary disc in mm; preview axes now in mm so positions can be read off the picture. |
| 0.17.0 | 2026-08-18 | Tube detection rebuilt: median against a local baseline, relative dead/hot tests, statistical test gated on counts. A beam halo no longer masks whole tubes. |
| 0.16.2 | 2026-08-18 | Document `--top`/`--bottom`: pixel counts not indices, the 11-pixel floor and how to bypass it, and that the machine-physics tool names the two ends the other way round. |
| 0.16.1 | 2026-08-18 | Full `/mask` usage: in-CLI help with examples and troubleshooting, rewritten README section, corrected SKILL/AGENT_SKILL/knowledge/LLM entries. |
| 0.16.0 | 2026-08-18 | Beam-stop detection rebuilt on local contrast: a dim run's Poisson noise no longer produces a huge off-centre circle. Refuses when no shadow is discernible; `--beam-center` / `--beam-radius` added. |
| 0.15.1 | 2026-08-17 | `--beam-pad` back to y-pixels, the units the machine-physics mask tool uses; converted to mm internally. |
| 0.15.0 | 2026-08-17 | Beam stop masked in millimetres against real pixel positions — tube index is not a spatial coordinate, so the index-space circle was only 87% right. |
| 0.14.1 | 2026-08-17 | Fix: `/mask --beam-pad` padded only the y radius, distorting the beam circle (13% off aspect at the default, 77% at pad 6). |
| 0.14.0 | 2026-08-17 | `/mask create <run>` builds a mask from a run's own image, self-contained, named for its configuration so the resolver finds it. |
| 0.13.0 | 2026-08-17 | Knowledge base restructured into `knowledge/` with `protocol.md` as the authority; topic-aware loader; stale/contradicting `preset_configs/knowledge.md` removed. |
| 0.12.0 | 2026-08-17 | `/reduce` preflight: refuses rows with no empty beam (beam centre), with `--skip-missing` / `--force`; autopilot's `--from 4+` gap closed and `_reduce_phase` skips unreducible rows. |
| 0.11.0 | 2026-08-17 | Masks resolved per configuration from the working folder → this IPTS's shared folder → the cycle's `masks/` default; foreign-IPTS paths removed from presets; per-config mask note printed. |
| 0.10.1 | 2026-08-17 | Fix: compound commands (`/export script`, `/apply preset`) were silently not executed via natural language; actionable `/export script` guidance; LLM sees empty-table/no-catalog state and chains prerequisites. |
| 0.10.0 | 2026-08-17 | Three revisions, all shipped together (see the Change Log entries below, each tagged `v0.10.0`): **(1)** `/config` namespace + per-row `configuration_override`, clone naming rule, physics-based output naming, single command registry; **(2)** run-aware instrument calibration files from machine physics + `/instrument`; **(3)** `/set --config` selector + classify-vs-assign LLM routing. Also: `__init__.py` became the single version source. |
| 0.9.0 | earlier | `/version` command added |
| 0.1.0 | initial | first release |

From 0.10.0 onward, one bump per revision — the collapsed 0.10.0 above is the
last multi-revision version.
- Tag the Change Log heading with the version it shipped in, so history and
  builds line up.

### Testing

Six suites, 173 checks, no external dependencies beyond numpy/scipy. Run them all:

```bash
python3 -m pytest -q tests/          # system python3 has pytest; .venv does not
```

| suite | covers |
|---|---|
| `test_mask.py` (67) | `/mask` end to end — geometry, cross cuts, bands, tubes, discs, leaks, the archive lookup, and every threshold the README documents |
| `test_instrument_files.py` (39) | cycle scanning and run-aware resolution, over a synthetic tree **and** the live machine-physics share |
| `test_knowledge.py` (20) | the `knowledge/` editing contract, mechanically |
| `test_config_clone.py` (20) | clone/override flow, naming, session round-trip, entry-point registration parity |
| `test_reduce_preflight.py` (16) | what blocks a reduction and what only warns |
| `test_router_dispatch.py` (11) | compound-command dispatch and natural-language routing |

Rules that keep these useful:

- **Never pin a machine-physics value to a literal.** Those are re-reduced within
  a cycle — 2026B moved `detoffset` 66.763 → 66.714 on 2026-08-18 — so a literal
  fails on the day the resolver correctly picks up new calibration. Assert that
  what resolves equals what the folder currently holds, plus a plausibility range.
- **Pin documented constants instead.** `test_documented_thresholds` asserts every
  number in the README's *What sets each size* table, and
  `test_every_documented_flag_parses` walks every flag in the in-CLI help through
  the parser. Both have already caught real drift.
- The live-share suites skip themselves when `/SNS` is not mounted, so they are
  safe to run anywhere.

For a one-off check of something not worth a test, `sys.path.insert(0, "src")`
against system python3 works — the `.venv` has textual/rich but no pytest.

### Adding a new algorithm

Physics or geometry that decides *what* to do goes in `services/`, in plain
numpy, so it is testable without Mantid or drtsans; the command layer only parses
flags, formats output and writes files. `mask_service.py` is the worked example:
everything it decides is pure, and only two steps — reading a run's counts and
writing the mask — shell out to `drtsans`, via generated scripts kept in that
module.

When you add one:

1. **Write the rule down first.** `knowledge/protocol.md` is the authority; give
   the algorithm a rule prefix (`MSK-` for masks) with severity and enforcement
   status. Behaviour with no rule has nothing to be judged against.
2. **Report the derivation, not just the answer.** `BeamStop.how_sized()` and
   `MaskPlan.how_banded()` print the measurement, the factor and the bound behind
   every number, because "how did you decide that?" is the question these get
   asked. Record the same in the `.params.json` beside the output.
3. **Measure against real runs before believing it**, and put the numbers and the
   ground truth in the change-log entry. Every mask estimator that looked right in
   the abstract failed on a real run.
4. `services/<thing>_service.py` stays one algorithm's home, and builds on the
   shared layers rather than growing its own copy:
   - `detector.py` — reshaping, real pixel positions, local contrast, cross cuts
     and valley finding. Geometry and image primitives, no policy.
   - `run_files.py` — locating a run by number across the archive.
   - `protocol.py` — the rules, parsed; add a validator here when your rule is
     decidable from session state, and flip it to `enforced` in the document.

   `mask_service.py` is the worked example of the split: 1304 lines became 1041
   of mask policy over 243 of detector primitives and 70 of run lookup.

---

## Change Log

The **last 5 revisions** are below. Everything older is in
[`docs/CHANGELOG.md`](docs/CHANGELOG.md), which is not loaded into the session —
read it when you need the history of a decision.

When adding an entry: put it here, and move the oldest one out to
`docs/CHANGELOG.md` so this list stays at 5.

### 2026-08-31: empty beam matches camelCase names; /show preset stitch_overlaps (v0.33.0)

**1 — empty beam not assigned (IPTS-38659).** `/matchruns` left every row without
an empty beam even though the runs `T-emptyBeam_4m 10A` / `T-emptyBeam_2.5m 2.5A`
were present. `classify_title` read them as plain **transmissions**: the
`_EMPTY_BEAM_RE` only matched "empty beam" with a literal space or standalone
"empty" as a whole word, so the camelCase joined form matched nothing. Two subtle
points in the fix: (a) `empty`/`emp`/`emt` may join `beam` by any separator or
none (`empty beam`, `emptybeam`, `empty_beam`, `emptyBeam`); (b) a trailing `\b`
fails before `_` (underscore is a `\w` char), so the pattern uses letter-boundary
lookarounds `(?<![a-z])…beam(?![a-z])` instead. Background cells
(`emptycell`/`emptyticell`/`empty_ticell`) still classify as background — they
have no word boundary after "empty" and are matched by BKG keywords first. Now
`T-emptyBeam_4m 10A` → `empty_trans` and becomes the config's empty beam.

**2 — `/show preset stitch_overlaps`** showed an empty table (it is not a config
preset — it holds an `overlaps` list, not a `configuration` section). It now
detects that shape (`load_preset_raw`) and prints the config pairs with their
overlap Q-windows and notes, plus a how-to-edit hint pointing at the JSON file
and the entry format. Smart stitch prefers a listed pair's overlap over the
auto-computed one; unlisted pairs fall back to auto.

`tests/test_matching.py` (+3: camelCase/joined/underscore → empty, background not
swallowed, empty beam assigned end to end) and `tests/test_apply_preset_file.py`
(+1: overlaps render + edit hint). 272 tests.

**Files changed:** `services/matching_service.py`, `services/preset_service.py`,
`commands/preset.py`, `tests/test_matching.py`, `tests/test_apply_preset_file.py`,
CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-08-31: --adapt — LLM revises the script for a config mismatch (v0.32.0)

The fail-closed guard (v0.31.0) was safe but a dead end for the real case: a
4-config template used for a 2-config experiment. `--adapt` (opt-in) now lets an
LLM revise the script — but as a **hybrid**, decided after weighing fully-LLM
against it:

- **Fully-LLM** (model returns the whole revised script, trusted) throws away the
  verbatim guarantee — it could silently change a calibration constant, the
  absolute-scale arithmetic, a mask path. Rejected for real reduction.
- **Hybrid (built):** code fills the matched configs' run arrays deterministically
  (the model never touches a run number); the LLM does only the structural
  surgery it is good at — comment out the surplus config blocks and rewire the
  `stitch_profiles(...)` call. `validate_adapt()` then enforces a hard contract:
  the model may **only** comment lines out or change the single stitch call —
  every other altered/added active line is rejected (this provably protects all
  kept parameters), plus no active reference to a removed config may remain and
  every filled array must survive. The one thing not machine-checkable — whether
  the new `overlap[…]` slice and `target_profile_index` are physically right —
  gets a `# attn.` marker and the whole output is labelled *review-required*.

`--adapt` engages only when the deterministic path can't handle it (mismatch);
when configs already line up it is a no-op that defers to the exact fill. The LLM
call (`llm_adapt_default`, via `settings.llm`) is injectable, so the safety layer
is tested offline: a good stub passes and flags the stitch; a stub that edits a
param or leaves stale runs is rejected; an unconfigured LLM fails gracefully.
The deterministic `--like` output also gained a header block stating what was
refilled vs kept verbatim (with a `# attn.` section).

Feasibility was proven first by running the transform by hand (Claude as the LLM):
a 4-block example → correct 2-config script, stitch rewired to
`stitch_profiles([iq1, iq2], overlap[2:4], target_profile_index=0)`.

`tests/test_script_templating.py` (25 checks). 268 tests. Deferred: reaching the
tool's own smaller model (gemini-3-flash / gpt-5-mini) needs a real key and its
reliability on the stitch rewrite is unverified — hence the review-required label.

**Files changed:** `services/script_templating.py`, `commands/export.py`,
`services/llm_handler.py`, `tests/test_script_templating.py`, SKILL.md, CLAUDE.md,
`src/eqsanscli/__init__.py`.

### 2026-08-31: --like fails closed on a config mismatch (v0.31.0)

Testing the new `--like` export surfaced a dangerous case: the user's template had
4 configuration blocks but the experiment had only 2. The tool matched 2 blocks
to the table and left the other 2 with the **example experiment's own run
numbers**, wrote the file (ok=True, warning only), and the emitted script would
still stitch all 4 profiles. Running it would reduce runs from a different
experiment and mis-stitch — silent garbage.

Now `fill_from_example()` refuses before writing when the example and table don't
line up: any example block with no matching table config (would keep stale runs),
any table config with no block (samples silently unreduced), or a block whose
comment/mask hint disagrees with the config it would be aligned to. The error
names the exact mismatch and the block count on each side.

The safe options are to use an example whose configurations match the table, or
trim one to fit. Automatically commenting out and re-wiring the surplus blocks —
including the `stitch_profiles([...], overlap[...], target_profile_index=...)`
call, whose overlaps and target index depend on the profile count — is a planned
follow-up (task), left out here because guessing the stitch rewrite is unsafe.

`tests/test_script_templating.py` (18 checks): fewer-configs and extra-config both
fail closed and write nothing; the command reports the mismatch. 261 tests.

**Files changed:** `services/script_templating.py`,
`tests/test_script_templating.py`, CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-08-31: /apply preset from a file, and an LLM fallback for --like (v0.30.0)

Two follow-ups, built on a branch for testing before merge.

**1 — `/apply preset <file.json> <config>`.** `/apply preset` resolved only names
in `preset_configs/`, so pointing it at the user's own reduction JSON
("use this.json as the configuration parameters for 2.5m2.5a") failed with
"Preset not found". New `resolve_preset_source()` treats the argument as a path
first — an existing `.json` (as given, or resolved against cwd / the output dir)
wins over a same-named preset — and falls back to the `preset_configs/` lookup.
All non-null configuration parameters are flattened and copied; user-set values
are preserved unless `--force`. The copy-all mechanism itself was already correct;
this only widened where the source can come from. `tests/test_apply_preset_file.py`
(10 checks).

**2 — LLM fallback for `--like` odd naming.** The heuristic identifier covers the
`samscatt_N` + comment style offline. For scripts that name their input arrays
unusually, `llm_identify_structure()` asks the model to return a **structured JSON
mapping** (variable → role + config index) — never code — which
`apply_llm_mapping()` applies through the same deterministic substitute/validate
path, so the verbatim guarantee is unchanged. It runs only when the heuristic
finds nothing and `settings.llm.is_configured`; otherwise it is a no-op. Wired
into `/export script --like`. Tested with a stub identifier against an
odd-named fixture (no network): the fallback fires only when the heuristic is
empty, ignores unknown variable names, and fills correctly.

`tests/test_script_templating.py` grows to 16 checks. 259 tests.

**Files changed:** `services/preset_service.py`, `commands/preset.py`,
`services/script_templating.py`, `commands/export.py`, `services/llm_handler.py`,
`tests/test_apply_preset_file.py` (new), `tests/test_script_templating.py`,
SKILL.md, CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-08-31: reproduce a user's own script style — /export script --like (v0.29.0)

Asked whether the tool could "write a reduction script following the style of
script_style2.py (assume the table is done)" — reuse the user's own script (how
EQVar is set up, how many config loops, the stitching) and change only the run
lists / sample names, since every scientist's script differs slightly.

Framed as LLM work, but the reliable design is **identify, then substitute
deterministically** — the language model (if used at all) only *names* which
variables are the input arrays; code does the edit, so "keep everything else
verbatim" is exact and checkable. For the common style it needs no LLM:

- `parse_example()` — `ast` collects module-level assignments with their exact
  RHS character spans and the comment above each.
- `identify()` — regex maps `samscatt_N`/`samtrans_N`/`bkgscatt_N`/`bkgtrans_N`/
  `emptybeam_N`, `sample_names`, `sample_thick`; the config hint per block comes
  from its comment (`# 9m 15A`) or a `maskWS…` token, normalized (`2p5`→`2.5`).
- `align()` — matches each block's hint to a table physical config, fills the
  rest by order, and picks the reference sample order (warns on non-rectangular
  sample sets or missing/extra configs).
- `substitute()` — replaces only the identified RHS spans (back-to-front so
  offsets stay valid); scalar `emptybeam` stays scalar, lists stay lists.
- `validate()` — fails closed: the result must `ast.parse`; every emitted run
  must be in the table; per-config lengths match the sample count; no original
  example run survives in a replaced array; and every non-input line is
  byte-identical to the example.

Verified on the real `script_style2.py` (4 configs, per-sample loop, inline
stitch): only the 22 input lines change, everything from the first EQVar block
down is identical, and the output parses. An **LLM fallback** for odd variable
naming (structured-JSON identification, never code generation) is left as a
follow-up; the heuristic covers the common case offline.

`tests/test_script_templating.py` (12 checks) against a committed fixture copy of
the example + a synthetic 4-config table. 245 tests.

**Files changed:** `services/script_templating.py` (new), `commands/export.py`,
`services/llm_handler.py`, `tests/test_script_templating.py` +
`tests/fixtures/example_reduction_script.py` (new), SKILL.md, CLAUDE.md,
`src/eqsanscli/__init__.py`.

