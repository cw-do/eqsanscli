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

No formal test suite. Quick verification via:
```bash
python -c "import sys; sys.path.insert(0, 'src'); from eqsanscli.<module> import <thing>; ..."
```

The `.venv` has textual/rich but the system Python may not — use `sys.path.insert(0, 'src')` for import-only checks.

---

## Change Log

### 2026-08-17 (v0.13.0): Knowledge base — one authority, no contradictions

Phase 0 of the agentic-reduction plan: before anything reviews a reduction, the
rules it reviews against have to exist and be coherent.

**What was wrong.** Six places described how to drive the tool and one described
the physics — `preset_configs/knowledge.md` (20 KB, last touched April), injected
into *every* natural-language call. It had drifted into contradicting both itself
and the code:

- `MP_DIR = ".../2025B_mp/"` with hardcoded `FLOOD_4m` / `DARK_FILE` / `FLUX_FILE`
  constants, plus "as of 2026-3-3 we are at 2026A but haven't prepared 2026A_mp" —
  three cycles stale, and superseded by the v0.11.0 run-aware resolver.
- masks "found in `IPTS-{ipts}/shared/` or current folder, else use
  `eqsanstools/mask_4m.nxs` temporarily" — the fallback removed in v0.11.0.
- line 142 said `--sample` matching is exact-unless-wildcard (correct); line 193
  said case-insensitive substring (wrong) — in the same file.
- "`/assign bkg` gives the background sample the empty beam as its background" —
  changed in 2026-06-09 to *no* background.
- ~200 lines of natural-language→command examples duplicating
  `_SYSTEM_PROMPT` (27.6 KB), so today's routing edits landed in only one copy.

**New structure.** `knowledge/`, one file per decision domain, each with a
`topic` / `summary` / `load` / `updated` header:

- `protocol.md` — **the authority.** Numbered rules (`CAT-`, `EMP-`, `TBL-`,
  `BKG-`, `CAL-`, `CFG-`, `SCL-`, `STC-`) each with a severity
  (blocking/warning/info) and an enforcement status (enforced + the file that
  does it / advisory / unenforced). The `unenforced` set is the backlog for the
  `/review` validators; three `TBD` numbers are flagged for the instrument
  scientist.
- `instrument-files.md`, `configurations.md`, `background-selection.md`,
  `absolute-scale.md`, `stitching.md`, `troubleshooting.md` — physics and
  rationale, carried over from the old file with the stale parts corrected and
  filenames demoted to cycle-labelled examples.
- `README.md` — the editing contract: one fact one home; no command reference
  here; no hardcoded cycle paths; rule ids are permanent; numbers need provenance
  or `TBD`.

**`services/knowledge.py`** replaces `_load_knowledge`'s single-file read.
Topic-aware: only `protocol.md` is `load: always`, so a natural-language call now
carries 9.5 KB of knowledge instead of 20 KB, and `_llm_suggest_config` asks for
`["configurations", "instrument-files"]`. Reads fresh from disk (edits apply
without restart), caches parsed headers on mtime, and warns once if a leftover
`preset_configs/knowledge.md` is found rather than silently ignoring it.

**Rules kept out of the deletion:** two routing rules existed *only* in the old
file and moved into `_SYSTEM_PROMPT` — "show me X" means `/show table --sample`
and never `/remove`, and the configuration-matching rule for catalog run lookups.

**`tests/test_knowledge.py`** (20 checks) enforces the editing contract
mechanically: headers complete, topics unique, exactly one `always` doc, rule ids
unique, every rule declaring severity + enforcement, rule cross-references
resolving, files named as enforcing a rule existing, and regression guards for
each specific drift above (no `MP_DIR =`, no concrete `/SNS/EQSANS/IPTS-<n>` path,
no "case-insensitive substring", no "empty beam as its background", no
command-reference section). Two checks assert the docs still agree with the code
on flood-distance mapping and the mandatory empty beam.

### 2026-08-17 (v0.12.0): Reduction preflight — empty beam is mandatory

**Question that started it:** does anything check that the working table has the
must-have runs before reducing? Answer at the time: autopilot yes, `/reduce` no.

- `/autopilot` Step 3 listed rows missing an empty beam, asked the LLM to explain,
  aborted if *no* row had one, else prompted "proceed without those N rows?" and
  dropped them. **But** `--from 4` or higher skipped Step 3 entirely, and in
  headless mode (no `prompt_user`) it just aborted.
- `/reduce` validated only "table non-empty" and "selection resolves". A row with
  a blank `empty_beam` went straight to drtsans with `beamCenter.runNumber = ""`
  *and* `emptyTransmission.runNumber = ""` (json_builder sets both from the same
  field), so the user learned about it as a per-row `✗` with whatever error text
  `_summarize_error` scraped out of the `.err` file.

**What is mandatory vs advisory.** Blocking: empty beam (it supplies the beam
centre — there is no fallback) and a scattering run. Advisory: transmission
(drtsans accepts a value instead of a run) and background (a background-cell row
such as banjo deliberately has none — see `matching_service.assign_background`),
plus a non-positive/non-numeric thickness.

**`services/reduction_service.py`** gains `blocking_problems`,
`advisory_problems`, `preflight` and `format_preflight`. The failure text names
the rows and configurations and then the actual fixes, in the order most likely
to be right — `/show catalog` to find the `EmpT` run, `/reclass <run> empty` +
`/matchruns` when the run exists but was misclassified (the common cause), or
`/set --config <id> emp <run>`.

**`/reduce`** refuses before starting when any selected row is blocked, and takes
`--skip-missing` (reduce the valid rows, skip the rest) or `--force` (hand them
to drtsans anyway). Flags are stripped before selection parsing, so
`/reduce --sample Good --force` and `/reduce --new --skip-missing` work. Advisory
problems print a warning and proceed.

**Autopilot:** the `--from 4+` path now runs the same preflight and refuses when
*no* row can reduce; `_reduce_phase` skips blocked rows with a `⊘` line rather
than handing them over. That is autopilot-only, so it never fights `/reduce --force`.

**Tests:** `tests/test_reduce_preflight.py` (new, 16 checks) covers the
classification, all `/reduce` modes, flag/selection interaction, and a stubbed
`_reduce_phase` proving unreducible rows never reach `reduce_row`.

### 2026-08-17 (v0.11.0): Masks resolved per configuration, never from another IPTS

**Problem:** reducing IPTS-38773 pulled a mask out of *another* experiment's
shared folder (`/SNS/EQSANS/IPTS-36548/shared/mask_4m2.nxs` and friends, baked
into every preset). Those folders are frequently unreadable to other users, so
the reduction fails on permissions — and even when readable, a mask from someone
else's experiment is the wrong mask. Autopilot's preset-less branch had the same
bug in code: it tried `IPTS-<current>/shared/mask_4m.nxs`, then cwd, then a
hardcoded `eqsanstools/mask_4m.nxs`.

