# eqsanscli change log

Full history, newest first. The most recent entries also appear in
`CLAUDE.md`; everything older lives only here, so the file loaded into every
session stays small. Same format: one `###` heading per revision, tagged with
the version it shipped in.

---

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

### 2026-08-28: /show table filters — rows, name, sample (v0.28.0)

Asked for `/show table --rows 50-100` and `/show table --name 0.25phr` (rows whose
sample name contains `0.25phr`). `/show table` previously took only `--sample`,
which is an *exact* match (or glob with `*`), so `--sample 0.25phr` matched
nothing — you had to type `--sample *0.25phr*`.

Three filters, composable (AND):
- **`--rows <spec>`** (aliases `--row`/`--index`/`--idx`/`--range`) — index range,
  list, or run number, via the existing `parse_row_selection` (`50-100`, `1,3,5`).
- **`--name <text>`** (alias `--contains`) — case-insensitive **substring** of the
  sample name, the easy "contains" form the user wanted.
- **`--sample <pat>`** — kept as-is: exact, or glob when it contains `*`.

Unrecognised arguments are now rejected with usage rather than silently ignored
(the parser walks tokens instead of only checking `args[0]`). Read-only — no rows
are removed; the label shows which filters ran and "N of M row(s)". LLM routing
maps "rows 50 to 100" → `--rows`, "containing 0.25phr" → `--name`.

`tests/test_show_table.py` (10 checks): substring vs glob vs exact, range/list,
filters combining, no-match message, unknown-flag rejection, empty table. 233
tests.

**Files changed:** `commands/catalog.py`, `services/llm_handler.py`,
`tests/test_show_table.py` (new), SKILL.md, CLAUDE.md,
`src/eqsanscli/__init__.py`.

### 2026-08-28: long names wrap in the tables, not truncate (v0.27.1)

Reported: in the reduction (working) table a long sample name showed clipped —
`70.30PBD_0.25…`. The run-number columns wrapped fine, so the fix should make the
sample column behave the same.

**Cause.** Rich `Table` columns default to `overflow="ellipsis"`, so a plain-text
cell that outgrows its allotted width is truncated with `…`. The run-number
columns only *looked* like they wrapped because `_run_cell` puts the title on a
second line with an embedded `\n`; even they clipped a long no-space title token
(`S-70.30PBD…`) at a narrow width.

**Fix.** `overflow="fold"` on every free-text column of the working table (Sample,
Config, and the five run columns) and the stitch table's Sample. Fold wraps the
full text onto more lines — breaking mid-token when there is no space — so nothing
is ever hidden. The fixed-width numeric/status columns (Idx, Thick, Status) keep
the default; they are short and must not wrap.

`tests/test_table_display.py` (3 checks) drives the real render methods with a
stub log and asserts the free-text columns fold and none of them ellipsize. 223
tests.

**Files changed:** `app.py`, `tests/test_table_display.py` (new), CLAUDE.md,
`src/eqsanscli/__init__.py`.

### 2026-08-28: one cancel stops the whole parallel batch (v0.27.0)

Reported: clicking Cancel during a multi-core reduction only killed the in-flight
jobs; a 15-job batch kept going and needed several clicks. Single-core cancelled
cleanly on one click.

**Cause.** `reduce_row` / `run_reduction` checked the cancel event only *after*
launching drtsans. In a `ThreadPoolExecutor` batch every row is submitted up
front; when the user cancels, the running jobs are killed within ~1s, but as each
worker frees the executor hands it the next queued row, which builds a JSON and
spawns a fresh drtsans — waits 1s — *then* notices the cancel and dies. So one
click drained the queue slowly, one launch at a time, and looked like it wasn't
working. Single-core was fine because it checks the event at the top of each
iteration and returns.

**Fix, two layers:**
1. `reduce_row` returns immediately with a cancelled result when the event is
   already set, before building a JSON or spawning drtsans. This is the
   deterministic core — every queued row becomes a no-op, so the batch drains in
   the ~1s it takes to kill the in-flight jobs, not job-by-job.
2. Both parallel loops (`app.py` `/reduce` worker and `services/autopilot.py`
   `_reduce_phase`) drop every not-yet-started future (`future.cancel()`) and
   break the moment the event is seen, so freed workers never pick up a queued
   row and the summary reports the queued jobs as cancelled.

`tests/test_reduce_cancel.py` (3 checks): a set event makes `reduce_row` a no-op
(run_reduction never called), an unset event still launches exactly once, and a
`None` event is safe. The executor-loop drop is timing-dependent and left to real
use rather than a flaky concurrency test. 220 tests.

**Files changed:** `services/reduction_service.py`, `services/autopilot.py`,
`app.py`, `tests/test_reduce_cancel.py` (new), CLAUDE.md,
`src/eqsanscli/__init__.py`.

### 2026-08-25: stop autopilot at a step, and reject unknown flags (v0.26.0)

Two gaps found while driving autopilot by natural language.

**1 — no way to stop partway.** "reduce porsil and find scale factor" / "run
autopilot until you get the scale factor" had no target: `--from N` sets a start
but there was no end. Added **`--to N`** (aliases `--till`, `--until`): run
through step N, then write a resumable summary (`--from N+1` / `--continue`) and
save the session. `_maybe_stop(step)` is checked at the step boundaries (2, 4, 5,
8, 9, 12); the check is `>=`, so grouped steps stop as a block — `--to 6/7` run
through 8 (the scale-calibration block 6→7→8, which `--from` already treats
atomically because step 6's porsil reduction has no skip guard and step 7's
scales are volatile until step 8 persists them), and `--to 10/11` run through 12
(stitch). So **`--to 8` is the "find the scale factor" stop**: reduce the
standard, calibrate, apply, stop before samples. Steps 1–2 build the table first,
so it works with or without an existing table — which is exactly the "check if
porsil is in the table, else /matchruns, then reduce porsil + calibrate" flow the
user described, without needing a bespoke command.

