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

### 2026-04-06: /zipnsend command

New command to zip files from output directory and email them via `mailx`/`mail`:
```
/zipnsend ccd@ornl.gov                          # merged*.txt from outputdir
/zipnsend ccd@ornl.gov --pattern "*_Iq.dat"     # custom file pattern
/zipnsend ccd@ornl.gov --subject "IPTS data"    # custom subject
/zipnsend ccd@ornl.gov --dir /path              # from specific directory
```
- 25 MB size limit (suggests `/share` if larger)
- Auto-detects `mailx` or `mail` on system
- LLM handler has intent-mapping examples so "send/mail/email data to X" routes to `/zipnsend`

**Files changed:** `commands/export.py`, `headless.py`, `app.py`, `services/llm_handler.py`
