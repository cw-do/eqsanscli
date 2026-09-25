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

### 2026-09-25: /load ipts suggests the conventional output folder (v0.45.1)

Asked, after confirming the current behaviour is safe: "having /load ipts suggest
[a] default outputdir." `/load ipts` deliberately changes neither the cwd nor the
output dir — there is no `chdir` in the reduction path, and output defaults to
`./output/` relative to wherever eqsanscli was launched. That is safe but easy to
forget, so reduced files can scatter into a stray `./output/`.

Fix: purely a message addition — no side effect. After a successful `/load ipts`
the handler appends a line showing where output currently points and a
ready-to-paste `/set outputdir /SNS/EQSANS/IPTS-<N>/shared/output/`. It is
suppressed when `os.path.abspath(state.output_directory)` already contains
`IPTS-<N>` (a session that is already pointed at the experiment tree isn't
nagged). Nothing is set automatically — the user still runs `/set outputdir`.

`tests/test_load_ipts.py` (+2: the suggestion appears and changes nothing when
the output dir is unset; it is absent when the dir is already under this IPTS).

**Files changed:** `commands/catalog.py`, `tests/test_load_ipts.py`, CLAUDE.md,
docs (regenerated), `src/eqsanscli/__init__.py`.

### 2026-09-25: title tokens name each sample's background and thickness (v0.45.0)

Asked (Changwoo, working on a proposal-to-script study): a proposal already says
which background each sample uses, so the acquisition script should write it into
the titles — label backgrounds `bkg1`, `bkg2`, … and tell each sample which one to
use — and carry the sample thickness too, since the reduction needs it.

Why it was needed: `match_runs` gives **every** sample in a configuration the
lowest-numbered `bkg_scatt` (and, independently, the lowest `bkg_trans`). A
contrast-variation series (one solvent background per H2O/D2O ratio) or a
temperature series with its own solvent run per temperature was therefore paired
wrongly for every sample but one, and `/assign bkg` could not fix it either — it
also assigns one background per configuration. Thickness was never read from
anything but `/set` / `--thickness` (0.1 cm default).

Grammar (tokens are `_`-delimited words inside the extracted sample name):

- `bkg<N>` in a background title: this is background N.
- `bg<N>` in a sample title: use background N. **Not `bkg<N>`** — `classify_title`
  tests "bkg" as a substring, so `S-x_B_bkg2 4m 10a` is a *background* run. Pinned
  by `test_the_pointer_must_not_be_spelled_bkg`.
- `th<X>mm`: cell path length, `p` for the decimal point (`th0p5mm` = 0.05 cm).

Resolution, within the row's configuration: the `bkg<N>` run with the same
temperature token; else, if `bkg<N>` was measured at only one temperature there,
that one; else nothing is guessed — the row keeps the pre-0.45 default and a
warning names the pointer and what was found. Newest run wins among equals, as for
transmissions. The CAT-04 "several backgrounds, using the first" warning is
suppressed only when every sample row in the config names its own background.
`merge_new_runs` (`--update`) no longer copies the config's background onto a new
row whose title named one. `/matchruns --no-title-tokens` restores the old
behaviour exactly. New protocol rules BKG-04 and TBL-08; CAT-04 and BKG-03 amended.

No effect on existing titles, checked three ways: no `bg<N>`/`th<X>mm` word occurs
in the 367 real ONCat titles of IPTS-36552 and IPTS-38603 or in the 131 titles in
this repo's tests and docs; `match_runs` from v0.44.0 (`a6290d6`) and from this
version give identical working tables and identical warnings on both catalogs
(263 and 54 rows); and a legacy-title test asserts tokens on/off give the same
table. The rest of the suite is unchanged: run on Windows (anaconda 3.12,
`PYTHONUTF8=1`, no `textual`) against a worktree of `a6290d6`, the same 7 tests
fail before and after — all POSIX-only (chmod read-only dirs, `/SNS/…` cwd
parsing) — and passing goes 328 → 339. Not yet run on the analysis nodes.