**Model:** a mask belongs to an *experiment*, not to an instrument
configuration, so it does not belong in a preset at all. `maskfilename` becomes
the 7th managed param of `services/instrument_files.py` (so it inherits the
provenance rules: preset-derived values are replaced, `/set config` values are
kept). Search order, first match wins:

1. the folder eqsanscli was started in — any `mask*.nxs`
2. `/SNS/EQSANS/IPTS-<current>/shared/` — this experiment's own folder
3. `<cycle>_mp/masks/*mask.nxs` — the cycle's default (only 2026B has one today:
   `EQSANS_186104_mask.nxs`)

**Matching within a folder** (`_parse_mask_tokens` + `pick_mask`): distance must
agree, a matching wavelength is preferred, `_FS`/`30hz` breaks ties for
frame-skipping. `2p5`/`2o5` both read as 2.5. A mask naming a *different*
distance or wavelength is excluded outright rather than borrowed; a token-less
mask is a generic fallback. Verified against every real naming style found on
disk — `mask_4m.nxs`, `mask_4m2.nxs`, `mask_8m3mm.nxs` (8 m, not 3 m),
`mask_9m.nxs`, `mask_2o5m.nxs`, `maskWS4m10A.nxs`, `maskWS4m2p5A_FS.nxs`,
`EQSANS_186104_mask.nxs`. On IPTS-38773 this maps `4m10a → maskWS4m10A.nxs` and
`4m2.5a → maskWS4m2p5A_FS.nxs` with no user input.

**Visibility (requested):** `/matchruns` and autopilot Step 4c print a *Masks per
configuration* block naming the file and where it came from. When nothing is
found, the warning lists every folder searched and gives the exact command to
fix it — `/set config <id> maskfilename <file>`.

**Presets cleaned:** `maskFileName` set to null in all six, and the leftover
foreign-IPTS `outputDir`/`dataDirectories` values normalised to `./output/`.
A test now asserts no preset contains `/SNS/EQSANS/IPTS-` at all.

**Files:** `services/instrument_files.py` (MaskFile, `_parse_mask_tokens`,
`local_masks`, `cycle_masks`, `pick_mask`, `resolve_mask`, mask branch in
`resolve_for_run`), `commands/instrument.py` (`format_mask_note`),
`commands/matching.py`, `services/autopilot.py` (old mask search removed),
`services/llm_handler.py`, all six `preset_configs/conf_*.json`,
`tests/test_instrument_files.py` (+7 mask checks, 39 total), README/SKILL/AGENT_SKILL.

**Next:** a skill for *creating* masks on request (not in this revision).

### 2026-08-17 (v0.10.1): Compound commands silently ignored via natural language

**Reported:** "make reduction script for me" (before any working table existed)
printed `/export script` and then nothing — no result, no error. Typing
`/export script` directly *did* report "Working table is empty."

**Cause:** `CommandRouter._is_valid_command` checked only the **first word**
against the handler registry, while `_dispatch_command` resolves compound
two-word registrations. `export script` and `apply preset` are registered as
compounds and neither `export` nor `apply` exists as a bare handler, so
`_is_valid_command("/export script")` was False → `has_commands` was False →
`_dispatch_natural_language` treated the LLM's output as **chat prose**, printed
it back verbatim, and executed nothing. Two code paths, only one compound-aware.
`/apply preset auto` was silently broken the same way ("apply the presets" via NL
did nothing). Every other command happened to work because its first word is
also registered bare (`show`, `set`, `list`, `refresh`, …).

**Fix:** `_is_valid_command` now also accepts the two-word compound form,
mirroring `_dispatch_command`.

**Two follow-ons so the failure mode can't recur quietly:**

1. `commands/export.py:_nothing_to_export()` — "Working table is empty. Use
   /matchruns first." was true but wrong-footed when no catalog was loaded
   either (`/matchruns` alone cannot help then). Now distinguishes no-catalog
   (→ `/load ipts`), catalog-but-no-table (→ `/matchruns`), and rows-in-another-
   table (→ `/table <name>`), and points at `/autopilot` as the one-shot path.
2. `services/llm_handler.py` — `_build_context` said *nothing* when the table was
   empty or the catalog missing, so the model could not distinguish "empty" from
   "not mentioned" and emitted commands that could only fail. It now states
   `Table 'x': EMPTY` / `Catalog: NOT LOADED` explicitly (plus which other tables
   have rows), and the system prompt has a PREREQUISITES section: chain the
   missing step first (`/matchruns` → `/export script`), never chain `/matchruns`
   when the table already has rows (it rebuilds and resets status), and never
   guess an IPTS number — ask instead.

**Tests:** `tests/test_router_dispatch.py` (new, 11 checks) covers compound
validity, alias validity, rejection of unknown commands, end-to-end NL dispatch
of a compound command with the LLM stubbed, prose pass-through, all three
`/export script` guidance branches, and the new context lines.

### 2026-08-17 (v0.10.0): `/set --config` + classify-vs-assign routing

*(v0.10.0 ships this and the two entries below: per-row config overrides +
command registry, and machine-physics instrument resolution.)*

**Reported from a real session on IPTS-38773.** The user said "run 186517 and
186518 are the empty beam for 4m10a and 4m2.5a configuration, respectively" and
got `/set --sample * emp 186517` → *"No rows with sample name containing '*'"*.
Three separate defects:

1. **The message blamed the pattern.** `*` is a valid wildcard
   (`sample_matches` → `fnmatch`, matches every row); the real cause was an
   empty working table. New `_no_match_message()` separates "table is empty —
   run /matchruns" from "pattern matched nothing", and lists the sample names or
   configs that do exist.
2. **No per-config selector existed**, so no correct command was available for
   that sentence. Added **`/set --config <id> <field> <value>`** — sets the field
   on every row in one configuration, matching either the row's parameter config
   or its `physical_configuration`, so `4m10a` still selects rows pointed at a
   clone like `4m10a_v2`. The `--sample` and `--config` branches now share one
   implementation. (Even as an assignment the generated command was wrong:
   `--sample *` would put 186517 on *every* row and drop 186518.)
3. **The intent was classification, not assignment.** "run X *is* the empty
   beam" → `/reclass X empty`; `/matchruns` then pairs each run to its configs
   from the ONCat distance/wavelength, so "respectively" needs no run→config
   mapping. `llm_handler.py` now documents the classify-vs-assign split,
   defaults to `/reclass` when a sentence declares what a run *is*, and notes
   that `--sample` matching is exact unless `*` is used.

