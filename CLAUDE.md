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
| 0.47.5 | 2026-10-02 | Startup banner: one line under Getting Started — *Best viewed in a terminal window of at least 120×35*. Chosen over auto-resizing the window (`ESC[8;35;120t`), which only some terminals honour (VTE, macOS Terminal, PuTTY; not xterm by default, Windows Terminal, VS Code, tmux/screen) and which would leave the user's window resized after exit. Text only. |
| 0.47.4 | 2026-10-01 | Naming: the release folder is **`eqsanscli-stable`** (was `eqsanscli-safe`), matching `sansdir-stable`. Rebuilt fresh at the new path (a venv bakes its own path into its scripts, so it is not moved), `/SNS/EQSANS/shared/bin/eqsanscli` repointed, the old folder removed. Docstring and CLAUDE.md only in the repo. |
| 0.47.3 | 2026-09-29 | **Release channel `eqsanscli-safe`** (renamed `eqsanscli-stable` in 0.47.4; same protocol as `sansdir-stable`): users run a non-editable install of a tagged commit. Six data lookups (`.env`, `knowledge/`, `protocol.md`, `preset_configs/` ×2, `absscale_reference/`) walked up four levels from `__file__` — inside a site-packages install that is the venv, so they would have found nothing, silently. They now go through `eqsanscli.paths.app_root()`: `EQSANSCLI_ROOT` (exported by the launchers, previously unused) when it names a folder, else the repo root. `tests/test_paths.py` forbids the old pattern. |
| 0.47.2 | 2026-09-29 | Fix: **autopilot found no stitchable groups** on IPTS-37681. Titles wrote the configuration without a space (`S-CTAB 1,3_0.1shear 4m2.5a`); `_extract_sample_name` only stripped the spaced form (`4m 2.5a`), so the name kept `_4m2.5a`, output doubled it (`…_4m2.5a_4m2.5a_Iq.dat`), and the 4 m and 8 m rows of one sample had different names — every group had one config. Names now drop a compact configuration word (`4m2.5a`, `8m10a`, `2p5m2p5a`, `…30hz`, whole words only), and `build_stitch_table` groups on the name without a configuration token (`strip_config_tokens`), so sessions matched before the fix stitch their existing files without re-reducing. STC-01. |
| 0.47.1 | 2026-09-29 | Fix command forms the app itself told users to type. The `/session load` listing said `Usage: /load session <name>`, which refused with "Use /session load …" (a loop); README said `/save session …` (also refused). `/load session` and `/save session` now **forward** to `/session load`/`save`. `/help` listed `/confirm … (--status, --comment)` but `--status` never existed and unknown args were silently dropped — `/confirm --status No` would still confirm **Yes**; `/confirm` now refuses anything it does not parse. Found by auditing every `/command` mention (code strings, SKILL, README, knowledge, docs) against the router; `tests/test_command_forms.py` keeps the documented-flags check permanent. |
| 0.47.0 | 2026-09-29 | **rheo-SANS matching + prefix-aware `/reclass`**, from IPTS-37681 (CTAB in a Couette cell, shear planes 1,3/2,3 × shear rates × 2 configs). (1) `/reclass --sample S-X bkg` now reaches only `S-` titles (a prefixed name matches only that prefix; before, the prefix was discarded, so "S-cup are bkg, T-cup are bkgtrans" set all ten runs BkgS then all BkgT); new prefix-aware class `background` (S-→BkgS, T-→BkgT); a literal class contradicting a run's prefix is warned; a name-based reclass no longer revives `ignore` runs. CAT-08. (2) `/matchruns`: a `_<rate>shear` token is a condition like `_dX` — every shear rate takes the plane's at-rest transmission (TBL-09); several empty beams/backgrounds per config are chosen per row by the distinguishing title token the sample shares (`empty beam 2,3` for `CTAB 2,3_…`), else first-found + warning as before (CAT-09; off with `--no-title-tokens`). `emptycup` is a background keyword. 20 → 0 rows missing transmission, and the 2,3 rows no longer get the 1,3 empty beam/cup. (3) Default OpenRouter model → `openai/gpt-6-luna-pro`. |
| 0.46.3 | 2026-09-26 | Cosmetic: the catalog **Class column is now colour-coded** in `/load ipts` and `/show catalog` — scattering `S` bold green, transmission `T` cyan, background `BkgS`/`BkgT` yellow, empty beam `EmpT`/`EmpS` magenta, ignored `N` dim — so run roles are scannable at a glance. TUI-only: `_render_table` renders the Class cell as a styled `rich.Text` (`_CLASS_STYLES`, `_class_cell`); the underlying row data is unchanged, so headless JSON stays plain. |
| 0.46.2 | 2026-09-26 | Fix: v0.46.0's launcher hook **forced the ONCat browser sign-in before the TUI started** when no token existed — intrusive, and it pre-empted the intended in-TUI `/oncat login`. The launcher no longer signs in at startup; the TUI just opens. When not signed in it shows one non-blocking line (`🔑 Not signed in to ONCat — type /oncat login …`), and `/load ipts` still prompts on demand. Sign in via `/oncat login` in the TUI (device URL shown in the pane, approve in your browser — works over SSH) or `eqsanscli-oncat-login` in a terminal, whichever you prefer. |
| 0.46.1 | 2026-09-25 | Document the ONCat sign-in (v0.46.0) in the **in-CLI help**: `/oncat login|status|logout` now appear in `/help` (new "ONCat Sign-in (per-user)" block), as step 0 in `/help --simple` and the `/guide` side pane, and in the startup "Getting Started" banner — with the per-user + SSH (approve the URL in your own browser) notes. Help text only; no behaviour change. |
| 0.46.0 | 2026-09-25 | **Per-user ONCat login (Device Authorization Grant).** The old code authenticated with a committed machine-to-machine `client_id`+`client_secret` (`CLIENT_CREDENTIALS_FLOW`) — one shared identity for everyone, and the **secret was in the public repo** — which ORNL's docs say must not be used for a distributed CLI. Now each user signs in as themselves: a **public** client id (no secret), device flow, per-user token cached in `~/.eqsanscli/oncat_token.json` (0600), so `/load ipts` and `/list ipts` return **only the IPTS that user can access**. New `/oncat login|status|logout`, an `eqsanscli-oncat-login` console entry, and a launcher hook that runs the one-time sign-in before the TUI. Works over SSH: the verification URL is shown (TUI pane or terminal), the user approves it in their own browser. Data calls are **token-first and never pop a browser** (raise `OncatAuthRequired` → "run /oncat login"); the TUI runs the sign-in in a worker thread. Browserless services (NDIP/Galaxy) can set `ONCAT_USERNAME`/`ONCAT_PASSWORD`/`ONCAT_CLIENT_ID`/`ONCAT_CLIENT_SECRET` (deprecated Password Grant, no secret committed) or pre-seed a token. Requires `pyoncat>=2.6` (2.7 installed on the cluster venv). **The leaked m2m secret must be revoked by the ONCat admin** — it stays in git history. |
| 0.45.2 | 2026-09-25 | Fix: a **retired sensitivity file kept beside its replacement** could be chosen over the live one. On 2026B a new 4 m flood `…_186200.nxs` was added and the old one renamed `…_186200.OLD_nominal_geometry.nxs` and kept "just in case"; both parsed to the same `(variant, plain, run)`, and on that tie `_pick_sensitivity`'s `max()` returned the alphabetically-first candidate — and `.OLD_…` sorts before `.nxs` — so 4 m reductions silently used the old map. `SensitivityFile` gains a `deprecated` flag (name contains a delimited marker token: `OLD`/`bak`/`backup`/`deprecated`/`superseded`/`donotuse`/…), and `not deprecated` is now the top-priority ranking key: a live file always beats a marked sibling, but a marked file is still used if it is the only map for that distance (deprioritize, don't exclude — a cycle never loses its sensitivity). Protocol CAL-06. The live 2026B test was de-literal'd (asserts a live 4 m map the folder holds, never an `OLD` one) per the "no pinned machine-physics literals" rule. |
| 0.45.1 | 2026-09-25 | `/load ipts` now **suggests** the conventional output folder. It still does not change the cwd or the output dir (deliberately safe — reduced files default to `./output/` next to the cwd), but the load message now shows where output currently points and a ready-to-paste `/set outputdir /SNS/EQSANS/IPTS-<N>/shared/output/`. The nudge is suppressed when the current output dir is already inside this experiment's tree (contains `IPTS-<N>`), so a configured session isn't nagged. Suggestion only — nothing is set for you. |
| 0.45.0 | 2026-09-25 | **Title tokens name each sample's background and thickness.** A background titled `bkg<N>_…` is background N; a sample titled `…_bg<N>_…` gets that background from its own config at the same temperature token (else the only `bkg<N>` there; never guessed — unresolved keeps the default and warns); `…_th<X>mm_…` sets thickness (`th0p5mm` = 0.05 cm). The pointer is `bg`, not `bkg`, because any title containing "bkg" is a background. Before, every sample got the config's lowest-numbered background, so contrast and per-temperature solvent series were mis-paired. `--update` keeps a title-named background; `/matchruns --no-title-tokens` restores the old behaviour. Existing titles unaffected: identical tables and warnings vs 0.44.0 on IPTS-36552/38603. BKG-04, TBL-08. |
| 0.44.0 | 2026-09-16 | **New `/retitle` command — correct a wrong ONCat run title in-session so `/matchruns` can pair it.** `/matchruns` derives the sample name from the title, so a transmission mislabeled by sample-changer slot (`T-s1 4m 10A`) can never pair with `S-L62_0 4m 10A` — and `/reclass` (fixes *class*), `/set <row> sample` (renames *after* matching) and per-row `/set … trans` (thrown away by the next `/matchruns`) couldn't fix it. `/retitle 181470 T-L62_0 4m 10A` sets one run's whole title; `/retitle s1 L62_0 [--runs <spec>] [--regex]` swaps a word across titles (**whole-word by default** so `s1` never rewrites `s10`/`s11`); `/retitle show` / `/retitle clear [<runs>]`. Corrections live in the session (`state.title_overrides`, `{run: {title, original}}`), never touch ONCat, and are re-applied after `/load ipts`/`/refresh catalog` (which would bring the wrong titles back); `/show catalog` marks a corrected title with a trailing `*`; `original` always keeps ONCat's own title so `clear` restores the real record. Motivated by IPTS-36552 (11 slots × 2 configs; verified against each NeXus `SampleId`/`SampleTable:Position`). |
| 0.43.1 | 2026-09-10 | Fix: a frame-skipping mode suffix in a transmission title stopped it matching its sample. IPTS-38151 samples were titled `S-porsil 4m 2.5a` but the re-measured transmissions `T-porsil 4m 2.5a`**`fs`** — the `fs` glued to the wavelength leaked past the config-stripping regex into the extracted sample name (`porsil_fs`), so it never matched `porsil` and every sample came out with no transmission. `_extract_sample_name`'s config regex now also consumes a `fs` suffix (attached `2.5afs` or spaced `2.5a fs`) and a following frequency token, so `T-…fs` transmissions match their plain `S-…` samples. Classification was already correct; only name extraction was wrong. |
| 0.43.0 | 2026-09-10 | **Per-row output directory: `/set <rows> outputdir <path>`.** For data-heavy (time-sliced) reductions the user wanted each sample in its own folder. New per-row `output_override` field on `WorkingTableRow` (mirrors `configuration_override`); precedence is **row override → session-wide** (the row override also wins over the config's own `outputdir`, which `build_reduction_json` otherwise uses). `reduce_row` computes an `effective_dir` used consistently for the JSON `outputDir`, the `mkdir`, and the produced-file glob. `none` clears the override (back to session-wide). `/reduce` and autopilot's up-front output-dir writability check now validates *each distinct* effective dir (a bad per-row path is caught before launch, not per row). The `⟳` reduce line shows `@ <dir>` when a row overrides. Changing `output_override` deliberately does **not** mark a `done` row `modified` — where output is written doesn't invalidate the science (an hour-long time-slice run won't silently re-run). Persisted in `to_dict`; NL routes "put rows 5-10 output in /path" → `/set 5-10 outputdir /path`. |
| 0.42.0 | 2026-09-10 | **Time-slice reductions now show a slice estimate up front and a live progress heartbeat.** A user reducing a 1-hour run at a 5 s interval (720 slices) had no idea that was 720× the work and saw no progress for an hour. Two fixes: (1) `/reduce` (and autopilot) now print a per-config line — `⏱ Time-slicing 4m2.5a30hz: ~720 slices/run (3600s ÷ 5s)` — computed from the config's `timesliceinterval` and the run's catalog `duration`, with a caution above 200 slices; new `timeslice_estimate()` + `SessionState.run_duration()`. (2) `run_reduction` now **streams** drtsans stdout/stderr to the `.out`/`.err` files as it arrives (line-buffered, `PYTHONUNBUFFERED=1`, reader threads) instead of buffering until the end — so the log can be watched with `tail -f`, cancellation stays responsive (~0.2 s poll), and an optional `progress_cb` counts drtsans's per-slice `SaveNexus …_processed.nxs` lines to emit a throttled `⏳ <sample>: slice N/720 (P%)` heartbeat in the TUI (`make_slice_progress`, ≤1 line per 25 slices / 30 s). |
| 0.41.0 | 2026-09-10 | **A second `/reduce` or `/autopilot` while one is running is now refused instead of launching a concurrent batch.** Reductions run in a background worker thread, so the TUI input stays live; before this, a second `/reduce` started a *second* thread pool — up to 2× the worker count of drtsans processes, a shared cancel event (one Cancel stopped both), interleaved output, and — if a row was in both batches — the same run reduced twice at once, both writing the same output files. The `_job_running` flag existed but was only read by the Cancel binding. New `_reject_if_busy()` guard at both worker launch sites in `_render_data` refuses with `⚠ A job is already running — not starting another <reduction/autopilot>. Wait … or press ^X / ✕ Cancel`. The flag is now claimed synchronously on the main thread at launch (not only inside the worker) so two fast submissions can't both pass. TUI-only (headless reduces synchronously, so it can't overlap). |
| 0.40.0 | 2026-09-10 | **A GUI/display crash *after* a complete reduction is no longer reported as a failure.** A 62-min time-slice reduction (IPTS-38151 a20a0-1_fs) wrote all 242 I(Q) files, then drtsans exited nonzero on a teardown error — an interactive Qt plot attempted under `--simple-prompt` (`Cannot install event loop hook for "qt"`) with a dropped X11 connection (`ICE default IO error handler doing an exit(), errno = 32`). Since success was decided purely by exit code, the row was marked `error` and would be needlessly re-reduced. `reduce_row` now **rescues** such a run: if I(Q) output files exist (glob, so time-slice layouts count), the log tail carries a recognizable display-teardown signature, and there is no Python traceback, it sets `success=True`, marks the row `done`, and attaches a `note` (shown as a `⚠` line in `/reduce`/autopilot, included in headless JSON) explaining the non-fatal exit. A genuine crash (traceback) or a run that produced no output still fails. Also fixes `output_file` detection for time-slice runs (was pointing at a non-existent `<name>_Iq.dat`). |
| 0.39.0 | 2026-09-10 | **A non-writable output directory no longer crashes eqsanscli.** Setting `/set outputdir` to a folder without write permission crashed the app mid-reduction — `Path(output_dir).mkdir()` raised `PermissionError` inside the reduction worker and took the whole TUI down. Now three layers: `/set outputdir` **warns immediately** if the path isn't writable; `/reduce` and autopilot **refuse up front** with one clear line (`Cannot reduce — output directory permission denied … Set a writable one with /set outputdir <path>`) instead of failing every row; and `reduce_row` **catches `OSError`** so any per-row write failure becomes a failed result (`row.status=error`, clear stderr) rather than an escaped exception. New `output_dir_problem()` helper checks the nearest existing ancestor (the dir need not exist yet). `_summarize_error` gained a stderr fallback so the message surfaces even with no `.out`/`.err` file. |
| 0.38.0 | 2026-09-10 | Two things found driving a real reduction. **`/matchruns --update` now back-fills a transmission (or background/empty) measured *after* the first match** — you match while collecting (scattering done, no transmission yet), measure the transmission later so it lands at a higher run number, and `--update` (which preserves existing rows verbatim) would leave the field empty forever. It now fills any *empty* run field on an existing row from the fresh match, marking the row `modified`; a value already set (incl. user overrides) is never touched. Plain `/matchruns` was always order-independent (matches by sample name). **Parallel `/reduce` now prints each `⟳ <sample>` line when a worker actually starts that job**, not all upfront — a 10-run batch on 3 workers no longer shows 10 "submitted" lines at once (which read as 10 running); the `[n/total]` ordinal counts job *starts*, so at most `max_workers` show as in-progress. |
| 0.37.0 | 2026-09-01 | `/config list` now shows a clone's normalized id in parentheses (`4m2.5a30hz_TR (4m2.5a30hztr)`) and flags **leftover** configs — a stored key that collapses to the same normalized id as another (e.g. a phantom from a `_`/case variant), which the dedup otherwise hid — with a `/config delete` hint. New `/config delete <id> [--force]`: deletes a clone/leftover config; refuses a config that is the *physical* configuration of rows; `--force` also reverts rows using a clone to their physical config (marking `done` rows `modified`). Rows are matched by exact override key, so deleting a phantom never touches the real clone. The reduction-table Config column is unchanged (per request). |
| 0.36.6 | 2026-09-01 | Fix: `/set config <clone> <param> <val>` on a cloned config whose name has an underscore/uppercase (e.g. `4m2.5a30hz_TR`) silently wrote to a phantom key — `handle_set_config`/`handle_show_config` normalized the id (`4m2.5a30hz_TR` → `4m2.5a30hztr`), but clones are stored under their raw name, so the override landed on a non-existent config and the row's reduction never saw it (`usetimeslice` kept reading its old value; the confirmation even echoed the mangled name). Both now resolve the typed id to the existing config key (exact, then normalized-equal, preserving the stored casing) before read/write; the normalized spelling also maps back to the clone. New config ids still fall back to normalized. |
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