**2 — an unknown flag ate the IPTS.** The failing input was `--till 7`: `--till`
wasn't recognised, so it was dropped and the following `7` was parsed as the IPTS,
and autopilot ran all 13 steps. Any unrecognised `--flag` is now an error, so a
typo can never silently launch the whole pipeline.

`--to` is threaded through both front ends (`app.py`, `headless.py`) and validated
(1–13, and `--to ≥ --from`). LLM routing maps the scale-factor phrasings to
`--to 8`. `tests/test_autopilot_tostep.py` (8 checks): the flag + aliases parse,
out-of-range / `to<from` / unknown-flag are rejected, and the engine actually
stops — no step-6+ commands dispatched, resume hint printed, and a full run still
reaches step 13. 217 tests.

**Files changed:** `commands/autopilot.py`, `services/autopilot.py`,
`services/llm_handler.py`, `app.py`, `headless.py`,
`tests/test_autopilot_tostep.py` (new), SKILL.md, CLAUDE.md,
`src/eqsanscli/__init__.py`.

### 2026-08-24: transmission for a displacement series, and combined `/set` (v0.25.0)

Two gaps found during real-IPTS reduction (IPTS-37828, runs 187233–187242: one
transmission `T-70.30PBD_0.25phr` and a scattering series `S-…_d0, _d2, … _d16`,
all 4m 2.5Afs 3mmsa, `_dX` = sample displacement).

**1 — `/matchruns` missed the transmission.** Matching is by sample name, and the
`_dX` suffix made every scattering name differ from the transmission's. Two
additions, both deterministic (no LLM):
- **Displacement-aware base match.** `_match_base()` strips a trailing temperature
  *and* any `_d<number>` token, so `poly_d0`, `poly_d16` and `T-poly` all key on
  `poly`. Only the numeric `_dN` convention is stripped — `_d2o` and other
  non-numeric `d` tokens are left alone (the `(?=_|$)` lookahead needs the digits
  to end the token), so D2O-like names don't collapse together.
- **Sole-transmission-per-config fallback.** If names still don't match and a
  configuration holds exactly one plain transmission run, it can only be that one
  — assign it, and warn that it "matched by configuration" so the user verifies.
  Guarded: two transmissions in a config → no guess.

The base match handles the real 187233 case cleanly (no warning); the fallback is
the safety net for series whose names share nothing.

**2 — one run as both transmission and empty beam, in one command.**
`/set <row> trans,emp <run>` now accepts several run fields separated by `,` or
`+` (run fields only — trans/bkg/bkgtrans/emp; mixing in thickness/sample/cfg is
refused rather than guessed). Clearing (`none`) works across the set too. Note
this makes it easy to set `trans == emp`, which **TBL-06** flags as an error
(transmission ÷ empty beam ≈ 1); the rule is unchanged and the capability is a
deliberate manual override, not the matcher's default.

`tests/test_matching.py` (11 checks): the displacement series resolves, the
fallback fires and is guarded, `_d2o` is protected, and the combined `/set` sets
both fields / rejects special-field mixes / clears / leaves single-field behaviour
untouched. 209 tests.

**Files changed:** `services/matching_service.py`, `commands/matching.py`,
`services/llm_handler.py`, `tests/test_matching.py` (new), SKILL.md, CLAUDE.md,
`src/eqsanscli/__init__.py`.

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

**Restyled to match the machine-physics page** (`cw-do.github.io/eqsans_mp`) on
request, by reading its actual stylesheet out of `<mp_root>/doc/index.html` rather
than guessing: the same tokens (ORNL green `#00703c`, `#0067b9` blue, the grey
scale), the same 15px Helvetica with a mono stack for anything typed, the green
masthead with tagline over a grey sub-navigation whose active tab carries a green
underline, and bordered cards with grey header rows for commands and rules.

Verified by rendering with headless chromium and **sampling the pixels** — worth
doing, because reading the screenshot by eye told me the masthead was white when
it was `rgb(0, 112, 60)` all along. The render did find two real defects: every
command showed an empty `.py` source label, because `registered_commands()` used a
line-based regex and `registry.py` imports most handlers in parenthesised
multi-line form (now parsed with the AST, 57/57 resolve), and the command count in
the page lede was hardcoded.

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

### 2026-08-21 (v0.24.2): the documentation site gains a video index

Twelve screencasts of the real tool reducing one live experiment (IPTS-38603)
are now published on YouTube, and the site links them. A new **Video tutorials**
page (`docs/pages/tutorials.md`) embeds the 3-minute overview in its playlist
context and lists all twelve — the overview plus eleven task clips — each row
linking to its own video (`watch?v=<id>&list=<playlist>`), with commands in the
tables linking through to the command reference.

The overview is a live `<iframe>` embed rather than a click-through poster: the
embed was confirmed to play over an http(s) origin, so the earlier Error 153 was
only the `file://` origin of a local preview, not a permissions block. The index
page, guide and home page cross-link the videos.

**Files changed:** `docs/pages/tutorials.md` (new), `docs/generate.py`
(`tutorials_page`, playlist/overview IDs), `docs/site.css` (`.video-frame`),
`docs/pages/index.md`, `docs/pages/guide.md`, `docs/README.md`,
`src/eqsanscli/__init__.py`.

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

