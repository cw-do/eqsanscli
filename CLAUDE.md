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
| 0.36.5 | 2026-09-01 | `/reduce` in parallel mode now shows which sample each job is at **submission** (a `⟳ <sample> (config) → …json` line per row), instead of only naming samples on completion — so a single parallel job no longer sits at "Submitting 1 jobs to 3 workers…" with nothing identifying it until it finishes. Mirrors the single-core start line and autopilot. TUI (`app.py`) multi-core `/reduce` branch. |
| 0.36.4 | 2026-09-01 | Fix: `/matchruns --update` kept using a run the user had reclassified to `ignore` (e.g. an old transmission remeasured after a bad wavelength). `--update` preserves existing rows' assignments verbatim, and never re-checked them against the fresh `ignore` set — so the stale transmission stayed assigned. It now reconciles preserved rows: rows whose scattering run is now `ignore` are removed, and any transmission/background/empty pointing at a now-ignored run is re-matched from the fresh table (rows marked `modified`), with a warning. Plain `/matchruns` (rebuild) already excluded `ignore`; only `--update` was affected. |
| 0.36.3 | 2026-09-01 | Fix: `/autopilot --from 9` re-reduced every row even when 8/9 were `done`. Steps 1–5 were skipped but the scale block (6–8) had no `--from` guard, so step 8 re-applied `standardabsolutescale` via `/set config`, which marks every row in that config `modified` — so step 9's skip-if-`done` saw no `done` rows and reduced all. `--from ≥ 9` now skips 6–8 and only *reports* the existing scale (no re-apply), matching the flag's documented "reduce samples with existing scales". `done` rows are preserved; only non-`done` rows reduce (still `--force` to redo all). |
| 0.36.2 | 2026-09-01 | Three fixes surfaced during real use. **`/autopilot --from 2`** was wrongly rejected with "requires a populated working table" — but step 2 *is* match-runs, which builds the table; `--from 2` now needs only a loaded catalog (`--from 3+` still need the table). **Step 4b** printed machine-physics files (dark/flood/flux/offset) under "user-set parameters per config" because its snapshot kept everything differing from the preset — it now also excludes resolver-owned values (tracked in `instrument_provenance`), so only genuine `/set config` edits show; step 4c still resolves the calibration. **Knowledge** updated on when instrument files resolve (`/matchruns`, autopilot 4c — *not* `/export script`), preset precedence (`--force` can clobber them), and that `sampleoffset` changes experiment-to-experiment (override with `/set config <id> sampleoffset`). |
| 0.36.1 | 2026-09-01 | Fix: some users hit `ModuleNotFoundError: No module named 'rich'`. The launchers (`eqsanscli`, `eqsanscli-headless`) did `source .venv/bin/activate` then `export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"`, **keeping the caller's PYTHONPATH** — on the analysis nodes that often points at another Python (a python3.9 conda / `~/.local`), so the venv's python3.11 imported rich/textual from there and failed when that env lacked a compatible copy. Launchers now run the venv's python by absolute path and don't inherit the user's Python search paths (`unset PYTHONHOME`, `PYTHONNOUSERSITE=1`, `PYTHONPATH=src` only). Verified by running the real launcher under a hostile `PYTHONPATH`/`PYTHONHOME`. |
| 0.36.0 | 2026-09-01 | New `/display <image.png> [...]` opens existing image files (mask previews, saved plots) in a viewer window — distinct from `/plot`, which renders *data* files. Resolves paths against the cwd and output dir; opens a detached matplotlib window when `DISPLAY` is set (same pattern as an interactive `/plot`), otherwise reports the resolved path (headless/SSH). LLM routes "show me the mask png" / "open X.png" → `/display`. |
| 0.35.0 | 2026-09-01 | `/load ipts` with no number infers the IPTS from the current folder — running eqsanscli from `/SNS/EQSANS/IPTS-39659/shared/` and typing `/load ipts` loads 39659 (regex matches with or without a trailing slash; falls back to usage when the cwd isn't under `/SNS/EQSANS/IPTS-NNNNN/`). LLM routes "load the current ipts" → `/load ipts`. |
| 0.34.0 | 2026-08-31 | Fix: `--like` aligned hint-less config blocks by the table's order (distance-ascending, so `2.5m2.5a` came before `4m10a`), but a script's block index order is physical **low-Q → high-Q** (block 0 → `iq0`, the low-Q profile). It mis-assigned block 1 → 2.5m, block 2 → 4m, so the stitch (which expects `iq1` low-Q first) was backwards. `align()` now fills unhinted blocks from the remaining configs sorted low-Q first (largest λ·L = lowest Qmin), and warns if the final block order still isn't monotonic in Q. Explicit comment/mask hints still win. Fixes the case with no `--adapt` needed. |
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

### 2026-09-01: /reduce names the sample at submission, not on completion (v0.36.5)

Reported: running `/reduce` in parallel mode, "it doesn't show which sample I'm
reducing" — the sample name "appeared after done". Autopilot showed it.

Cause: the TUI `/reduce` worker has two branches. Single-core prints a
`⟳ <sample> (config) → …json` line at the START of each row. The multi-core
(parallel) branch — the default when `/settings multiprocessing > 1` — marked
rows "reducing" silently, printed only "Submitting N jobs to M workers…", and
named samples solely on the completion line inside the `as_completed` loop. So a
lone parallel job sat at "Submitting 1 jobs to 3 workers…" with nothing
identifying it until it finished a minute later.

Fix: the multi-core branch now writes the same `⟳ <sample>` start line for every
row right after submitting (before the executor runs), so each sample appears
immediately; the existing ✓/✗/⊘ completion lines are unchanged. Matches
single-core and autopilot.

TUI-only display change (no test — the reduction worker is a Textual `@work`
thread); the line mirrors the proven single-core one. 294 tests.

**Files changed:** `app.py`, CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-09-01: /matchruns --update respects runs reclassified to ignore (v0.36.4)

Reported: a series of runs had wrong wavelength metadata, so they were
reclassified to `ignore`; the transmission was remeasured. But `/matchruns` kept
using the OLD, ignored transmission.

Cause is the `--update` path (`merge_new_runs`). Plain `/matchruns` rebuilds from
the catalog and `_classify_catalog` drops `ignore`, so it was always correct. But
`--update` — the recommended flow after remeasuring, because it preserves
already-reduced rows — copies existing rows' assignments verbatim and never
re-checked them. So a transmission the user had since marked `ignore` stayed
assigned on the preserved row. Reproduced: reduce a row (trans 200, `done`),
reclass 200 → ignore with new trans 300 present, `--update` → row still on 200.

Fix: after merging, `merge_new_runs` reconciles the preserved rows against the
fresh `ignore` set — a row whose *scattering* run is now ignored is removed, and
any `transmission`/`background`/`empty` pointing at a now-ignored run is
re-matched from the fresh table (blank if none), via `set_field` so a `done` row
becomes `modified` for re-reduction. Both actions warn. New rows (from the fresh
table) already exclude ignored runs, so they are unaffected.

`tests/test_matching.py` (+3): --update re-matches an ignored transmission and
marks the row modified, removes a row whose scattering run is ignored, and leaves
valid assignments untouched. 294 tests.

**Files changed:** `services/matching_service.py`, `tests/test_matching.py`,
CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-09-01: /autopilot --from 9 no longer re-reduces done rows (v0.36.3)

Reported: `/autopilot --from 9` on IPTS-38151 re-reduced all 9 sample rows even
though 8 were `done`. The log was the giveaway — steps 1–5 said "Skipped
(--from 9)" but steps 6, 7, 8 ran, and step 8 logged "Applying absolute scale
factors ✓ 4m2.5a30hz: 0.4145807".

Cause: the standard/calibrate/apply-scale block (steps 6–8) was guarded only by
`continue_mode`, not by `from_step`. So `--from 9` fell into the `elif has_porsil`
branch and re-applied the scale with `/set config <cfg> standardabsolutescale …`.
That call runs `_mark_config_rows_modified`, which flips every `done` row in the
config to `modified`. Step 9 then skips only rows whose status is exactly `done`
— and there were none left — so it reduced all 9. The done-skip logic was fine;
it was being sabotaged one step earlier.

Fix: the "skip 6–8, reuse existing scale" branch now triggers on
`continue_mode or from_step >= 9`, and it only *reports* the current
`standardabsolutescale` — it does not re-run `/set config`, so `done` rows stay
`done`. This matches `--from 9`'s own documented meaning ("skip
standard/calibrate/apply-scale; reduce samples with existing scales"). `--from
6/7/8` still run the whole scale block (unchanged); `--force` still redoes all.

`tests/test_autopilot_tostep.py` (+1): --from 9 with a scale-bearing config and
8 done rows reduces only the one non-done row, and never re-applies the scale
(the stub simulates the modified-marking side effect that the earlier repro
missed). 291 tests.

**Files changed:** `services/autopilot.py`, `tests/test_autopilot_tostep.py`,
CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-09-01: autopilot --from 2, step-4b snapshot, calibration knowledge (v0.36.2)

Three things found while driving real reductions.

**1 — `/autopilot --from 2` was rejected.** The `--from` validation demanded a
populated working table for any `from_step >= 2`, but step 2 *is* match-runs — the
step that builds the table — so `--from 2` refused before it could run. Fixed:
`--from 2` needs only a loaded catalog (step 1 = load is what it skips); the
populated-table requirement now applies to `--from 3+`, which skip matching. Help
text corrected; it wrongly said `--from` always needs a table.

**2 — Step 4b mislabelled machine-physics files as "user-set".** Step 4b
re-applies the parameters you set before autopilot so they win over presets. Its
snapshot kept every value differing from the preset — and a prior `/matchruns`
leaves the resolved dark/flood/flux/offset files in the config, which also differ
from the preset, so they were captured and printed under "user-set parameters per
config". The snapshot now also excludes resolver-owned values (still equal to what
the resolver recorded in `instrument_provenance`), so only genuine `/set config`
edits appear there; step 4c still resolves the calibration. A user override of a
resolved param (e.g. `sampleoffset` differing from the cycle value) is kept.
Extracted as `_user_param_snapshot()` for testing.

**3 — Calibration-procedure knowledge.** `knowledge/instrument-files.md` and the
LLM routing now state when instrument files resolve (`/matchruns`, autopilot 4c —
NOT `/export script`, which emits what's already in the config), preset precedence
(`/apply preset` without `--force` preserves them; `--force` can clobber them →
recover with `/instrument apply --force`), and that `sampleoffset` changes
experiment-to-experiment, overridden with `/set config <id> sampleoffset <mm>`.

`tests/test_autopilot_tostep.py` (+6: --from 2 builds the table / needs catalog,
--from 3 still needs a table, and the snapshot excludes resolver-owned params but
keeps overrides). `tests/test_knowledge.py` still green. 290 tests.

**Files changed:** `services/autopilot.py`, `commands/autopilot.py`,
`services/llm_handler.py`, `knowledge/instrument-files.md`,
`tests/test_autopilot_tostep.py`, CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-09-01: launchers pin the bundled venv — fixes "No module named 'rich'" (v0.36.1)

Some users hit `ModuleNotFoundError: No module named 'rich'` while others didn't.
The venv (`.venv`, python3.11) is self-contained and world-readable and has rich,
so it wasn't a permission or install problem. The launchers were the cause: they
`source .venv/bin/activate` and then `export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"`,
**keeping the caller's PYTHONPATH**. On the SNS analysis nodes a user's PYTHONPATH
(or PYTHONHOME, or `~/.local` user-site) frequently points at ANOTHER Python — a
python3.9 conda env, drtsans/mantid — and PYTHONPATH entries are searched before a
venv's own site-packages, so the python3.11 venv imported rich/textual from the
wrong place and failed when that environment had no compatible copy. Reproduced
directly: with `PYTHONPATH` set to a python3.9 site-packages, the venv python
imported `rich` from `…/python3.9/site-packages/rich`.

Fix: both `eqsanscli` and `eqsanscli-headless` now run the venv's python by
absolute path (no reliance on `activate`) and do not inherit the user's Python
search paths — `unset PYTHONHOME`, `export PYTHONNOUSERSITE=1`, and
`PYTHONPATH="$SCRIPT_DIR/src"` (only our package). drtsans still resolves from the
user's PATH as before (it is a separate subprocess). The `/SNS/EQSANS/shared/
usertools/eqsanscli` entry point is a symlink to this launcher, so it inherits the
fix. Verified by running the real launcher under a hostile PYTHONPATH+PYTHONHOME:
boots and reports v0.36.0, rich loaded from the venv.

**Files changed:** `eqsanscli`, `eqsanscli-headless`, CLAUDE.md,
`src/eqsanscli/__init__.py`.