### Release channel (`eqsanscli-stable`)

Users run a **frozen release**, not this tree — same protocol as `sansdir-stable`:

```
/SNS/EQSANS/shared/script/eqsanscli-stable/
  bin/eqsanscli, bin/eqsanscli-headless, bin/eqsanscli-oncat-login   launchers
  python/           the release's own Python 3.11 (pixi, conda-forge) on GPFS
  .venv/            built on python/; non-editable install of the tagged commit
  constraints.txt   pinned dependency versions (snapshot of the tested dev venv)
  knowledge/ preset_configs/ absscale_reference/   extracted from the same tag
  .env              LLM key/model — local config, not in git, never overwritten
  update.sh         maintainer only
  VERSION           version, tag, commit, date
/SNS/EQSANS/shared/bin/eqsanscli -> ../script/eqsanscli-stable/bin/eqsanscli
```

To release: commit, bump, push, `git tag vX.Y.Z && git push origin vX.Y.Z`, then
`/SNS/EQSANS/shared/script/eqsanscli-stable/update.sh vX.Y.Z`. `update.sh` installs
from `git archive <tag>`, so uncommitted edits can never reach a user, and it
keeps already-installed dependencies frozen (adds only missing ones).

**The interpreter must live on the shared filesystem.** A venv does not contain
Python — its `bin/python` links to the interpreter it was built from. Built on
`/usr/bin/python3.11` (an optional RPM, node-local), the release failed on
analysis-node23, which lacks it (2026-10-02: "stable-release venv not found").
`python/` is a pixi project (`pixi.toml`, `python = "3.11.13.*"`); `update.sh`
creates `.venv` from it when missing and refuses to run without it. Verified by
running the user launcher in a mount namespace with `/usr/bin/python3.11` and
`/usr/lib64/python3.11` hidden. (`sansdir-stable` is still built on the system
Python — not yet changed.) Recreate from scratch: `cd python && pixi install`,
remove `.venv`, `./update.sh <tag>`; pixi needs
`HTTPS_PROXY=http://bl-proxy1.sns.gov:3128`.