### 2026-08-18 (v0.23.0): a run number is enough for `/mask create`

Asked: Mantid finds a run from its number without being told the experiment —
can `/mask create` do the same, with no `/load ipts` first? Yes, and it needs no
Mantid to do it: the SNS archive layout is fixed, so one glob locates the run.

`find_run_in_archive()` tries `/SNS/EQSANS/IPTS-*/nexus/EQSANS_<run>.nxs.h5`, then
`/SNS/EQSANS/IPTS-*/data/EQSANS_<run>.nxs` for experiments before ~2013 (surveyed
on disk: those are the two layouts in use). The filename is exact, never globbed,
so the `_ORIG.nxs.h5` copies some folders keep are not matched, and the second
pattern is only paid for when the first misses. About 0.9 s across the 1117
experiment folders on disk.

`resolve_run_file` order: an absolute path, the session's (or `--ipts`) folder,
the current folder, then the archive. The report names the experiment found —
`found in IPTS-38681 by searching the archive` — and `ipts_from_path()` reads it
back out of the path.

Verified end to end on a fresh session with `state.ipts` unset: `/mask create
186636 --dry-run` located the file, read it through Mantid and produced the plan.

**Files changed:** `services/mask_service.py` (`ARCHIVE_PATTERNS`,
`find_run_in_archive`, `ipts_from_path`, `resolve_run_file`), `commands/mask.py`
(report line, `--ipts` help), `tests/test_mask.py` (+4, 60 total), README,
SKILL, AGENT_SKILL, knowledge.

### 2026-08-18 (v0.22.3): the preview was mirrored

Reported: *"i realize that horizontal index is reversed. the correct image should
switch left and right."* Correct — v0.15.0 ordered tubes by ascending x for
display, which looked right until v0.22.2 put the tube index on the axis and
showed it running 191 -> 0 across the picture. Tube 0 sits at **+x** on this
detector, so ascending x left-to-right draws it back to front.

`ax.invert_xaxis()` on both panels: tube index now ascends left to right, and the
millimetre axis descends (+500 left, -500 right). `imshow` resets the limits it is
given, so the overlay panel is inverted again after the overlay is drawn — worth
knowing, it silently un-flipped the right-hand panel otherwise.

**Only the view is mirrored, not the coordinates.** Millimetres are Mantid's, and
they are what `--disc` and `--beam-center` are given and what `.params.json`
records, so nothing written by earlier versions changes meaning. A feature the
report puts at x = +13 mm is now drawn left of centre.

If the instrument's own convention is that x increases the *other* way, the fix is
a sign change on the coordinates rather than on the view, and would change what
`--disc 13,-55,48` means — raised with the user rather than assumed.

`render_comparison` split into `build_comparison_figure` (returns the figure) plus
a thin writer, so the orientation is testable.

**Files changed:** `services/mask_service.py`, `tests/test_mask.py` (+1, 56
total), README, SKILL, AGENT_SKILL, `knowledge/instrument-files.md`.

### 2026-08-18 (v0.22.2): the preview carries both scales

Asked for: *"when displaying (making comparison png file) display both tube
index(pixel index) and mm. tube index is useful to mask detector by tube number."*

Right — the two sets of flags speak different languages. `--disc`,
`--beam-center` and `--beam-radius` are in millimetres; `--tubes`, `--top` and
`--bottom` are in indices. The picture only carried the first.

`index_ticks()` returns tick positions in mm with the tube / pixel index sitting
at each, **looked up from the geometry** rather than computed: tube index is not
linear in x, and on the real detector it runs backwards — tube 191 sits at
x = −525 mm and tube 0 at +525. `render_comparison` adds a `twiny` (tube index,
every 16) and a `twinx` (pixel index, every 32) to both panels.

Labels are exact only at the ticks, because of the pack-of-four interleave, and
the axis label says so. To act on a tube spotted by eye, read the approximate
index and confirm against the tube list in the report or with
`--tubes <n> --dry-run`.

**Files changed:** `services/mask_service.py` (`index_ticks`, twin axes, figure
11x5 -> 12x5.4), `tests/test_mask.py` (+2, 55 total), README, SKILL,
AGENT_SKILL, `knowledge/instrument-files.md`.

### 2026-08-18 (v0.22.1): `--leak-scale` — a bigger disc over the fallen beam

Asked for directly: *"what if I want to cover the leak with larger disc?"* It was
possible already, by copying the reported position into `--disc` with a radius of
your choosing, but the position is detected — only the size is in question.

`--leak-scale <f>` multiplies the radius of each masked leak disc about its own
centre, and implies `--leak` (sizing the disc means you want it). The disc is
fitted to the broad peak, so its faint tail is what a larger one buys. On 186636,
against a plateau of 1 count:

| | masked | disc | worst unmasked pixel below the stop |
|---|---|---|---|
| (none) | 9.14% | — | 370 |
| `--leak` | 9.69% | r 48 mm | 34 |
| `--leak-scale 1.4` | 10.20% | r 68 mm | 18 |
| `--leak-scale 1.6` | 10.51% | r 78 mm | 8 |

Recorded in `.params.json` as `leak_scale`, and the report names the radius it
actually masked. `--disc` remains the way to state a disc outright.

**Files changed:** `services/mask_service.py` (`leak_scale` on `build_plan` and
`MaskPlan`), `commands/mask.py` (flag, validation, report, params, help),
`tests/test_mask.py` (+2, 53 total), README/SKILL/AGENT_SKILL, knowledge.

