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

### 2026-08-19: a documentation site under `docs/` (no version bump)

Asked for a hostable information page: introduction, how to use it, a manual of
every command with examples, a searchable reference, a page for the configuration
parameters and how they reach the exported script, and a step-by-step guide.

**Seven pages, generated.** `python3 docs/generate.py` writes static HTML into
`docs/`, servable by GitHub Pages from the main branch `/docs` folder with no
workflow and no build step. System python3, no dependencies — `docs/md.py` is a
small Markdown renderer because no such library exists on the analysis machines.

**The reference pages are built from the code**, which is the point: commands from
`commands/registry.py` (the list), `SKILL.md` tables (one-liners) and each
module's `_USAGE` (full help); parameters from the `EQVar` mapping in
`script_exporter.py`, `knowledge/configurations.md` (descriptions) and the presets
(values); rules from `services/protocol.py`. Only the introduction, the
step-by-step guide and the parameters preamble are hand-written, under
`docs/pages/`.

**Search** is a prebuilt JSON index (239 entries: commands, parameters, rules,
knowledge topics, headings) with a client-side filter — no CDN, works offline,
`/` focuses it. Rule ids and `/command` mentions auto-link, but only to anchors
that exist, so a mention of an undocumented command renders as plain code rather
than a dead link.

**Found while building it, each fixed at the source rather than in the
generator:** `/calibrate` was missing from `SKILL.md`'s tables (documented only in
prose, so the drift test could not see it); the 26 managed parameters had no
one-line descriptions anywhere, now a table in `knowledge/configurations.md`; and
the front-end commands (`/help`, `/exit`, `/version`, `/list`, `/guide`) were
absent from every reference because they are not in `registry.py`.

`tests/test_docs.py` grows to 9 checks: the generator must run, every page must be
written, every command and parameter must reach the site with a description, and
no internal link may be broken.

**Files changed:** `docs/generate.py`, `docs/collect.py`, `docs/md.py`,
`docs/site.css`, `docs/search.js`, `docs/pages/*.md`, `docs/README.md` (all new),
the seven generated pages, `SKILL.md`, `knowledge/configurations.md`,
`tests/test_docs.py`, README.md, CLAUDE.md.

### 2026-08-18: an algorithm layer, and the protocol made executable (no version bump)

Items 5 and 6 of the structure review.

**5 — `mask_service.py` split three ways**, by AST line spans so nothing was
retyped: `detector.py` (243 lines) holds geometry and image primitives — reshaping
with its ordering self-check, real pixel positions, local contrast, the cross cuts
and valley finding; `run_files.py` (70) holds archive lookup, which was never
mask-specific; `mask_service.py` (1041, from 1304) keeps mask **policy** plus the
Mantid read/write and the preview.

No facade and no re-exports: names have one home, and the ~40 call sites in
`commands/mask.py` and the tests were retargeted. The seam is where a second
algorithm will need it — anything that reads a detector image now builds on
`detector.py` rather than importing from a mask module.

**6 — `services/protocol.py`.** `knowledge/protocol.md` was prose to the code:
nothing parsed it, so "13 unenforced" was a number no build could act on. The
module parses all 48 rules into `Rule` objects and holds validators for the ones
decidable from session state alone — **TBL-04** (background needs its own
transmission), **TBL-06** (one run, one role per configuration), **BKG-01**
(background from the row's own configuration), **BKG-02** (a row is not its own
background), **CFG-01** (qmin < qmax). Those five moved from `unenforced` to
`enforced (services/protocol.py)` in the document. Backlog: 15 → 10, and
`unenforced_rules()` now lists it from code.

`tests/test_protocol.py` (13 checks) keeps the two sides honest in both
directions: a rule with a validator must be marked enforced by this file, and a
rule the document says this file enforces must have a validator. Plus one test per
validator on the violation it describes, and one asserting a raising validator
never breaks its caller.

**Deliberately not wired to a command.** `/review` stays deferred, as asked — this
is the library it will use. Note that `check()` running clean does not mean the
protocol is satisfied, only the mechanical part of it; the remaining ten rules
need a run's metadata, the reduced output, or a judgement.

**Files changed:** `services/detector.py`, `services/run_files.py`,
`services/protocol.py` (all new), `services/mask_service.py`,
`commands/mask.py`, `knowledge/protocol.md`, `tests/test_protocol.py` (new),
`tests/test_mask.py`, `tests/test_knowledge.py`, CLAUDE.md. 194 tests.

### 2026-08-18: one agent document, not two (no version bump — docs and tests)

`SKILL.md` (449 lines, TUI-oriented) and `AGENT_SKILL.md` (698, headless) were
two hand-maintained copies of the same command reference. They had **drifted in
both directions**: `/refresh catalog`, `/reclass`, `/stitch reorder` and
`/set drtsans` existed only in one, `/list iqxqy`, `/session list`, `/settings`
and the shell commands only in the other. Neither was a superset, so neither
could be generated from the other.

**Merged into `SKILL.md`** (816 lines, from 1147): one command reference, one
workflow, both front ends — the TUI and the headless JSON protocol — under *Two
ways to drive it*. `AGENT_SKILL.md` is now a stub pointing at it, kept so old
references land somewhere correct rather than on half a document.