The launchers export `EQSANSCLI_ROOT` = the release folder; **every data lookup
must go through `eqsanscli.paths.app_root()`**, never `Path(__file__)` walking
up — in site-packages that lands inside the venv and finds nothing, silently
(`tests/test_paths.py` enforces it). A new top-level data folder must also be
added to `update.sh`'s extract list.

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

### 2026-10-02: banner recommends a 120×35 window (v0.47.5)

Asked whether eqsanscli could enlarge a too-small terminal to 120×35. Possible
only as a request to the terminal (`ESC[8;rows;cols t`, what `resize -s` sends),
honoured by VTE terminals (the analysis-cluster desktop), macOS Terminal and
PuTTY, but ignored by xterm (allowWindowOps off by default), Windows Terminal,
VS Code, tmux/screen and maximized windows — and a resize outlives the program.
The user preferred an instruction: the Getting Started banner now ends with
"Best viewed in a terminal window of at least 120×35 — enlarge it for readable
tables." Text only.

**Files changed:** `app.py`, CLAUDE.md, docs (regenerated),
`src/eqsanscli/__init__.py`.

### 2026-10-01: release folder renamed eqsanscli-stable (v0.47.4)

v0.47.3 shipped the release channel as `eqsanscli-safe`; the agreed name is
`eqsanscli-stable`, parallel to `sansdir-stable`. Built fresh at
`/SNS/EQSANS/shared/script/eqsanscli-stable` (new venv from the same
`constraints.txt`, the same `.env`, launchers and `update.sh` with the wording
changed) and released this tag into it, rather than `mv`-ing the old folder: a
venv bakes its absolute path into `bin/` scripts and `pyvenv.cfg`.
`/SNS/EQSANS/shared/bin/eqsanscli` now points at it and `eqsanscli-safe` is gone.
In the repo only the `paths.py` docstring and CLAUDE.md named the folder; the
v0.47.3 entries keep the name it actually shipped under, with a pointer here.