Also documented: `/matchruns` rebuilds (status resets) while `--update` does
*not* back-fill empty/bkg on existing rows — that case is what `/set --config`
is for.

### 2026-08-17 (v0.10.0): Run-aware instrument calibration files from machine physics

**Problem:** dark current, sensitivity (flood), beam flux and the AgBe-derived
`detectoroffset` / `scalecomponents.detector1` / `sampleoffset` are **cycle**
properties, but they were stored in `preset_configs/*.json`, which are keyed by
**instrument configuration**. Every cycle the paths went stale by hand-editing.
At the time of this change all presets pinned `2026A_mp` files and 2026A's
`detoffset = 77.244` / `scalecomp = [1.003571, 1.052902, 1]` while 2026B had
been published with `66.763` / `[1.004251, 1.057915, 1]`; one preset
(`conf_2.5m_2.5a_60hz_inc.json`) pointed at the **4 m** flood from **2025B** —
wrong distance *and* two cycles stale. Autopilot's `_discover_cycle_files` only
ran when *no* preset matched, always took the newest cycle folder, and ignored
run numbers entirely.

**Where the data lives.** `/SNS/EQSANS/shared/NeXusFiles/EQSANS/<year><A|B>_mp/`
per cycle: `EQSANS_<run>.nxs.h5` (dark), `Sensitivity_patched_<variant>_<tag>_<run>.nxs`
(flood, tag ∈ `1o3m`/`2o5m`/`4m`), `bl6_flux_<cycle>_<month>_rebinned.txt`, and
`agbe_calibration/**/checkpoint.json` + `calibration_report.txt` (AgBe).

**Folder, not web page.** The machine-physics summary page
(https://cw-do.github.io/eqsans_mp/) is *generated from* these folders by
`<mp_root>/doc/generate.py` → `doc/data.js` → GitHub Pages. It is a derived view
that only refreshes when someone republishes, so reading it would add a network
dependency and a publish lag to something already on the mounted share — and
reduction needs filesystem paths anyway. `services/instrument_files.py`
deliberately mirrors `doc/generate.py`'s naming rules; **if that generator's
rules change, change these too.**

**New `services/instrument_files.py`** (stdlib only, no drtsans/mantid):

- `scan_cycles()` — every `<year><A|B>_mp` folder → `Cycle` records (darks,
  sensitivities with distance/run/variant, flux, lazily-parsed AgBe). Cached on
  the mtimes of the root and each cycle folder, so a newly dropped file
  invalidates it by itself. 28 cycles scan in ~30 ms cold, ~0.5 ms warm.
- `resolve_for_run(run, distance)` — **cycle-coherent** selection: newest cycle
  whose *anchor run* (lowest dark/flood run in the folder) ≤ the data run, then
  the whole set from that cycle. Anchor runs are strictly increasing across all
  28 cycles (2011B:5702 → 2026B:186198, verified), so run order and cycle order
  agree. A data run can land between a cycle's dark and its floods (e.g. 186199
  with floods 186200-186202); taking the cycle as a unit avoids pairing this
  cycle's dark with last cycle's floods, and the case is recorded as a note.
- `flood_distance_for()` — clamp into the available range then nearest, ties to
  the larger: 1.3 m → `1o3m`, 2.0 m → `2o5m`, 4 m *and anything longer* → `4m`.
- Within a cycle: prefer `thinPMMA`, then an undecorated tag (`4m` over
  `4mSM`), then the highest run. 2025B holds both thinPMMA and 5mmPMMA with
  5mmPMMA *higher-numbered*, so a purely run-driven pick would silently switch
  variants; 2022A holds four flood generations, so intra-cycle run order matters.
- Fallbacks are bounded on purpose: flux never reaches back more than one cycle
  (otherwise a 2024 run picks up `flux_spectrum_2013B.txt`), and AgBe values are
  never invented for runs before 2026A. In both cases the existing value stays
  and the reason lands in `Resolution.missing`.
- `classify_param()` — the single decision function (`write` / `unchanged` /
  `keep_user`) shared by `apply_resolution()` and `/instrument show`, so the
  preview cannot disagree with what apply does.

**Layering** — now four tiers:

```
drtsans template defaults  <  JSON preset  <  resolved machine-physics files  <  explicit /set config
```

`SessionState.instrument_provenance[cfg][param]` records what the resolver
wrote. A param is (re)written when absent, equal to the resolved value, equal to
what the resolver wrote last time, or still equal to the JSON preset's value —
anything else is a user edit and is kept and reported. New session fields
`auto_instrument_files` (default True) and `instrument_cycle_pin` persist too.

**Where it runs:** `commands/matching.py` after the preset auto-apply (both
`/matchruns` and `--update`), keyed on each config's **lowest** run with a
warning when a config's runs straddle a cycle boundary; autopilot **Step 4c**
(after 4b, so user snapshots still win) — its "Effective configuration" summary
now also lists flux and the three calibration values. `/show config` marks
resolver-owned values `mp:<cycle>`.

**New `/instrument` command** (`commands/instrument.py`): `show`, `list [run]`,
`apply [--force] [--rescan]`, `pin <cycle>`, `unpin`, `off`/`on`, `check`.

**Removed:** `autopilot._discover_cycle_files` and `_MP_BASE` (superseded —
Step 4c covers every config, not just preset-less ones).

**Presets keep these six params** as the offline fallback for `/instrument off`;
they are no longer authoritative. `conf_2.5m_2.5a_60hz_inc.json`'s wrong-distance
flood was corrected to the 2.5 m file.

**Files changed:** `services/instrument_files.py` (new), `commands/instrument.py`
(new), `tests/test_instrument_files.py` (new, 31 checks over a synthetic tree +
the live share), `models/session_state.py`, `commands/matching.py`,
`commands/config.py`, `commands/registry.py`, `services/autopilot.py`,
`services/llm_handler.py`, `app.py`, `preset_configs/conf_2.5m_2.5a_60hz_inc.json`,
README.md, SKILL.md, AGENT_SKILL.md.