### 2026-08-18 (v0.22.0): the stop is measured from cross cuts

The user's own procedure, and it is better than what 0.21.0 did:

> 1) horizontal cross cut and find center -> x value  2) vertical cross cut and
> find center (deep valley) -> that's center y value.  3) then use the valley
> width (just focusing horizontal valley width in this case) as a diameter of the
> center mask.

**Why the circle fit was not good enough.** Fitting a circle to all the flare
pixels averages over the whole ring, and on run 186636 the broad gravity lobe
below the stop dragged the fitted centre 14 mm down: it reported (11.3, −4.2)
where the cuts say (12.3, 10.1). The mask therefore sat low — "not fully
satisfactory".

**Now** `beam_from_cross_cuts()`: a vertical cut (mean per pixel row over tubes
within 30 mm of the seed) gives the centre's y as the midpoint of the valley's two
walls; a horizontal cut through that y gives the centre's x and, from the wall
separation, the diameter. The wall *summit* is the rim — flare is brightest just
clear of the stop — so peak-to-peak is the width. The width is taken from the
horizontal cut only, exactly as asked: vertically the gravity-dropped beam lands
inside the shadow and makes it read narrow (69 mm against 80 mm on 186636).

Three details, each from a failure while building it:

- **Anchor on the beam, not the darkest point.** Outside the flare the plateau is
  *darker* than the filled-in shadow (1 count against 9 on 186636), so the
  minimum of the cut is 77 mm from the stop. The shadow is a local dip between two
  walls, not the darkest place around. This is what made the first attempt report
  "no valley" on two of three runs.
- **Sample per tube and per pixel row, do not bin by position.** Tubes are 5.49 mm
  apart but their index order interleaves packs of four, so binning at the pitch
  aliases — some bins take two tubes, some none — which moved the centre 5 mm.
- **Read a wall's summit over at most two bins either side.** Unbounded, the
  vertical cut's lower wall (the gravity lobe, merged with the rim flare and far
  broader) pulled the centre 6 mm down.

A side that rises onto the plateau and stays up is not a wall: that run has no
flare and is sized from the shadow as before. `fit_flare_ring` and `_fit_circle`
are removed — the cuts replace them.

| run | config | measured valley | mask | ground truth |
|---|---|---|---|---|
| 186636 | 9 m 15 Å | 80 mm at (12.3, 10.1) | r 44.0 | stop 90 mm across, centre (10, 10) |
| 186631 | 4 m 10 Å | 66 mm at (30.0, 13.4) | r 37.2 | 4 m mask made by hand is 68 mm across |
| 186104 | 4 m 2.5 Å | no flare walls → shadow | r 34.2 | hand-made 2026B mask ≈ 34 mm |

**`--leak` now masks only lobes BELOW the stop.** Neutrons fall, so the beam that
misses the stop is the beam that fell past it. The bright patch above the stop is
rim flare or the short-wavelength end of the band; it is an arc, not a blob, and
the disc drawn round it reached y +112 for a feature ending at +75. It is still
reported, with a `--disc` line to copy. On 186636 `--leak` adds 0.55% rather than
1.7%, and takes the worst unmasked pixel below the stop from 370 counts to 34
(plateau 1).

**Files changed:** `services/mask_service.py` (`cut_along_x`, `cut_along_y`,
`valley_walls`, `_summit_centre`, `beam_from_cross_cuts`; `fit_flare_ring` and
`_fit_circle` removed; `BeamStop.valley_width` replaces `ring_radius`; leak
masking restricted to below), `commands/mask.py` (report, help, `valley_width_mm`
in params), `tests/test_mask.py` (8 cross-cut tests replace the 7 ring tests, 51
total), `knowledge/instrument-files.md`, `README.md`, `SKILL.md`, `AGENT_SKILL.md`.

### 2026-08-18 (v0.21.0): the beam stop is found from the flare ring

**Problem.** On the 9 m 15 Å banjo (run 186636) `/mask create` put the stop at
(16.5, −9.5) mm with r 13.7 mm. The instrument scientist measures that stop at
**90 mm across**, centred near the middle, with the gravity-dropped direct beam
forming a large blob near (0, −50) mm. Two separate faults:

1. The largest connected `contrast < 0.6` region was a **3804 px annulus**
   spanning 385 × 376 mm — the wide (41 px) surround window used by
   `local_contrast` includes the bright beam complex, so pixels just *outside* it
   read as very dark. Its centroid sits in the hole, i.e. at the detector centre,
   which is exactly what got reported as the beam.
2. The radius came from walking outward until a ring "recovered" 75% of its
   surrounding brightness. Those rings immediately hit the bright gravity lobes,
   so it stopped at 10 mm.

**Solution — use the ring of increased intensity, not the dark patch.** As the
user put it: the stop is a dark centre surrounded by a flare, so the flare's
centre is the stop's centre and the stop is slightly smaller than the flare.

- New `fit_flare_ring()` — flare pixels (`local_contrast > FLARE_CONTRAST` 1.6)
  within `FLARE_SEARCH_MM` (150) of the shadow, fitted with an algebraic circle
  fit, five rounds of trimming to |d − r| < 30%. Restricting to the neighbourhood
  is essential: unrestricted, least squares walked to a centre 187 mm off the face
  with r 213 mm. Requires ≥ 6 of 8 octants (two lobes side by side reach five) and
  ≥ 30 px.
