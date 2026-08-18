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
- `SKILL.md` and `AGENT_SKILL.md` document the tool for TUI and headless agent use respectively.

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
4. `services/<thing>_service.py` stays one algorithm's home. When a second
   algorithm needs the same primitives (detector geometry, local contrast, cross
   cuts), lift those into their own module rather than importing across services.

---

## Change Log

The **last 5 revisions** are below. Everything older is in
[`docs/CHANGELOG.md`](docs/CHANGELOG.md), which is not loaded into the session —
read it when you need the history of a decision.

When adding an entry: put it here, and move the oldest one out to
`docs/CHANGELOG.md` so this list stays at 5.

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

### 2026-08-18 (v0.24.1): say where the tube-end bands came from

Asked: are the top/bottom bands a threshold or just a default? Both, and the
answer was only in the code: `find_edge_bands` walks the mean along-tube profile
in from each end while it sits **below half the plateau** (`DEFAULT_BAND_DROP`),
then `build_plan` floors the result at 11 pixels (`DEFAULT_MIN_BAND`, the
`MASKED_PIXELS = '1-11,246-256'` convention).

**The floor is what applies in practice.** Measured now on four real runs, the
profile crosses half the plateau at pixel 8-11 — 186621 gives 9/8, 186104 9/8,
186631 10/8, 186636 11/10 — so every one of them ends up at 11/11. The
measurement only takes over on a run whose ends fall off further than usual.

`MaskPlan.how_banded()` now reports which happened, next to the beam radius
derivation added in 0.23.1, and `.params.json` records `bands_measured` and
`band_source`. Reads: *"tube-end bands: response falls below half the plateau by
pixel 9 / 8, raised to the 11-pixel EQSANS convention"*.

**Files changed:** `services/mask_service.py` (`how_banded`, `measured_bottom`,
`measured_top`, `band_source`), `commands/mask.py` (report line, params, help),
`tests/test_mask.py` (+2, 66 total), README, `knowledge/instrument-files.md`.

### 2026-08-18 (v0.24.0): `/mask` flag review, and a shorter help

Asked once the command settled: review the flags, trim what is not needed, and
rewrite the help — useful but not long.

**Trimmed one: `--band-drop`.** It moved the threshold the band-edge measurement
uses, which is never the right tool — `--top` / `--bottom` set the bands directly,
in the units the convention is written in, and the 11-pixel floor is what the rest
of the pipeline assumes. `DEFAULT_BAND_DROP` stays as the internal constant and is
still recorded in `.params.json`.

**Kept, with the reasoning, since two came close:**

- `--beam-scale` and `--beam-pad` overlap — both add margin, one proportional and
  one in y-pixels. Kept both: the pad is in the units the machine-physics mask
  tool uses (v0.15.1), and the scale is the mechanism behind the 1.2 default on
  the shadow path, so removing either would make the printed derivation
  unexplainable.
- `--tube-sigma` has a narrow effect since v0.17.0 (the statistical test only
  applies where counts support it), but the tool itself prints "lower
  --tube-sigma to look harder" when it finds nothing, so it stays.
- `--ipts` is rarely needed since v0.23.0 finds the run by number, but still skips
  the search and disambiguates.

**Help: 110 lines to 65**, reorganised by what people actually reach for —
`--dry-run`, `--leak`, `--tubes`, `--disc` first under *Common*, then the beam
stop, then tube ends, then the two path options. The long physics passages (why
gravity drops the beam, why tube index is not a coordinate, the full worked
comparison of estimators) live in the README and `knowledge/`; the help keeps one
line of each where it changes what you would type.

`test_every_documented_flag_parses` walks every `--flag` in the help text through
the parser, so the two cannot drift apart — it would have caught the `--band-drop`
line left in the README.

**Files changed:** `commands/mask.py` (help rewritten, flag removed),
`tests/test_mask.py` (+2, 64 total), README.

### 2026-08-18 (v0.23.1): say how the beam radius was decided

Asked after a good run on 186621 (`S-banjo 1.3m 1A`, 133.6 M counts, median 2565
per pixel — the brightest run yet): *"do you decide the size of auto-created
center mask by how? ... i think it created slightly larger mask?"*

**Checked, and it is not too large.** That run has no flare, so it takes the
shadow path: r 30.5 x 1.2 + 4.1 mm pad = 40.7 mm. Measuring the transmitted level
in rings about the centre, as a fraction of the level well outside:

| radius | 186621 | 186104 |
|---|---|---|
| edge of the visibly dark disc | 0.30 (30 mm) | 0.15 (24 mm) |
| the mask edge | 0.88 (41 mm) | 1.19 (34 mm) |
| 1.25x the mask edge | 1.16 (51 mm) | 1.09 (43 mm) |

The dark disc is the umbra; the ring outside it is penumbra, where 70% of the beam
is still blocked at 30 mm on 186621. A mask drawn round the dark disc would leave
those pixels in the lowest-Q bins. 186104 lands at 34.2 mm against a hand-made
mask of ~34 mm, which is the one external reference for the no-flare path, and
186636 at 44.0 mm against a stop measured at 90 mm across.

**What changed:** the report now prints the arithmetic behind every radius —
`BeamStop.how_sized()`, plus `raw_radius`, `applied_scale` and `applied_pad`
fields and the same three in `.params.json`. Both paths are covered, and an
explicit `--beam-radius` says so rather than inventing a derivation.

**Files changed:** `services/mask_service.py`, `commands/mask.py`,
`tests/test_mask.py` (+2, 62 total), README, `knowledge/instrument-files.md`.