**Open item:** 2026B's own README notes its files were deliberately *not*
published to `/SNS/EQSANS/shared/instrument_configuration/` ("publishing is a
separate, deliberate step"). Reading the cycle folder directly means eqsanscli
picks up new calibration the moment it lands. If a publish gate is wanted, the
cleanest signal is a per-cycle marker file the resolver requires.

### 2026-08-17 (v0.10.0): Config-override hardening + single command registry

Follow-up to the 2026-06-24 `/config` work below. That feature let a row point at
a cloned config, but the clone label then flowed into places that expect a
*physics* config ID. Six fixes:

**1. `models/config_id.py` — `base_config_id()` / `is_derived_config_id()`.**
`base_config_id("4m10a_v2") → "4m10a"` (searches the normalized name, returns the
canonical ID, `""` when absent). `is_derived_config_id()` distinguishes a clone
label from a bare config ID. `parse_config_id()` now falls back to the base, so
clone names no longer parse as `(0.0, 0.0, 60)`.

**2. Overrides never affect file naming.** New
`WorkingTableRow.output_stem` = `<sample>_<physical_configuration>`, used by
`reduction_service.reduce_row`, `app.py`'s reduce worker, autopilot's
calibration lookup, `merge_service.build_stitch_table` and
`commands/stitch.py`. **This was a real bug:** with a clone-named file
(`SampA_4m10a_v2_Iq.dat`), `merge_service._scan_output_dir` splits on the last
underscore and would read sample=`SampA_4m10a`, config=`v2`. Stitch grouping
tuples and `script_exporter`'s emitted `eq._filename` use the physical config for
the same reason. **Rule: parameters follow `row.configuration`; filenames and
stitch grouping follow `row.physical_configuration`.**

**3. `/config clone` naming rule.** `<dst>` must contain `<src>`'s physics ID
(`4m10a` → `4m10a_v2` / `4m10a-mask2` / `porsil_4m10a`); `mask2` is rejected with
an explanation. This is what makes the base recoverable from the name alone — no
extra session field to persist.

**4. `/config clone` produces a faithful copy.** It previously kept only keys
present in the source's JSON preset or `__all__`, so cloning a config with no
matching preset produced a near-empty clone that silently fell back to drtsans
defaults. It now copies every key whose effective value differs from the
drtsans-template default — the minimal set guaranteeing
`get_config(dst) == get_config(src)` at clone time.

**5. Physics heuristics resolve clones.** `config_manager._load_matching_preset`,
`autopilot._find_closest_preset`, `commands/preset.py`'s `/apply preset auto`,
`llm_handler._parse_config_id` (hence `_llm_suggest_config` and
`_discover_cycle_files`) and `merge_service._default_target_index` all resolve
the base first, so a clone matches the same preset as its source instead of
`find_closest_preset`'s loose "same distance" tier.

**6. Autopilot no longer deletes clones.** Step 4b's orphan cleanup removed every
`state.configurations` key absent from `table.configurations` — which silently
discarded a clone awaiting `/set <row> cfg`, or one whose rows were filtered out
by `--samples`/`--exclude`/`--config`. It now skips derived (clone) names and
reports what it dropped.

**Also:** `/set <row> cfg <name>` rejects a target whose physics differs from the
row's own (`4m10a` row ✗ `8m10a` params) — `_validate_config_target` takes the
rows and names the offending one. `/config list` annotates clones with
`(clone of 4m10a)`. Remaining `/set <row> config` hints changed to the canonical
`cfg`.

**`commands/registry.py` (new) — one registration list.** `register_all(router)`
registers all 50 shared commands + 4 aliases; `app.py` and `headless.py` call it
and then add only their own front-end handlers (`/help`, `/exit`, `/version`,
`/list`, and `/guide` in the TUI — see `ENTRY_POINT_COMMANDS`). Both files' long
handler-import blocks are gone. **Adding a command is now two steps, not three:
`registry.py`, then the `llm_handler.py` reference.**

**`tests/test_config_clone.py` (new)** — 20 checks over the clone/override flow,
naming, preset resolution, session round-trip and entry-point registration
parity. Runs standalone (`python tests/test_config_clone.py`) since pytest isn't
installed in `.venv`; pytest-compatible if it is.

**Files changed:** `models/config_id.py`, `models/working_table.py`,
`commands/config.py`, `commands/matching.py`, `commands/preset.py`,
`commands/stitch.py`, `commands/registry.py` (new), `services/config_manager.py`,
`services/autopilot.py`, `services/merge_service.py`,
`services/reduction_service.py`, `services/script_exporter.py`,
`services/llm_handler.py`, `app.py`, `headless.py`, `tests/test_config_clone.py`
(new), README.md, SKILL.md, AGENT_SKILL.md.

### 2026-06-24: `/config` namespace + per-row config override

**Problem:** No way to give two rows at the same physical config different reduction
params (e.g. a different mask for one sample). `state.configurations` was keyed by
the physics-derived ID (`4m10a`), so any per-config setting hit ALL rows at that config.
Cloning a config wasn't possible, and rows had no way to point at an alternative.

**Solution:** Two changes that work together.

1. **`WorkingTableRow.configuration_override: str = ""`** — new stored field.
   The `configuration` property returns the override when set, else the
   physics-derived ID. New `physical_configuration` property always returns
   the derived ID. The override is in `_REDUCTION_FIELDS` so changing it on
   a done row flips status to `modified`. `from_dict` filters unknown keys
   so older session files (no `configuration_override`) still load.

2. **`/config` sub-router**:
   - `/config list` — configs in the table + stored extras (clones not yet assigned)
   - `/config clone <src> <dst>` — copy params from `<src>` to a new `<dst>`.
     Rejects names colliding with `__all__`, existing stored configs, or
     physical configs already in the table. If `<src>` is a physical config
     (not in `state.configurations`), the clone snapshots preset + `__all__`
     defaults so it's self-contained.
   - `/config rows <id>` — list rows referencing `<id>`
   - Bare `/config` falls through to `/config list`.

3. **`/set <row> cfg <name>` + `/set --sample <name> cfg <name>`** —
   assigns `configuration_override`. Validates the target exists as a stored
   config or a physical config in the table; rejects unknown names with the
   available list. `/set <row> cfg none` clears the override.
   `cfg` is the canonical row-field name (chosen over `config` to avoid
   visual collision with the `/set config <id> <param> <val>` sub-command);
   `config` and `configuration` remain accepted as aliases.

**Typical workflow:**
```
/config clone 4m10a 4m10a_v2                  # create the variant
/set --sample MySample cfg 4m10a_v2           # point a subset of rows at it
/set config 4m10a_v2 maskfilename mask_v2.nxs # diverge from 4m10a
```

**Backwards compat preserved:**
- All ~30 call sites that read `row.configuration` (autopilot, reduction,
  stitch, merge, config_manager lookups) pick up the override transparently
  via the property — no other code changes needed.
- `match_runs`/`merge_new_runs` produce rows with blank overrides, so
  `/matchruns` still works exactly as before unless the user opts in.
- Old session files without the new field deserialize cleanly.

**Files changed:**
- `models/working_table.py` — `configuration_override` field, `configuration`
  property, `physical_configuration` helper, `_REDUCTION_FIELDS`,
  filtered `from_dict`
- `commands/config.py` — `handle_config` dispatcher, `handle_config_clone`,
  `handle_config_rows`, `_dedup_config_names`, extended `handle_list_configs`
  to show stored extras
- `commands/matching.py` — `config`/`configuration` in `SETTABLE_FIELDS`,
  `_validate_config_target`, clear/set handling in both per-row and
  `--sample` branches
- `app.py`, `headless.py` — register `/config`
- `services/llm_handler.py` — document new commands + intent examples

### 2026-06-17: Remove CONFIG_PRESETS Python dict — JSON presets are the single source of truth

**Problem:** Two parallel preset systems existed and silently overrode each other:

1. **`src/eqsanscli/config/presets.py`** — a Python `CONFIG_PRESETS` dict baked into
   `services/config_manager.py:get_config()` as a middle layer between drtsans
   defaults and user overrides. Active on every `/show config`, `/reduce`, etc.,
   even if the user never ran `/apply preset`.
2. **`preset_configs/*.json`** — JSON files loaded lazily by `/apply preset`,
   which writes flattened `configuration` keys into `state.configurations[cfg]`.

Most JSON presets had `"Qmin": null, "Qmax": null`, while the Python preset for
`4m10a` had `qmin: 0.003, qmax: 0.05`. Applying the JSON preset would write
`user_configs['4m10a']['qmin'] = None`, which then shadowed the Python preset's
`0.003` — silently *removing* values the user had via the prior layer. For
`8m10a` (no Python preset entry), `qmin`/`qmax` simply never landed because the
JSON had nulls and there was nowhere else for them to come from.

**Solution:** JSON files in `preset_configs/` become the single source of truth.

1. **Deleted `src/eqsanscli/config/presets.py`** entirely. `CONFIG_PRESETS`,
   `get_preset()`, `list_presets()`, `MP_DIR_PATTERN`, `MP_DIRS` — all dead.
2. **`/matchruns` auto-applies the matching JSON preset** for each new config.
   `commands/matching.py:handle_matchruns` calls
   `_load_matching_preset(cfg)` (via `services/preset_service.find_closest_preset`
   + `load_preset`) and merges non-None values into `state.configurations[cfg]`
   with `setdefault` semantics — never overwrites a user value or a
   `/set config all` default. Reports per-config preset apply + missing presets
   in the command output.
3. **`/apply preset` skips None values** in both the `auto` and explicit
   branches (`commands/preset.py`). JSON `null` no longer clobbers anything,
   even with `--force`.
4. **`services/config_manager.py` refactored:**
   - Removed `_find_preset()` (the Python-dict lookup).
   - Removed `CONFIG_PRESETS` import.
   - `get_config()` is now two layers: drtsans-template defaults + user
     overrides. No middle preset tier.
   - `list_config_params()` source attribution now compares each user-set value
     against the matching JSON preset (loaded via new `_load_matching_preset()`
     helper). Match → `source="preset"`; differ → `source="user"`; absent →
     `source="default"`. Keeps the `*`/blank/`d` annotation in `/show config`
     meaningful after auto-apply.

5. **Autopilot snapshot filtered:** `services/autopilot.py` snapshot at the top
   of `run_autopilot_sync` now filters out values that match the JSON preset,
   so the "User-set parameters per config" summary in Step 4b actually shows
   what the user explicitly set — not preset-defaulted values from a prior
   `/matchruns`. `__all__` values are still always considered user intent.

**Files changed:**
- DELETED `src/eqsanscli/config/presets.py`
- `src/eqsanscli/services/config_manager.py` — removed `_find_preset`/import,
  added `_load_matching_preset`, simplified `get_config`, rewrote
  `list_config_params` source logic
- `src/eqsanscli/commands/matching.py` — auto-apply preset loop in
  `handle_matchruns`; updated summary message
- `src/eqsanscli/commands/preset.py` — skip `None`-valued keys in both
  apply branches
- `src/eqsanscli/services/autopilot.py` — filter pre-autopilot snapshot
  against matching preset

**Behavioral implications:**
- Configs that previously got values ONLY from the Python `CONFIG_PRESETS`
  (e.g. `9m8a`, `1.3m4a`, `1.3m1a`) will now fall through to drtsans defaults
  unless a matching JSON preset is added to `preset_configs/`. If those configs
  matter, create the JSON files.
- Configs covered by a JSON preset (`4m10a`, `4m2.5a`, `2.5m2.5a`, `8m10a`,
  `8m12a`) get all non-null preset values automatically at `/matchruns` time.
- `/show config <id>` immediately after `/matchruns` now shows real values
  (with `src=preset` marker) instead of blank `—` for things the preset set.
- Existing `state.configurations` saved in session files keep working — the
  values are already there, just attributed differently in `/show config`.

### 2026-04-06: Run classification system (`run_class` column)

**Problem:** Run classification (scattering vs transmission vs background vs empty beam) was done by parsing title prefixes (S-, T-) every time `/matchruns` was called. If ONCat titles had typos or were mislabeled (e.g., `T-sample` when it should be `S-sample`), runs were misclassified and excluded from the reduction table with no way to fix it.

**Solution:** Moved classification upfront to catalog load time, stored as a `run_class` column in catalog data. Added `/reclass` command to override.

**Files changed:**

1. `services/matching_service.py`
   - Extracted `classify_title(title) -> str` — public function, classifies based on title
   - Added `add_run_class_column(df)` — stamps `run_class` on catalog DataFrame at load time
   - Added `resolve_run_class(name)` — maps user aliases (scatt, trans, bkg, etc.) to canonical values
   - Added `RUN_CLASS_SHORT` dict — display labels (S, T, BkgS, BkgT, EmpT, EmpS)
   - Added `_classify_run_from_row(row)` — builds ClassifiedRun from `run_class` column
   - Changed `_classify_catalog()` to read `run_class` column instead of re-deriving from title
   - Old `_classify_run()` removed (replaced by `classify_title` + `_classify_run_from_row`)

2. `commands/catalog.py`
   - `handle_load_ipts`: calls `add_run_class_column(df)` after ONCat fetch
   - `_build_catalog_rows`: added `Class` column to display
   - Added `handle_reclass()` — `/reclass <runs> <class>` command
   - Added `_parse_run_numbers()` helper for run number range parsing

3. `app.py`
   - Imported and registered `handle_reclass`
   - Added `"Class"` to hardcoded catalog column list in `_render_data`
   - Updated help text (Getting Started + command reference)

4. `headless.py`
   - Imported and registered `handle_reclass`

5. `services/llm_handler.py`
   - Added `/reclass` to LLM command reference

6. Documentation: README.md, AGENT.md, SKILL.md, AGENT_SKILL.md all updated

**Valid run_class values:** `scattering`, `transmission`, `bkg_scatt`, `bkg_trans`, `empty_trans`, `empty_scatt`

**User-facing aliases:** `scatt`/`s`, `trans`/`t`, `bkg`, `bkgtrans`, `empty` (=empty_trans), `emptyscatt`, `sample`

**Key design decisions:**
- `run_class` lives in `catalog_data` (list of dicts) so it persists with session save/load automatically
- `add_run_class_column` preserves existing values — only fills in missing/empty entries
- `empty_trans` is the common class; `empty_scatt` is rare but supported
- After `/reclass`, user must re-run `/matchruns` to rebuild the working table

### 2026-04-06: Classification refinements and /matchruns warnings

**1. Fixed empty beam vs background keyword classification:**
- **Empty beam:** standalone `empty`, `emp`, `emt` (word boundary regex), or `* beam`
- **Background:** `bkg`, `banjo`, `background`, `emptycell`, `emptyticell`, `empty ticell`, `ti-cell`, `ticell`
- Background keywords checked BEFORE empty beam regex, so `emptyticell` → `bkg_scatt` not `empty_trans`
- Changed from simple substring matching (`"empty" in title`) to word-boundary regex (`_EMPTY_BEAM_RE`)

**2. Multiple empty beam / background warnings in `/matchruns`:**
- `match_runs()` return type changed: `WorkingTable` → `tuple[WorkingTable, list[str]]`
- Warns per config if >1 `empty_trans` or >1 `bkg_scatt` run found
- Warning includes run numbers + titles so user can decide which to keep
- Only one caller (`handle_matchruns` in `commands/matching.py`) — updated to unpack tuple

**3. `/reclass <runs> sample` — prefix-aware reclassification:**
- `sample` is a special target: looks at each run's S-/T- title prefix
- `S-BkgG` → scattering, `T-BkgG` → transmission (instead of both → scattering)
- Useful when sample names contain background keywords (BkgG, etc.)
- Implemented via `_title_prefix_class()` helper in `commands/catalog.py`

**Files changed:**
- `services/matching_service.py` — keyword lists, `_EMPTY_BEAM_RE` regex, `classify_title()`, `match_runs()` return type
- `commands/matching.py` — unpack `(table, warnings)`, append warnings to summary
- `commands/catalog.py` — `_title_prefix_class()`, `handle_reclass()` sample mode
- Documentation: README.md, SKILL.md, AGENT_SKILL.md updated

### 2026-04-06: /reclass --sample mode

**Problem:** `/reclass` only accepted run numbers. When user said "reclass BkgG as sample" via
NL, the LLM only generated commands for S-BkgG runs (it thought T-BkgG was already transmission).
But T-BkgG was actually classified as `bkg_trans` due to the "bkg" keyword.

**Fix:** Added `--sample` flag to `/reclass`:
- `/reclass --sample BkgG sample` — finds ALL catalog runs whose title contains "BkgG" and reclasses each by S-/T- prefix
- `_match_catalog_title()` strips S-/T- prefix before matching, supports `*` wildcard
- Works with all class targets, not just `sample`: `/reclass --sample emptyticell bkg`

**Files changed:** `commands/catalog.py` — added `_match_catalog_title()`, updated `handle_reclass()` arg parsing

### 2026-04-06: /zipnsend command

New command to zip files and email them via `mailx`/`mail`:
```
/zipnsend ccd@ornl.gov                              # merged*.txt from outputdir
/zipnsend ccd@ornl.gov --pattern "*_Iq.dat"         # custom pattern
/zipnsend ccd@ornl.gov --dir /path --subject "text" # options
```

- 25 MB zip size limit (suggests `/share` if larger)
- Auto-detects `mailx` or `mail`
- LLM handler updated with intent examples: "send/mail/email data to X" → `/zipnsend`

**Files changed:** `commands/export.py`, `headless.py`, `app.py`, `services/llm_handler.py`

### 2026-04-06: /autopilot current + no-arg usage fix

- `/autopilot` with no args now shows usage (consistent with other commands)
- `/autopilot current` uses `state.ipts` from session (preserves reclassed catalog)
- `/autopilot current --bkg banjo` etc. — all flags work with `current`

**Files changed:** `commands/autopilot.py`

### 2026-04-06: Autosave after background thread completion

**Bug:** Both `run_autopilot_worker` and `run_reduction_batch` run in background threads
(`@work(thread=True)`). The normal autosave fires after command dispatch returns, but
`/autopilot` and `/reduce` return immediately (they just launch the thread). So autosave
captured the pre-work state, not the post-work state.

**Fix:** Added `state.save(SessionState.auto_save_path())` in the `finally` block of
`run_autopilot_worker` and after the summary in `run_reduction_batch`.

**Autosave coverage in TUI (`app.py`):**
- After every command dispatch (line ~260)
- After `/reduce` batch completes in thread
- After `/autopilot` completes in thread
- On `/exit` and Ctrl+Q quit

**Files changed:** `app.py` — two locations in background workers

### 2026-04-06: drtsans version in footer bar

Added `drtsans_label` reactive property to `FooterBar` widget. Displays after the LLM model info:
- `drtsans` — default version
- `drtsans --dev` — dev version
- `drtsans --qa` — QA version

Updated `_update_status_bars()` in `app.py` to set the label from `state.drtsans_version`.

**Files changed:** `tui/widgets/status_bar.py`, `app.py`

### 2026-04-09: /autopilot --continue for incremental reduction

**Problem:** Users run autopilot, collect more data, and want to reduce only the new runs
while reusing calibration scale factors, config parameters, and bkg/empty assignments.

**Solution:** At the end of every autopilot run, save a full `SessionState` to
`{outputdir}/autopilot_session.json`. On `--continue`, load this file, refresh the catalog
from ONCat, merge new runs into the saved table, and reduce only new data.

**Key components:**

1. `_save_autopilot_session(state, output_dir)` — saves `state.save()` to outputdir
2. `_load_autopilot_session(output_dir)` — loads saved SessionState from outputdir
3. `merge_new_runs(existing_table, fresh_catalog, ipts)` — in `matching_service.py`:
   - Keeps existing rows with their status (done/error)
   - Adds only new scattering runs from refreshed catalog
   - New rows inherit bkg/empty from existing rows in same config
   - Returns `(table, warnings, n_new, new_config_ids)`

**Modified autopilot flow in --continue mode:**
- Step 1: Always refresh catalog (to discover new runs)
- Step 2: Merge instead of rebuild — `merge_new_runs()` replaces `/matchruns`
- Step 4: Skip presets (restored from saved session), unless new configs found
- Steps 6-8: Skip porsil/calibrate (display saved scale factors)
- Step 9: Only reduce rows with status != "done"
- Steps 10-13: Run normally (stitch all, plot all)

**Syntax:**
```
/autopilot 35884 --continue              # refresh + reduce new only
/autopilot --continue                    # infer IPTS from saved session
/autopilot --continue --samples NewSamp  # composable with all flags
```

**The saved session file is also loadable via `/session load {path}`** — users can inspect
or modify it manually before continuing.

**Files changed:**
- `services/autopilot.py` — save/load functions, `continue_mode` parameter, modified flow
- `services/matching_service.py` — `merge_new_runs()` function
- `commands/autopilot.py` — `--continue` flag parsing
- `app.py` — pass `continue_mode` through worker
- `headless.py` — pass `continue_mode` through dispatch

### 2026-05-01: Custom standard sample (`--standard`)

**Problem:** Autopilot hardcoded "porsil" as the calibration standard sample. But standard
sample names vary: `porsilb1`, `porsil b1`, `agb1`, or any user-chosen name.

**Solution:** Added `--standard <name>` flag and `_is_standard_sample()` helper.
- Default (no flag): auto-detects `porsil*` or `porasil*` by substring match
- With flag: matches by case-insensitive substring against the provided name
- All 13 porsil-hardcoded locations in `autopilot.py` replaced with `_is_standard_sample()`

**Syntax:**
```
/autopilot 38397 --standard porsilb1           # porsilb1 as standard
/autopilot current --standard "porsil b1"      # with space
/autopilot 38397 --standard agb1 --bkg banjo   # composable
```

**LLM handler:** Added intent examples so "use X as standard sample" → `--standard X`

**Files changed:**
- `services/autopilot.py` — `_is_standard_sample()`, `_DEFAULT_STANDARD_PATTERNS`, `standard_sample` param
- `commands/autopilot.py` — `--standard` flag parsing
- `app.py`, `headless.py` — pass `standard_sample` through
- `services/llm_handler.py` — intent examples

### 2026-05-01: /confirm command + autopilot integration

Wraps `/SNS/software/nses/bin/confirm-data` to update IPTS data reduction status in the
SNS experiment tracking system.

**Standalone:** `/confirm [ipts] [--comment "text"]` — always confirms as complete (status=Yes, type=Scripts).

**Autopilot:** Automatically called at the end of autopilot when at least 1 row was reduced.
Comment includes counts: "eqsanscli autopilot: N reduced, M failed".

**Files changed:**
- `commands/export.py` — `run_confirm_data()` helper + `handle_confirm()` command
- `services/autopilot.py` — calls `run_confirm_data()` after summary
- `headless.py`, `app.py` — registered `/confirm` command

### 2026-06-09: Major UX hardening — incremental flow, guide pane, autopilot guarantees

A coordinated set of changes addressing real-world friction from a user session
on IPTS-38603. Each subsection corresponds to a distinct fix.

#### 1. File-path auto-resolution for `/set config <id> <param> <val>`

`commands/config.py` now resolves bare filenames against (a) cwd, (b)
`/SNS/EQSANS/IPTS-{ipts}/shared/`, (c) `/SNS/EQSANS/shared/script/eqsanstools/`.
Applies to: `maskfilename`, `defaultmask`, `sensitivityfilename`, `darkfilename`,
`fluxmonitorratiofile`, `beamfluxfilename`. Absolute paths and `none`/`null` pass
through unchanged. So `/set config 4m10a maskfilename mask4m.nxs` now Just Works
from inside an IPTS folder.

LLM intent docs updated so the LLM passes bare filenames rather than
pre-constructing paths.

#### 2. `/reclass` ignore class (label `N`, aliases `i`/`n`/`skip`/`exclude`)

`services/matching_service.py`:
- Added `ignore` to `VALID_RUN_CLASSES`
- Aliases: `i`, `n`, `ignore`, `ignored`, `notused`, `not_used`, `skip`, `exclude`
- Short display label: `N` (originally `I` — changed for legibility)
- `_classify_catalog` skips rows where `run_class == "ignore"`, so they never
  enter `match_runs()`, `merge_new_runs()`, or `assign_background()`. Ignored
  runs do NOT appear in the working table.

#### 3. Incremental mid-experiment flow

Three new pieces work together:

1. **`/refresh catalog`** (`commands/catalog.py:handle_refresh_catalog`) —
   re-fetches the current IPTS from ONCat while preserving existing
   `run_class` values from `/reclass` overrides. Reports new run count.
   Use this INSTEAD of re-running `/load ipts` (which wipes reclassifications).
2. **`/matchruns --update`** (`commands/matching.py`) — wraps the existing
   `merge_new_runs()`. Appends new scattering runs to the existing table while
   preserving rows with `status=done`, their `output_file`, manual edits, and
   inheriting `bkg`/`empty`/`bkgtrans` from existing rows in the same config.
3. **`/reduce --new`** (`commands/reduction.py`) — selects rows where
   `status != "done"`. Equivalent to autopilot's Step 9 in continue mode.

Both `refresh catalog` and bare `refresh` are registered (the latter is shorthand).
LLM intent docs warn against `/load ipts` re-fetch and route to `/refresh catalog`.

#### 4. `/autopilot --continue` now prefers live state

`services/autopilot.py`: instead of unconditionally loading
`{outputdir}/autopilot_session.json`, `--continue` first checks if the current
in-memory session is usable (`state.ipts` AND catalog AND working table AND
configurations). If yes, uses it directly. If not, falls back to the saved
session file. Also switched Step 1 in continue mode from `/load ipts` to
`/refresh catalog` (preserves reclass overrides during merge).

When loading from disk, now also sets `state.ipts` and `state.catalog` so
downstream `/refresh catalog` works.

#### 5. `/autopilot --fresh` for clean re-runs

When you re-run autopilot in the same session for the same IPTS, by default it
reuses the in-memory catalog and matched table (printing "already loaded" /
"already matched"). `--fresh` forces the cached-state checks at Step 1 and Step 2
to fail, triggering a full reload + re-match.

`--fresh` does NOT clear `/set config` overrides or `--bkg`/`--thickness`/etc.
flags — only the catalog and table get reloaded.

LLM trigger phrases for `--fresh`: "fresh", "from scratch", "clean run",
"reload everything", "start over".

#### 6. `/autopilot` infers IPTS from cwd

`commands/autopilot.py:_infer_ipts_from_cwd()` matches
`/SNS/EQSANS/IPTS-NNNNN/...` patterns in the cwd. If `/autopilot current` is
called without an IPTS in session, this inference fills it in. Bare `/autopilot`
also uses inference. Prints a dim note `Inferred IPTS-N from cwd.` so the user
sees what was picked.

Also previously fixed: `set_config_param`'s mask path resolution uses
`state.ipts` if set, but resolves against cwd first regardless — so pre-loaded
mask sets work even before `/load ipts`.

#### 7. Banjo (and any `--bkg` sample) gets no auto-assigned background

Two locations fixed in `services/matching_service.py`:

- `match_runs()` Step 4: bkg/empty rows get blank `background_scatt`/
  `background_trans` instead of being filled with the empty-beam run.
  Empty-beam is a calibration measurement, not a real background reference.
- `assign_background()`: when a row's `sample_name == bkg_name`, the bkg
  fields are explicitly cleared (was previously setting them to empty-beam).

Combined, the banjo row (or any sample matching `--bkg`) ends up with NO
background subtraction — which is what users actually want for background-cell
runs.

#### 8. Preset preservation + autopilot Step 4b safety net

`commands/preset.py`:
- `/apply preset <name> <cfg>` and `/apply preset auto` now PRESERVE existing
  user-set values by default. Preset apply skips keys already in
  `state.configurations[cfg]`.
- Added `--force` flag to opt in to overwriting.
- Output reports how many user-set params were kept per config.

`services/autopilot.py` — Step 4b (defense in depth):
- At the start of `run_autopilot_sync`, snapshot
  `state.configurations` (normalized by `config_id`).
- After Step 4 (preset apply), iterate the snapshot and re-write any
  differing values onto the actual `state.configurations`. Uses a canonical
  lookup so `4m10a` vs `4m10a60hz` normalization mismatches don't drop user
  intent.
- ALWAYS prints a header (`"Step 4b/13: ..."`), even when nothing to restore.
- Prints an **Effective configuration (key files)** summary listing
  `mask`/`sens`/`dark`/`defmask` basenames per config. This was specifically
  requested for visibility — the user wanted to SEE which mask file each
  config will use at reduction time.

#### 9. `/note` command + auto-logging (note: implemented in a prior session
but documented here for completeness)