- The **stop edge** is the 5th percentile of the ring pixels' distance from the
  fitted centre — where the flare begins. No fudge factor: it gives 45.2 mm on
  186636 against the measured 45 mm.
- `find_beam_stop` now treats the shadow as a **seed** for that fit, and among
  dark regions discards any whose own centroid does not lie inside it — that
  single test kills the annulus (a ring's centroid is in its hole).
- Shadow sizing, used when there is no flare, is now the blob's equal-area radius
  or half its longest extent, whichever is larger. `BEAM_RECOVERY_LEVEL` deleted.
- `--beam-scale` default is now **conditional**: 1.0 for a ring fit (it measures
  the edge directly) and 1.2 for a shadow fit (a threshold stops short). Passing
  it explicitly applies either way. `BeamStop` gained `source` and `ring_radius`;
  both are reported in the output and in `.params.json` (`found_from`).
- The shallow-core warning is suppressed on the ring path, and the "no shadow
  discernible" refusal no longer vetoes a good ring fit.

**Measured against the three runs on disk:**

| run | config | result | ground truth |
|---|---|---|---|
| 186636 | 9 m 15 Å | (11.3, −4.2), r 49.3 mm, flare ring (ring r 61) | stop 90 mm across |
| 186104 | 4 m 2.5 Å | (27.8, 15.0), r 34.2 mm, shadow (no flare) | hand-made 2026B mask ≈ 34 mm |
| 186631 | 4 m 10 Å | (22.1, 17.6), r 29.4 mm, flare ring (ring r 38) | — |

Leak reporting on 186636 is unchanged and matches the user's description: discs at
(13, −55) r 48 mm and (13, 51) r 61 mm, still not masked unless `--leak` is given.

**Files changed:** `services/mask_service.py` (`fit_flare_ring`, `_fit_circle`,
centroid-containment test, extent sizing, conditional scale, `BeamStop.source`),
`commands/mask.py` (auto `--beam-scale`, estimator reported, `found_from` in
params, help text), `tests/test_mask.py` (+7 tests, 50 total),
`knowledge/instrument-files.md`, `README.md`, `SKILL.md`, `AGENT_SKILL.md`.

### 2026-08-18 (v0.20.1): `/mask create` crashed on the real path

`/mask create 186636` (no `--dry-run`) died with
`AttributeError: 'str' object has no attribute 'drtsans_version'`.

The leak-reporting loop added in 0.20.0 used `state` as the name for a per-leak
label — shadowing `_create`'s `state: SessionState` parameter — so the next use of
`state.drtsans_version`, in the call that writes the mask, hit a string.

**Why no test caught it:** every command-level test used `--dry-run`, which
returns *before* the write. The gap was the whole non-dry-run path, not one line.
`tests/test_mask.py` now exercises `/mask create` end to end with
`read_run_image`/`write_mask` stubbed, so the write path, the params file and the
leak reporting all run without needing Mantid — and asserts the params contain the
config, the leak list and `leaks_masked`.

**Also documented, in the help and the README:** `--disc` and `--beam-center`
coordinates are **millimetres from the centre of the detector** (where the
undeflected beam hits), `+y` up, face x −525…525 and y −521…521 mm. So
`--disc 13,-55,48` is 13 mm to one side and 55 mm below centre. The preview's axes
are the same millimetres.

### 2026-08-18 (v0.20.0): Back to a disc — leaks reported, masked on request

0.19.0 solved the right problem the wrong way. Feedback: *"that was too much.
Besides the extension didn't need to go up, that was over-masking. First I want to
see the centre mask created. Then we can decide whether to cover up the leak.
Usually I would have done it with two disc-shaped masks."*

All three points were fair. The capsule spanned y -145..+129 mm on run 186636 —
274 mm of a 1 m detector, extended upward as well as down, and it fused the beam
stop and the leakage into a single shape so the centre mask could not be judged on
its own. The tail-following made it worse.

**Now:** the beam mask is a **plain disc** again, always. Leakage is still detected
— that part was worth keeping — and each lobe is reported with its position and
radius, but nothing is masked unless asked:

```
Masking 4248 pixels (8.64%): beam stop at (16.5, -9.5) mm, r 13.7 mm; ...
  • direct-beam leak below the stop at (13, -55) mm, r 48 mm — not masked —
    add --leak, or --disc 13,-55,48
  • direct-beam leak above the stop at (13, 51) mm, r 61 mm — not masked — ...
```

`--leak` masks them as **one disc per lobe**, matching how they are masked by
hand; or copy the reported numbers into `--disc` to take just the lower one. On
186636: 8.6% masked by default, 10.3% with `--leak`, against 12.2% for the
capsule.

**Removed:** the `capsule_mm` shape, `y_low`/`y_high`/`is_streak` on `BeamStop`,
tail-following, and two constants. `local_contrast()` came out of `find_beam_stop`
as a named helper, and `find_direct_beam_leaks()` is now public and returns discs.

One detail kept from the exercise: a leak disc is padded by two pixels, because
local contrast is computed over a ~5-pixel window and therefore trims about that
much off a lobe's rim — without it a 20 mm lobe produced a 16.5 mm disc and 20
pixels of direct beam stayed unmasked.

### 2026-08-18 (v0.19.0): Masking direct beam that fell under gravity

Reported: automatic centre masking failed on the 9 m case (run 186636). The user
would have masked the dark disc around pixel (90, 130) *and* the bright spot just
below it — direct beam that fell under gravity.

**The physics, confirmed in the data.** Gravity drop goes as the square of the
wavelength, so across a wavelength band the direct beam lands at a range of
heights: it is a vertical *streak*, not a spot. A beam stop sized for the middle
of the band blocks the middle of the streak and lets the ends through. The
vertical profile through run 186636's beam column shows exactly that — bright
lobes of 348 and 190 counts at y ≈ +50 and −55 mm, either side of an 8-count
shadow at y ≈ +10, against a detector plateau of 5.

**Only ever looking for darkness was the flaw.** The leaked beam is what actually
ruins the data — a single unmasked direct-beam pixel spoils the low-Q bin it lands
in — and the old detector could not see it at all.

**Now**, after locating the shadow, bright patches in the beam's own column are
folded in (contrast > 3, ≥ 10 px, within 4 stop radii in x and 200 mm in y) and
the mask becomes a **capsule**: everything within the radius of a vertical
segment. Two further details were needed:

- **Contain, do not estimate.** Taking half a lobe's x-range, or its median row
  width, left the widest part unmasked — 611 counts against a plateau of 5. The
  radius now contains the detected patches by construction.
- **Follow the tails.** Local contrast saturates inside a broad bright region,
  because its own surroundings are lit, so the streak's ends read as low contrast
  and stopped the capsule short while ~23 counts per pixel remained. The tails are
  now followed until the column's mean falls back below twice the plateau.

Result on 186636: a capsule at x 16.5 mm spanning y −145…+129 mm, r 56 mm,
12.2% of the detector, with the worst unmasked pixel in the beam column down to
**4 counts against a plateau of 1** (previously 611). Runs with no leakage are
untouched: 186631 and 186104 still produce plain circles, and a test asserts a
clean stop is never turned into a capsule. `--no-leak` disables the extension.

### 2026-08-18 (v0.18.0): `--disc` for arbitrary discs, in millimetres

Asked for, together with the right question: mm or pixels?

**Millimetres**, for three reasons. Tube index is not a spatial coordinate — the
pack-of-four interleaving means a disc specified in index space would be
scattered across the face rather than round. The beam stop already uses mm
(`--beam-center`, `--beam-radius`), so one coordinate system covers both. And the
example that came with the request, `--disc 500,500,20`, only parses as mm: in
pixels the axes stop at 191 and 255, while the face runs x -525..525,
y -521..521 mm.

The one real argument for pixels was that the preview was drawn in index space,
which made mm hard to read off — so **the preview axes are now in millimetres**,
with tubes ordered by ascending x so the axis reads left to right. A position
read off the picture can be typed straight into `--disc` or `--beam-center`.

`--disc` is repeatable, validated (three numbers, positive radius), warns when a
disc falls entirely off the detector rather than silently masking nothing, and is
recorded in `params.json` as `discs_mm`. Verified: a 20 mm disc masks 1258 mm^2
against pi r^2 = 1257, centred within 1 mm of where it was asked for.

### 2026-08-18 (v0.17.0): A beam halo was masking whole tubes

Reported: a mask for run 186636 masked several entire tubes near the centre
instead of a beam disc.

**Cause.** That run is `S-banjo 9m 15A` — 112,148 counts, median **1** per pixel.
Tube health was judged from the **mean** along each tube, and at 15 Å the halo
scattered around the beam stop is broad and bright, so every tube crossing it sat
well above its peers. 29 tubes were flagged, spanning x from -58 to +102 mm — a
band straight across the centre — masking 22.4% of the detector. Blanking the
beam circle did not help: the halo extends far beyond the stop.

**Three fixes, each from a real run.**

- **Median, not mean.** A feature covering a minority of a tube's pixels no
  longer condemns it. (186636: 29 flagged → 0.)
- **A local baseline** of same-pack neighbours within ±16 tubes, so a gradient
  across the detector is not read as a fault.
- **Relative first, statistical only when counts allow.** A MAD-based z-score on
  tube medians of 0, 1 and 2 counts is meaningless — it flagged 34 tubes on
  186636 and 49 on 186631. So dead (<30% of local baseline) and hot (>3x) are
  tested by ratio at any count level, while the `--tube-sigma` test applies only
  where the baseline exceeds 20 counts *and* the tube is off by more than 25%.
  10-20% gain variation is normal and is what the sensitivity map corrects; the
  earlier version flagged 8 such tubes on the healthy 186104.

Where a run cannot support the test at all — 186636's baseline is ~1 count — no
tubes are flagged and the reason is printed, rather than masking noise.

Verified across three real runs: 186636 (9 m 15 Å, median 1) → no tubes, 8.6%
masked, with the note; 186631 (4 m 10 Å, median 4) → exactly tube 145, which is
100% dead; 186104 (4 m 2.5 Å, median 90, healthy) → none.

### 2026-08-18 (v0.16.2): `--top` / `--bottom` semantics documented

Asked how to set the tube-end bands, and the help did not say enough:

- they are **counts of pixels**, not indices — `--bottom 11` masks pixels 0-10,
  `--top 11` masks 245-255, together reproducing the `MASKED_PIXELS =
  '1-11,246-256'` convention from each cycle's `prepare_sensitivity.py`;
- an explicit value **bypasses the 11-pixel floor**, so `--top 0 --bottom 0`
  disables the bands, which nothing said;
- `--bottom` is the low-pixel-index end (-y), the band at the bottom of the
  preview image, since that is plotted with `origin="lower"`.

**The machine-physics mask tool names these the other way round** — its
`detect_bands` counts `top` from pixel index 0, and its 2026B `params.json`
records `top: 12, bottom: 11` for the mask whose shapes are rows 0-11 and
245-255. Ours is the physically-correct sense and matches our own preview, so the
naming stays; the difference is now called out in the help, the README, the
troubleshooting table and `params.json`, which records `band_convention` so a
stored mask states which sense it used.

### 2026-08-18 (v0.16.1): `/mask` documentation

`/mask` had grown three behaviours worth explaining — refusal, the shallow-shadow
warning, and the explicit `--beam-center` / `--beam-radius` overrides — while its
help was still the flag list written when the command was first added, and the
README section still described the beam as an index-space ellipse, which
v0.15.0 disproved.

- **In-CLI `/mask`** now groups options by what they control, states units and
  defaults, gives five worked examples, and ends with an *if it looks wrong*
  section mapping each symptom to its cause and fix. (`[options]` in the first
  line needed escaping — Rich was reading it as markup and dropping it.)
- **README** gained: which run to use and why (counting statistics, wavelength),
  what each of the three components does, when detection refuses and why that is
  deliberate, a full option table with units and defaults, how to review the
  preview, a troubleshooting table, what the three output files are, and the
  detector-geometry note that explains why the beam mask is computed in mm.
- **SKILL.md / AGENT_SKILL.md** rewritten to match, including the refusal.
- **`knowledge/instrument-files.md`** records the local-contrast method and the
  statistics/wavelength constraints.
- **LLM reference** learns the new flags and, importantly, that a refusal is
  correct behaviour: do not work around it by loosening thresholds, and never
  invent a beam centre or radius.

### 2026-08-18 (v0.16.0): Beam-stop detection on a dim run

Reported: a mask built from run 186631 came out far too big and off-centre,
while the machine-physics mask maker had been fine.

**Cause.** That run (`S-banjo 4m 10A`, IPTS-38681) has 236,593 counts, a median
of **4 per pixel** — against 4,025,003 (median 90) for the run I had tested on.
The detector thresholded at `counts < 0.3 x median` = 1.2 counts, and Poisson
noise at mean 4 puts ~9% of the whole detector below that. 418 scattered noise
pixels went into a single-pass centroid, giving a centre 45 mm off and a radius
of **69.7 mm** from the pixel count — precisely "too big and not centred".

**Also true:** at 10 Å the banjo's halo around the stop is bright, so the core is
only ~2x darker than plateau (0.54 local contrast) versus 12x (0.04) on the
bright 2.5 Å run. No global threshold separates those two cases.

**Now.** The shadow is found by **local** contrast — the image smoothed over
~5 pixels against ~41 — so a region qualifies by being darker than *its own
surroundings*, which works at both count levels and through a halo. The largest
connected blob is taken, its centroid refined over four rounds (the same idea
the machine-physics maker uses, which is what makes that one robust), and the
radius measured from **where the shadow ends** — the smallest radius at which
the surrounding ring has recovered 75% of its brightness — rather than from a
threshold-dependent pixel count.

**It now refuses rather than guesses:** no blob at all, a blob under 8 pixels, a
core less than 1.25x darker than its surroundings, a radius over 60 mm, or a
centre more than 60% of the way to an edge — each returns no beam mask and says
why. Pure Poisson noise is refused, as a test asserts.

**When detection is honest but limited**, it says so: on 186631 it finds the
centre correctly (26.6, 11.6) mm but warns that the shallow core means the
apparent size understates the real stop, and points at `--beam-radius`.

**New:** `--beam-center <x>,<y>` and `--beam-radius <mm>` state the beam
explicitly, in millimetres, used verbatim.

### 2026-08-17 (v0.15.1): `--beam-pad` speaks y-pixels again

0.15.0 moved the beam stop into millimetres, correctly, and moved `--beam-pad`
into millimetres with it — which broke the convention the machine-physics mask
tool established: its SKILL.md says outright "`--beam-pad` is in y-pixels", and
the 2026B mask was made with `beam_pad: 1.0` meaning one pixel. Someone用 to that
tool typing `--beam-pad 3` here would have got 3 mm, about three quarters of a
pixel, instead of three pixels.

The circle stays physical; only the knob's units revert. `pad` is now in pixels
along a tube and converted with the pitch measured from the real positions
(4.090 mm), so the two tools agree on what a number means. `params.json` records
`beam_pad_units: "y-pixels"` so a stored mask says which convention it used.

### 2026-08-17 (v0.15.0): The beam stop is a circle in millimetres, not in index space

Prompted by the question "did you consider that the number of x-pixels and
y-pixels differ for the same square geometry?" — I had, but only halfway, and
checking it against the instrument definition showed the reasoning was wrong.

**What I assumed.** The detector is ~1 m square with 192 tubes × 256 pixels, so a
physical circle is an ellipse in index space with `ry/rx = 256/192 = 1.333`.

**What the geometry actually says.** Measured from `LoadEmptyInstrument`
(remembering spectrum 0 is a monitor — 49153 spectra, 49152 pixels): pixels step
**4.09 mm** along a tube, but consecutive tube *indices* are **10.94 mm** apart in
x while physical neighbours are **5.49 mm** apart. The index order interleaves
sub-banks in packs of four — physical order by x is 0, 4, 1, 5, 2, 6, 3, 7, 8,
12, … — so **x is not monotonic in tube index at all**. The premise that index
maps linearly to position is false, which makes the aspect-ratio question moot.

**How wrong it was.** Run 186104's beam shadow is physically round (49.5 mm wide
× 49.0 mm tall) and touches tube indices 83–95 — but only 10 of those 13, with
84, 85, 86 physically elsewhere. The index-space ellipse agreed with a true disc
of the same area only **87.4%**: it missed 23 px of the disc and masked 21 px
outside it, covering a region 82.6 × 69.5 mm.