Corrected while merging: the headless copy still called `/apply preset auto`
**"MANDATORY, DO NOT SKIP"**, which has been wrong since v0.10.0 — `/matchruns`
applies the matching preset and then resolves the machine-physics files itself.
That step is now *verify, do not repeat*, and warns that `--force` overwrites user
edits.

**12 registered commands were documented nowhere** (`/table`, `/move`,
`/list tables`, `/note`, `/compare`, `/models`, `/tail` and the write-shell ones).
The first six gained sections; the write-capable shell commands are called out as
deliberately outside the agent workflow.

**`tests/test_docs.py` (new, 5 checks)** makes the drift a test failure: every
command in `registry.py` must appear in `SKILL.md`, the stub must stay a stub,
both front ends must be covered, and the preset-is-mandatory claim must not come
back.

`AGENT.md` — the original build prompt, which still describes `/show <ipts>` for
what is now `/load ipts` — was left alone: it is gitignored, so it is not part of
the repository's documentation surface.

**Files changed:** SKILL.md (merged), AGENT_SKILL.md (stub), `tests/test_docs.py`
(new), CLAUDE.md, README.md.

### 2026-08-18: structure for what comes next (no version bump — docs and tests)

Asked whether the knowledge and instructions are structured well enough to take
new algorithms. Three things fixed, in the order they were hurting.

**1. CLAUDE.md was 1798 lines, 1678 of them change log** (43 entries), loaded into
every session, with the 120 lines that actually describe the project buried on
top. History moved to `docs/CHANGELOG.md`, which nothing loads; the last five
entries stay here. Adding an entry now means moving the oldest one out.

**2. The Testing section claimed "no formal test suite"** while six suites and 176
checks existed. It now names each suite, gives one command
(`python3 -m pytest -q tests/`), and states the two rules that keep the suites
honest: never pin a machine-physics value to a literal, and do pin documented
constants.

That was not hypothetical — `test_live_current_cycle_resolves_to_2026b` was
**failing** when the whole directory ran, because machine physics re-reduced AgBe
that afternoon and `detoffset` moved 66.763 → 66.714. A test hardcoding a cycle
value fails on the day the resolver correctly picks up new calibration. It now
asserts that what resolves equals what the cycle folder currently holds, within a
plausibility range, and that the source is not a `.OLD` backup.

**3. `knowledge/protocol.md` gained the `MSK` section** — 11 rules for the most
developed algorithm in the repo, which until now answered to no authority:
uniformly illuminated run and configuration in the filename (MSK-01), refuse
rather than guess (MSK-02), size from the horizontal cut only (MSK-03), reach past
the umbra (MSK-04), band floor (MSK-05), leaks reported and masked below only
(MSK-06), tube judgement (MSK-07), read-back verification (MSK-08), millimetres
not indices (MSK-09), plus MSK-10/11 `unenforced` as backlog. Three new
code-agreement tests in `test_knowledge.py` check the band floor, the refusal and
the below-only leak rule against the code.

Also added to CLAUDE.md: the rule-prefix list, and an **Adding a new algorithm**
section — pure numpy in `services/`, write the protocol rule first, report the
derivation not just the answer, measure against real runs before believing it.

**Files changed:** CLAUDE.md (1798 → 328 lines), `docs/CHANGELOG.md` (new),
`knowledge/protocol.md` (+11 rules), `tests/test_knowledge.py` (+3, 23),
`tests/test_instrument_files.py` (live test de-hardcoded).

### 2026-08-18: every threshold documented (no version bump — docs only)

Follow-up to the band question: *"is measured threshold 0.8? or 0.85??"* — no,
**0.5**. The 0.80/0.85 were response *levels* at pixels 11 and 13, printed in the
same table as the threshold, which is exactly how documentation causes confusion.

**README gains a *What sets each size* section**: one row per measured quantity —
beam stop with and without flare, beam centre, tube-end bands, dead/hot/marginal
tubes, leak discs — giving what it is measured from, the number, the bound applied
after, and the flag that overrides it. Below it, a table of the named constants
with their values, and the reason for the two that are not self-explanatory (the
1.2 growth on the no-flare path, the 11-pixel floor).

The band item now shows the walk itself on run 186621 — 0.29 at pixel 8, 0.52 at
9, 0.72, 0.80, 0.83, 0.85 — so the threshold and the response levels cannot be
mistaken for each other again, and says why the band stops where response *starts*
rather than where it is complete: the residual 15-20% is the sensitivity map's
job.

`test_documented_thresholds` asserts all twelve constants against the table.
Writing it caught the table naming `FLARE_CONTRAST`, which v0.22.0 deleted when
cross cuts replaced the ring fit.

Also fixed: a `knowledge/instrument-files.md` edit in v0.24.1 silently did nothing
because its target text spanned a line break, and the script did not assert. The
paragraph is now a three-row table of what is measured and what bounds it.

**Files changed:** README.md, `knowledge/instrument-files.md`, SKILL.md,
AGENT_SKILL.md, `tests/test_mask.py` (+1, 67 total).