**Files changed:** `paths.py` (docstring), CLAUDE.md, docs (regenerated),
`src/eqsanscli/__init__.py`.

### 2026-09-29: release channel eqsanscli-safe; data folders via EQSANSCLI_ROOT (v0.47.3)

(Renamed `eqsanscli-stable` in v0.47.4.)

Asked to create a safe distribution folder for eqsanscli "as we did for
sansdir": `sansdir-stable` holds its own venv with a non-editable install of a
tagged commit, launchers that use only that venv, an `update.sh` that installs
from `git archive <tag>` (never the working copy), and a `VERSION` file.

eqsanscli could not be installed that way as it stood. `knowledge/`,
`preset_configs/`, `absscale_reference/` and the shared `.env` live at the repo
root, outside the package, and six call sites found them with
`Path(__file__).resolve().parent.parent.parent.parent` (protocol.py with four
nested `dirname`s). From site-packages that resolves inside the venv — no
presets, no always-loaded protocol, no absolute-scale reference, no LLM key —
and each lookup degrades quietly rather than failing. The launchers already
exported `EQSANSCLI_ROOT`, but nothing read it.

New `eqsanscli/paths.py:app_root()` returns `EQSANSCLI_ROOT` when it names an
existing folder, else the repo root (so the dev tree and tests are unchanged);
all six sites use it. The release folder carries copies of the three data
folders extracted from the same tag as the code. Chosen over packaging them as
wheel data because the cwd overrides (`./knowledge`, `./preset_configs`) and the
shared `.env` are folder-based anyway, and it keeps one mechanism for dev and
release.