`tests/test_title_tokens.py` (new, +11). NL routing in `llm_handler`, README
(*Title tokens*), SKILL decision tree, protocol, docs regenerated.

**Files changed:** `services/matching_service.py`, `commands/matching.py`,
`services/llm_handler.py`, `knowledge/protocol.md`, `tests/test_title_tokens.py`,
SKILL.md, README.md, CLAUDE.md, docs (regenerated), `src/eqsanscli/__init__.py`.

### 2026-09-16: /retitle — correct a wrong ONCat run title in-session (v0.44.0)

Asked, in the user's words: "if I can say 'rename 181470 title to be T-L62_0 4m
10A' … or 'replace s1 with L62_0 in the titles of run xxxx-xxxx' … it will be a
lot easier."

Why it was needed: `/matchruns` pairs a scattering run with its transmission /
background / empty-beam runs by parsing the **sample name out of the ONCat title**
(`matching_service._extract_sample_name`). When the titles are wrong, nothing
downstream could fix it — `/reclass` changes a run's *class*, `/set <row> sample`
renames a row *after* matching, and per-row `/set … trans` patches one row and is
discarded by the next `/matchruns`. IPTS-36552 was the case: transmissions titled
by sample-changer slot (`T-s1`, `T-s2`, …) while samples carried real names
(`S-L62_0`), so every transmission failed to pair.

Command surface: `/retitle 181470 T-L62_0 4m 10A` sets one run's whole title;
`/retitle s1 L62_0 [--runs <spec>] [--regex]` swaps a word across all titles;
`/retitle show`; `/retitle clear [<runs>]`. Design decisions worth keeping:

- **Whole-word swap by default** — `s1` must not also rewrite `s10`/`s11` (in
  IPTS-36552 that would have mislabeled two samples). `--regex` is the escape
  hatch. Pinned by `test_word_swap_does_not_touch_s10_or_s11`.
- **ONCat is never written.** Corrections live in `state.title_overrides`
  (`{run: {"title": corrected, "original": what ONCat says}}`), persisted in the
  session, and re-applied after `/load ipts` and `/refresh catalog` (which would
  otherwise bring the wrong titles straight back via `apply_title_overrides()`).
  `/load ipts <different N>` drops them.
- **`original` keeps ONCat's own title**, not the result of an earlier `/retitle`,
  so `clear` always restores the real record.
- **`*` marker** on a corrected title in `/show catalog`.
- Every path ends by telling the user to run `/matchruns`.

Simulating the rename + `/matchruns` on the IPTS-36552 session pairs 260/261 rows
(the leftover is `--- all samples 1mm.`, not a sample). The slot→name mapping was
verified against each NeXus `entry/DASlogs/SampleId` and `SampleTable:Position`,
not guessed.

`tests/test_retitle.py` (new, +9); `tests/test_load_ipts.py` stub updated for the
new `_build_catalog_rows(df, overrides)` signature. NL routing in `llm_handler`,
README, SKILL all updated. 341 tests.

**Files changed:** `commands/catalog.py`, `models/session_state.py`,
`commands/registry.py`, `services/llm_handler.py`, `tests/test_retitle.py`,
`tests/test_load_ipts.py`, SKILL.md, README.md, CLAUDE.md, docs (regenerated),
`src/eqsanscli/__init__.py`.

### 2026-09-10: frame-skipping "fs" suffix broke transmission matching (v0.43.1)

Reported on IPTS-38151: the first transmissions (188011–188019) were measured at
λ=0 and ignored; re-measured ones (188029+) were titled with a frame-skipping
suffix — `T-porsil 4m 2.5afs`, `T-a0ss 4m 2.5afs` — while the samples stayed
`S-porsil 4m 2.5a`. After `/matchruns` every sample had no transmission.

Cause: `_extract_sample_name` strips the config token so a title reduces to a
bare sample key ("S-porsil 4m 2.5a" → "porsil"). Its regex matched distance +
wavelength + an optional `\d+Hz`, but not a `fs` (frame-skipping) suffix glued to
the wavelength. So "T-porsil 4m 2.5afs" stripped only "4m 2.5a", leaving "fs" →
sample key "porsil_fs", which matched nothing (the transmission lookup and its
temperature/displacement-stripped fallback both keyed on the mismatched name).
Classification was fine — 188029/188030/188031 were correctly EmpT/BkgT/T — the
failure was purely the name key.