**Now.** `read_run_image` dumps the real pixel positions in the same Mantid pass
that reads the counts. The beam stop is found and masked as a circle in
millimetres (`{"type": "circle_mm", …}`), its radius derived from the shadow's
**area** (`npix × pixel_area = πr²`; a median distance would overestimate by √2
on a filled disc). `--beam-scale` multiplies the radius, `--beam-pad` adds
millimetres. The masked region is now 60.6 × 61.3 mm — round. Tube-end bands stay
in index space, correctly: pixel index *is* linear in y.

Comparison images are now plotted in physical tube order, which removes the
four-tube striping that was an artifact of index ordering, and shows the beam as
the round blob it is.

Two tests pin this: the masked area matches `πr²` within 15%, and the beam mask
is deliberately asserted to be *non-contiguous in tube index* — the signature
that it is spatial rather than index-space.

### 2026-08-17 (v0.14.1): `/mask --beam-pad` distorted the beam circle

Found while explaining the option. The beam stop is masked as a *physical*
circle, an ellipse in index space with `ry/rx = 256/192`, but `--beam-pad` added
its margin to `ry` alone — so padding stretched the mask vertically instead of
growing the circle: 13% off aspect at the default `pad 1.0`, 39% at 3, 77% at 6.
(The phrasing "pad is in y-pixels" was carried over from the machine-physics
skill and applied to one axis only.)