`tests/test_paths.py` (+4): default is the repo root; the env root wins and
moves `protocol_path()`; a missing env root falls back; no module walks up from
its own file. Release procedure documented under *Release channel* above.

**Files changed:** `paths.py` (new), `config/settings.py`,
`services/knowledge.py`, `services/protocol.py`, `services/preset_service.py`,
`services/calibration_service.py`, `services/smart_stitch.py`,
`tests/test_paths.py`, CLAUDE.md, docs (regenerated),
`src/eqsanscli/__init__.py`.

### 2026-09-29: compact configuration in titles no longer blocks stitching (v0.47.2)

Reported after a full autopilot on IPTS-37681: "28 reduced … ⚠ No stitchable
groups found". Titles wrote the configuration as one word (`S-CTAB 1,3_0.1shear
4m2.5a`). `_extract_sample_name` strips `\d+m\s+\d+a`, i.e. only the spaced
form, so the sample name kept `_4m2.5a`; `output_stem` appended the config again
(`CTAB_1,3_0.1shear_4m2.5a_4m2.5a_Iq.dat`); and `build_stitch_table`, which groups
by `row.sample_name`, saw `…_4m2.5a` and `…_8m10a` as two samples. I had noticed
the leftover config in v0.47.0 and called it harmless for matching — true, but it
broke stitching.

Two fixes. Root: `_extract_sample_name` also removes a configuration written as a
whole word (`_CFG_WORD_RE`: distance `m` wavelength `a`, `.` or `p` decimal,
optional `fs`/`<n>hz`, delimited by whitespace/`_`/ends — `sample2m5a` is left
alone). Compatibility: `build_stitch_table` keys groups by
`strip_config_tokens(row.sample_name)`, so an existing session (rows named before
the fix, files already on disk with the doubled stem) stitches without
re-matching or re-reducing. `_CFG_TOKEN_RE` (CAT-09's token filter) now shares the
same pattern body.

Verified read-only on the real `autopilot_session.json`: 14 groups, all
stitchable (12 CTAB + 2 EmptyCupBob), each ordered 8m10a → 4m2.5a, files found
under their existing names. STC-01 extended. `tests/test_rheo_matching.py` (+2).
380 tests.

**Files changed:** `services/matching_service.py`, `services/merge_service.py`,
`knowledge/protocol.md`, `tests/test_rheo_matching.py`, CLAUDE.md, docs
(regenerated), `src/eqsanscli/__init__.py`.

### 2026-09-29: command forms the app tells you to type now work (v0.47.1)

Reported: `/session load` lists sessions and ends "Usage: /load session <name>";
typing that answered "Use /session load <name> or /session list instead." Asked to
check the other usages for the same kind of error.

Audit, three passes over every `/command` mention in the code's string literals,
SKILL.md, README, `knowledge/` and `docs/pages/`:
1. every top-level command resolves in the router — clean (hits were Rich markup
   `[/dim]` and paths);
2. every distinct `/command subcommand` form dispatched through the real router
   on an empty session in a sandbox cwd/HOME (skipping shell, ONCat, share,
   zipnsend, exit, rm/mv/cp/cd), flagging "Unknown …"/"… instead" replies — after
   discarding noise (trailing punctuation, flags probed without their value,
   prose like "/instrument find the mask"), two real errors: the listing hint
   above and README's `/save session myexperiment`;
3. every `--flag` written after a `/command` is parsed somewhere — one miss:
   `/help` advertised `/confirm … (--status, --comment)`. There is no `--status`,
   and `handle_confirm` silently skipped anything it did not parse, so
   `/confirm --status No` would still write status=Yes to the IPTS record.

Fixes: the listing hint reads `/session load <name>`; `/load session` and `/save
session` forward to `/session load`/`save` instead of refusing (both spellings are
natural, and the TUI does not special-case the session command); README uses
`/session save`; `/help` shows `/confirm [ipts] [--comment <text>]`; `/confirm`
refuses any argument it does not understand (autopilot calls `run_confirm_data`
directly, unaffected).

`tests/test_command_forms.py` (+4): the listing's hint round-trips to a load; both
spellings forward; `/confirm --status No` writes nothing; and pass 3 as a
permanent check (no false positives today). Pass 2 is too noisy for a test.

**Files changed:** `commands/session.py`, `commands/export.py`, `app.py`,
README.md, `tests/test_command_forms.py`, CLAUDE.md, docs (regenerated),
`src/eqsanscli/__init__.py`.