`commands/note.py`, `services/note_service.py`. Writes
`{outputdir}/NOTE.md`. Subcommands: `add "<text>"`, `show [N]`, `path`, `clear --yes`.

`commands/router.py` auto-logs every successful command (with a denylist for
read-only commands like `/show`, `/help`, `/note`) to NOTE.md. Format includes
timestamp + IPTS tag. The idea: replaying the commands in NOTE.md reproduces
the reduction workflow.

#### 10. `/guide` side pane + `/help --simple` quickstart

`app.py`:
- New CSS layout — `#main-area` is a Horizontal container wrapping
  `#output-scroll` and the new `#guide-pane` (a `VerticalScroll` so the guide
  content actually scrolls).
- `#guide-pane` is 44 cols wide, hidden by default, toggled by adding/removing
  `-visible` class.
- `/guide` (and `on`/`off`/`hide`/`show`/`close`/`open`) toggles it.
- `/help --simple` prints an inline 7-step quickstart workflow.
- Step 8 in both = `/zipnsend`/`/share` for emailing results.
- Welcome banner (`on_mount`) points users at both `/guide` and `/help --simple`.

**IMPORTANT — Textual name collision:** an earlier version named the reactive
attribute `workers` on `FooterBar` — this shadowed Textual's `Widget.workers`
(WorkerManager) and crashed at unmount. Renamed to `worker_count`. **Do not
use `workers`, `app`, `screen`, or other Widget-reserved names as reactive
attributes.**