Padding now adds `pad` pixels on y and the matching `pad / aspect` tubes on x, so
the region stays circular on the detector face at every setting; `--beam-scale`
already did. The help text says which knob does what. Two tests pin the aspect
ratio across both knobs and check that `--beam-pad 4` really means four pixels.

### 2026-08-17 (v0.14.0): `/mask create` — build a mask inside eqsanscli

Masks were the one calibration input eqsanscli could resolve but not produce: if
no mask existed, v0.11.0 told the user to make one and stopped. Making one meant
the `eqsans-mask` skill in the machine-physics folder, which needs the `sansdir`
library and writes into a cycle folder — wrong shape for a user reducing their
own experiment.

**`services/mask_service.py`** decides what to mask, in plain numpy, so it is
testable without Mantid:

- **beam stop** — the low-count blob near the centre, found from the *deficit*
  inside the central half of the detector so a bright sample cannot drag it. It
  is a physical circle, which on this detector is an ellipse in index space
  (`ry/rx = 256/192`); `--beam-scale` and `--beam-pad` tune it.
- **edge bands** — measured from where the along-tube profile falls below half
  the plateau, floored at 11 pixels because EQSANS has masked pixels 1-11 and
  246-256 for years (`MASKED_PIXELS` in each cycle's `prepare_sensitivity.py`).
- **deviant tubes** — robust (MAD) comparison *within a front/back group*.

**The tube grouping was wrong everywhere it was written down.** The machine-physics
skill says "odd tubes are compared to odd, even to even". Measured on run 186104,
tubes alternate front/back in **packs of four**: grouping by `(tube // 4) % 2`
gives a mean MAD of 2.72, against 19.85 for parity and 20.06 for no grouping, and
the high/low pattern matches 4-on/4-off across all 192 tubes exactly
(fraction 1.000). Parity grouping leaves the two populations mixed, inflating the
spread ~7x — which is why auto tube detection flagged nothing at any threshold.
The four-tube striping is plainly visible in the generated comparison PNG.

**Detector ordering was verified, not assumed:** workspace index =
`tube * 256 + pixel`. Reshaped that way the mean profile along the pixel axis
shows the dead ends (edge/mid 0.23); the transpose shows no structure (0.93).
`reshape_counts` uses that same test at runtime and falls back with a warning
rather than masking the wrong pixels.

**Mantid contact is minimal and generated.** Two short scripts — read the counts,
write the mask — run under the `drtsans` command exactly as `/reduce` does.
Nothing outside `mask_service.py` is imported by them, and the written file is
verified by reading it back through `Load` + `ExtractMask`, the path drtsans
itself uses. The workspace is integrated before saving, so the file is 12 MB
rather than the ~69 MB of a full save, and still reads back identically.

**Naming is the discoverability mechanism.** `mask_<config>_<run>.nxs` with the
configuration read from the run's own logs (`detectorZ`, `wavelength`,
`frequency`) and `.` written as `o` — `mask_4m2o5a_186104.nxs` — is exactly what
`instrument_files._parse_mask_tokens` reads back, so a mask built in the working
folder is picked up by `/matchruns` and `/instrument` with no further action. A
test asserts that round trip for five configurations.

**Verified end to end** on run 186104 (the 2026B banjo): 4380 pixels masked,
read back as 4380 through drtsans's own path, and the resolver then selects it
for `4m2.5a` while leaving `4m10a` to fall through to the cycle default.
Against the hand-made 2026B mask for the same run, the beam centre agrees to
0.1 pixel (90.8/131.3 vs 90.7/131.2); that mask additionally carries tube 146,
added manually — in this run tube 146 reads *higher* than its neighbours, and its
known fault is a dead segment at low pixel numbers rather than a whole-tube
deficit. Auto-detection is whole-tube; `--tubes 146` covers the rest.

**Files:** `services/mask_service.py` (new), `commands/mask.py` (new),
`tests/test_mask.py` (new, 21 checks), `commands/registry.py`,
`services/llm_handler.py`, `app.py`, `knowledge/instrument-files.md`,
README/SKILL/AGENT_SKILL.

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