Fix: the config regex now also consumes an optional `fs` (attached `2.5afs` or
spaced `2.5a fs`), an optional frequency, and a trailing `fs`, case-insensitive.
`T-porsil 4m 2.5afs` → "porsil", matching `S-porsil 4m 2.5a`. Verified end to end
on the IPTS-38151 titles: porsil/a0ss/… each get their `…fs` transmission, empty
beam, and background. Frequency-only and temperature/thickness titles are
unchanged.

`tests/test_matching.py` (+3: fs stripped from the name attached/spaced/with
frequency; the fs transmission matches its plain sample end-to-end; 60Hz and
thickness titles still strip). 332 tests.

**Files changed:** `services/matching_service.py`, `tests/test_matching.py`,
CLAUDE.md, `src/eqsanscli/__init__.py`.

### 2026-09-10: per-row output directory — /set <rows> outputdir <path> (v0.43.0)

Asked: time-slice reductions generate a lot of data, so the user wants each
sample written to its own folder — "if a per-sample outputdir is defined use it,
otherwise the session-wide one." Chosen design (with the user): a per-row
override, two-tier fallback, no auto-magic.

New `output_override: str = ""` on `WorkingTableRow`, alongside
`configuration_override` and persisted in `to_dict` (`from_dict` already drops
unknown keys / keeps dataclass fields, so old sessions load with `""`).
Deliberately **not** in `_REDUCTION_FIELDS`: changing where output is written
does not invalidate a `done` reduction, so it never silently marks a done row
`modified` (an hour-long time-slice run must not re-run just because you moved
its folder).

`/set <rows> outputdir <path>` sets it (registered in `SETTABLE_FIELDS` as
`outputdir`/`outdir`/`output` → `output_override`, echoed as `outputdir`); the
value is stored as an abspath; `none` clears it. Combining with run fields is
rejected by the existing non-run-field guard. `/set outputdir <path>` (no rows)
is unchanged — still the session-wide setter.

Precedence in `reduce_row`: `effective_dir = row.output_override or output_dir`.
Crucially the row override also beats the config's own `outputdir` (which
`build_reduction_json` reads via `config_params["outputdir"]`, and which
`/set outputdir` populates) — so `reduce_row` overlays
`config_params["outputdir"] = effective_dir` when the row overrides. `effective_dir`
is then used for the JSON `outputDir`, the `mkdir`, the `json_path`, and the
produced-file glob, so all four agree. A row with no override behaves exactly as
before.

`handle_reduce`'s up-front writability check (v0.39.0) now iterates the *distinct*
effective dirs of the selected rows, so a bad per-row path is caught before
launch with a fix that names both `/set outputdir` and `/set <rows> outputdir`.
The `⟳` reduce line (both `/reduce` branches) shows `@ <dir>` when a row
overrides. NL routing + SKILL updated.

Not yet: downstream discovery (`/show data`, `/plot`, `/stitch`,
`merge_service._scan_output_dir`) still scans the session-wide dir, so outputs in
an override dir aren't auto-found — view them with `/plot <file>` or
`/show iq <dir>`, which take an explicit path. Descending into override dirs is
the planned follow-up.

`tests/test_matching.py` (+5: set stores abspath, `none` clears, can't combine
with run fields, round-trips, and doesn't mark a done row modified);
`tests/test_reduce_preflight.py` (+2: the override wins over session-wide *and*
the config outputdir in the JSON + on disk; an unwritable override is refused up
front). 329 tests.

**Files changed:** `models/working_table.py`, `commands/matching.py`,
`services/reduction_service.py`, `commands/reduction.py`, `app.py`,
`services/llm_handler.py`, SKILL.md, `tests/test_matching.py`,
`tests/test_reduce_preflight.py`, CLAUDE.md, `src/eqsanscli/__init__.py`.