#### 11. CPU count in footer status bar

`tui/widgets/status_bar.py` — added `worker_count: reactive[int]` to
`FooterBar`. Renders ` cpu:Nx ` next to drtsans label. `_update_status_bars()`
in `app.py` pushes `state.max_workers` into it.

#### 12. `/session list` shows save date/time; `/continue` cross-cwd

`commands/session.py`:
- `_fmt_mtime()` helper renders `YYYY-MM-DD HH:MM` for each saved file.
- `/session list` sorts by mtime descending (newest first), shows
  `name  YYYY-MM-DD HH:MM  (IPTS-N, M tables)`. Same treatment for
  `/list tables`.

`models/session_state.py` — added breadcrumb:
- `_breadcrumb_path()` → `~/.eqsanscli/last_autosave`
- `record_breadcrumb(path)` writes the path to the breadcrumb (best-effort).
- `read_breadcrumb()` reads it.
- `save()` writes the breadcrumb when `path` is an `_autosave.json` AND the
  session has real content (`ipts != 0` OR non-empty tables). The "real
  content" check prevents an empty just-launched session from clobbering a
  good breadcrumb.

`commands/session.py:handle_continue` — now checks (in mtime order):
1. cwd-local autosave
2. breadcrumb-pointed autosave (if different)
3. named sessions in cwd

