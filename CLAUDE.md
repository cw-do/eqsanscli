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
  config/             — Presets and settings
  tui/widgets/        — TUI components
preset_configs/       — Preset JSON configs for known instrument configurations
```

### Key patterns

- Commands are registered in both `app.py` and `headless.py` — always update both when adding a new command.
- Also update the LLM command reference in `services/llm_handler.py` for natural language routing.
- `app.py` has a `_render_data` method with hardcoded column lists per data type — update when adding columns.
- Session state auto-saves after every command. `catalog_data` is stored as list-of-dicts.
- `SKILL.md` and `AGENT_SKILL.md` document the tool for TUI and headless agent use respectively.

### Testing

No formal test suite. Quick verification via:
```bash
python -c "import sys; sys.path.insert(0, 'src'); from eqsanscli.<module> import <thing>; ..."
```

The `.venv` has textual/rich but the system Python may not — use `sys.path.insert(0, 'src')` for import-only checks.

---

## Change Log

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