Picks the most recent. Shows the loaded path in the message. This solves the
"I launched from a different directory and `/continue` came up empty" footgun
while keeping autosave itself cwd-relative (as the user explicitly requested
in an earlier session).

#### 13. `/autopilot` usage with full step list + `--from` examples

`commands/autopilot.py:_USAGE` — added the canonical 13-step list and concrete
examples for `--from 5/6/9/10/13`. The usage block is now self-documenting for
where `--from` should be used.

**Files changed (this batch):**
- `app.py` — `/help`, `/help --simple`, `/guide`, welcome banner, autopilot
  worker `fresh` wiring, `_update_status_bars()`
- `headless.py` — autopilot dispatch `fresh` wiring, `/refresh catalog` and
  `/note` registration
- `commands/autopilot.py` — `--fresh`, `--from` help, cwd inference
- `commands/catalog.py` — `/refresh catalog`, `/reclass` ignore class help
- `commands/config.py` — file-path auto-resolution
- `commands/matching.py` — `--update` flag wiring `merge_new_runs()`
- `commands/note.py` (new) — `/note` subcommands
- `commands/preset.py` — preserve user values; `--force` flag
- `commands/reduction.py` — `--new` flag
- `commands/router.py` — auto-log to NOTE.md
- `commands/session.py` — date/time display; breadcrumb-aware `/continue`
- `services/autopilot.py` — continue from live state; Step 4b snapshot/restore;
  effective-config summary; `fresh` parameter
- `services/config_manager.py` — `none`/`null` sentinel (clear param to None)
- `services/llm_handler.py` — intent docs for all new commands/flags
- `services/matching_service.py` — `ignore` class; bkg-sample gets no bkg;
  `merge_new_runs()` already existed
- `services/note_service.py` (new)
- `models/session_state.py` — breadcrumb support
- `tui/widgets/status_bar.py` — `worker_count` reactive (named avoid
  Textual's `workers` property collision)

---

### TUI Tips

- **Text selection:** Textual captures mouse events. Use `Shift+click+drag` to select text for copy/paste in the terminal.
- **Reserved Widget attribute names:** Do NOT use `workers`, `app`, `screen`,
  `tree`, `parent`, `children`, etc. as `reactive[]` attribute names — they
  shadow inherited Widget properties and break the message-pump lifecycle.
