# EQSANS CLI — Agent Integration Skill

You are an agent that controls eqsanscli, a SANS data reduction tool at SNS/ORNL.
You communicate with it by sending `/commands` to a headless subprocess and reading
JSON responses. This document teaches you everything you need to operate it.

---

## How to Connect

### Step 1: SSH into analysis server

```bash
ssh analysis.sns.gov
```

### Step 2: Navigate to the IPTS workspace

The user will tell you the IPTS number. The workspace is always at:
```bash
cd /SNS/EQSANS/IPTS-<number>/shared/
```

You may create a subdirectory for this reduction session (e.g., `mkdir reduction && cd reduction`),
or work directly in `shared/`. This directory becomes the working directory — output files,
session state, and saved tables are stored here.

### Step 3: Copy and launch eqsanscli-headless

```bash
cp /SNS/EQSANS/shared/script/eqsanstools-cli/eqsanscli-headless ./
./eqsanscli-headless
```

The script activates the correct Python environment and starts eqsanscli in headless mode.
You are now connected — send `/commands` to stdin and read JSON responses from stdout.

### Protocol

- **Send:** one command per line to stdin (e.g., `/load ipts 35884\n`)
- **Receive:** one JSON object per line from stdout:
  ```json
  {"success": true, "message": "Loaded 120 runs", "data": null}
  ```
- **Progress:** long-running commands (`/reduce`, `/autopilot`) stream progress lines to stderr prefixed with `progress:`
- **Session:** state is auto-saved after every command. On restart, previous session is auto-resumed.

### Response Schema

Every response is a JSON object with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | `true` if command succeeded |
| `message` | string | Human-readable result or error message |
| `data` | object or null | Structured data (see Data Types below) |

### Data Types

| `data.type` | When | Key fields |
|-------------|------|------------|
| `catalog` | `/show catalog` | `rows`: list of run objects, `ipts`: number |
| `working_table` | `/show table`, `/matchruns` | `rows`: list of row objects |
| `config_table` | `/show config <id>` | `rows`: list of param objects, `config_id` |
| `preset_list` | `/show presets` | `rows`: list of preset objects |
| `reduction_complete` | `/reduce` | `total`, `success`, `failed`, `results`: list |
| `autopilot_complete` | `/autopilot` | `ipts`, `log`: list of progress messages |
| `stitch_table` | `/stitch show` | `groups`: list of stitch group objects |
| `image` | `/plot --save` | `path`: saved file path |
| `null` | Most set/remove commands | Result is in `message` only |

---

## Core Workflow

When a user asks you to reduce an experiment, follow this workflow.
Always verify each step before proceeding to the next.

**IMPORTANT: Always prefer `/autopilot` over the manual path.** Autopilot handles
loading, matching, preset application, reduction, calibration, stitching, and plotting
automatically. Use the manual path ONLY when the user needs fine-grained control that
autopilot flags cannot express (e.g., setting individual row parameters, custom config
tweaks, or multi-step table editing).

### Quick Path (one command) — USE THIS BY DEFAULT

```
/autopilot <ipts>
/autopilot current              # use current session IPTS/catalog (preserves /reclass overrides)
/autopilot 35884 --continue     # reduce only NEW runs, reuse saved calibration/configs
/autopilot --continue           # infer IPTS from saved session in outputdir
```
Options (all composable, work with `<ipts>`, `current`, and `--continue`):
- `--thickness <cm>` — set thickness for all rows (default 0.1)
- `--bkg <sample>` — use named sample as background (config-aware). The bkg sample itself gets NO background subtraction (e.g., banjo's bkg fields stay empty)
- `--samples <a,b>` — keep only these samples (+ porsil)
- `--exclude <a,b>` — remove these samples
- `--config <id>` — reduce only this configuration (e.g., `8m12a`)
- `--standard <name>` — use named sample as calibration standard (default: auto-detect porsil/porasil)
- `--force` — re-reduce all rows, ignoring done/modified status
- `--fresh` — force a clean catalog reload + table re-match (ignores in-memory state). Does NOT clear `/set config` overrides
- `--from <N>` — skip steps 1..(N-1) of the 13-step pipeline (requires catalog + working table already in session)

**Execution order:** thickness → bkg → samples → exclude → config.
Setup (thickness, bkg) applies to the full table first, so all rows get correct
values. Then filters (samples, exclude, config) trim down to what gets reduced.

Examples:
```
/autopilot 35884 --exclude Y5 --bkg emptyticell
/autopilot 35884 --config 8m12a --thickness 0.2
/autopilot 35884 --samples Bi1,Bi2 --bkg banjo
/autopilot 35884 --bkg emptyticell --exclude Y5,Y6 --config 4m10a --thickness 0.15
```

This handles everything automatically — including preset application, calibration,
stitching, and plotting. Skip to "Sharing Results" below.

**"Reduce only porsil"** → `/autopilot 35884 --samples porsil`
**"Reduce only 8m config"** → `/autopilot 35884 --config 8m12a`
These are NOT reasons to use the manual path. Use autopilot with flags.

### Manual Path (only when autopilot flags are insufficient)

#### Step 1: Load Catalog

```
/load ipts <number>
```

**Check:** `success` is `true` and message contains run count.
**If failed:** ONCat may be down. Tell the user.

#### Step 2: Match Runs

```
/matchruns
```

**Check the message for match counts:**
```
Transmission matched: 48/50
Background matched: 50/50
Empty beam matched: 45/50
```

**Decision tree:**

- All N/N → proceed to Step 3
- Missing transmission → `/set --sample <name> trans <run>` (find run from catalog)
- Missing background → `/assign bkg <sample_name>` (this is the PREFERRED command — it handles config matching automatically)
- Missing empty beam → `/set <row> emp <run>`
- Unwanted rows → `/remove --sample <name>`

**To find the right run number:** Send `/show catalog` and search the data for runs matching the needed type (S- prefix = scattering, T- prefix = transmission) and same configuration.

#### Step 3: Apply Presets — MANDATORY, DO NOT SKIP

```
/apply preset auto
```

**This step is required.** Without presets, reduction parameters (qmin, qmax, numqbins,
sensitivity files, dark current, flux files, etc.) are missing or wrong. Reduction will
fail or produce garbage output.

**Check:** message shows which presets matched each config.
If any config shows "no matching preset found", tell the user — they may need to provide parameters.

#### Step 4: Set Output Directory

```
/set outputdir /SNS/EQSANS/IPTS-<number>/shared/output/
```

#### Step 4b: Calibrate with Porsil (if porsil is available)

If the working table contains porsil samples, calibrate absolute scale
before reducing the real samples:

```
# Reduce porsil with scale=1.0 first
/set config 4m10a standardabsolutescale 1.0
/set config 2.5m2.5a standardabsolutescale 1.0
/reduce --sample porsil

# Calibrate AND auto-apply scale factors in one step
/calibrate porsil_4m10a_Iq.dat --applynow
/calibrate porsil_2.5m2.5a_Iq.dat --applynow
```

`--applynow` parses the config ID from the filename (e.g., `porsil_4m10a_Iq.dat` → `4m10a`),
applies the scale factor to that config, and marks affected rows as "modified" so they'll
be re-reduced.

If NO porsil is in the working table, skip this step — the preset's
`standardabsolutescale` will be used as the fallback.

#### Step 5: Reduce

```
/reduce all
```

This re-reduces porsil too (status auto-reset to "modified" after scale changes).
If you want to skip already-reduced porsil, use `/reduce --sample <name>` for specific
non-porsil samples, or just accept the small overhead.

**Check `data.results`** — each entry has `status: "done"` or `status: "error"`.
If any failed, report the error messages to the user.

#### Step 6: Stitch (if multiple configs)

```
/stitch build
/stitch set all target 4m10a    # usually the lowest-Q config
/stitch set all overlap auto    # auto-computes centered overlap, widens until >=2 pts per profile
/stitch run
```

Or use `/stitch smart` for automatic quality analysis (recommended).

**Preset overlaps:** `/stitch smart` uses predefined overlap ranges for known config
pairs (e.g., `4m10a↔2.5m2.5a` → `[0.05, 0.06]`) from `preset_configs/stitch_overlaps.json`,
falling back to the auto-overlap algorithm for unknown pairs. The smart output shows
`(preset)` or `(auto)` next to each overlap pair.

**30Hz frame-skipping:** Rows with `frequency=30` produce two output files per run:
`{sample}_{config}_frame_0_Iq.dat` (low-Q) and `{sample}_{config}_frame_1_Iq.dat`
(high-Q). Both `/stitch build` and `/stitch smart` auto-detect these and treat them
as separate stitch entries. The `frame0↔frame1` preset overlap (`[0.05, 0.06]`) is
auto-applied.

**Config ordering:** Stitch groups are auto-sorted low-Q → high-Q (larger distance first,
longer wavelength first within same distance). Example order: `8m12a → 4m10a → 2.5m2.5a`.
The stitch algorithm requires this ordering.

**Default target priority** (when group is built):
1. `4m10a` if present (standard low-Q reference)
2. Any `8m*` config
3. `4m2.5a`
4. `2.5m2.5a`
5. First config (lowest-Q)

**The target can be any config** — the auto-overlap algorithm ensures sufficient
data points regardless. Override with `/stitch set <idx|sample|all> target <config_id>`.

**Merged filename:** `merged_{sample}_{config1}_..._{configN}_Iq.txt` with configs
in low-Q → high-Q order (e.g., `merged_porsil_8m12a_4m10a_2.5m2.5a_Iq.txt`).

#### Step 7: Plot

```
/plot *_Iq.dat --save all_iq.png
/plot merged_*.txt --save stitched.png
```

### Sharing Results

To share plots or data files with the user:
```
/share *.png
/share merged_*.txt
```

This returns a here.now URL (anonymous, expires in 24h). Send this URL to the user
so they can view the results.

### Emailing Results

To zip and email data files directly:
```
/zipnsend user@ornl.gov                           # merged*.txt from outputdir
/zipnsend user@ornl.gov --pattern "*_Iq.dat"      # all Iq files
/zipnsend user@ornl.gov --pattern "*.png"          # plot images
/zipnsend user@ornl.gov --subject "IPTS-38397"     # custom subject
```

Uses `mailx`/`mail` on the server. Max 25 MB (suggests `/share` if larger).
When the user asks to "send", "mail", or "email" data to someone, use `/zipnsend`.

---

## Command Reference

### Row / Selector Resolution

Many commands accept a `<row>` or `<idx|sample|all>` argument. Resolution order:
1. `all` keyword → all rows/groups
2. Try as **integer index** first (row index or stitch group index)
3. Fall back to **run number** or **sample name** match

If a sample name is a bare integer (e.g., `"3"`), it will be interpreted as an index.
Use `--sample 3` to force sample-name matching where available (`/set --sample`,
`/remove --sample`, `/stitch removerow --sample`).

Accepted formats for `<row>`: index (`3`), run number (`172815`), range (`1-5`, `1,3,5`), or `all`.

### Sample Name Matching

`--sample` flags use exact match by default (case-insensitive). Add `*` for wildcard:
- `empty` → matches only "empty"
- `empty*` → matches "empty", "emptycupbox"
- `*3b*` → matches "S-3b", "S-3b-2"

### Catalog & Loading

| Command | Purpose |
|---------|---------|
| `/load ipts <N>` | Fetch experiment catalog from ONCat (REPLACES current catalog) |
| `/refresh catalog` | Re-fetch current IPTS catalog while preserving `/reclass` overrides; reports new runs |
| `/show catalog` | Display all runs with metadata |
| `/show ipts` | Show current IPTS number |
| `/list ipts *` | List all EQSANS experiments |
| `/list ipts <text>` | Search experiments by title |

### Working Table

| Command | Purpose |
|---------|---------|
| `/reclass <runs> <class>` | Override run classification. Classes: scatt, trans, bkg, bkgtrans, empty, emptyscatt, sample, ignore (aliases i, n) |
| `/reclass --sample <name> <class>` | Reclass all runs matching sample name (e.g. `--sample BkgG sample`, `--sample banjo i`) |
| `/matchruns` | Auto-match trans/bkg/empty runs using `run_class` from catalog. REBUILDS table |
| `/matchruns --update` | Append new scattering runs only; preserves status=done rows. Use after `/refresh catalog` |
| `/show table` | Display full working table |
| `/show table --sample <name>` | Filter view by sample name |
| `/assign bkg <sample>` | Set background for ALL rows (config-aware, sets bkg+bkgtrans) |
| `/set <row> <field> <value>` | Set a field: trans, bkg, bkgtrans, emp, thickness |
| `/set <row> <field> none` | Clear a field |
| `/set --sample <name> <field> <value>` | Bulk set by sample name |
| `/remove <row>` | Remove rows |
| `/remove --sample <name>` | Remove by sample name |
| `/remove all --keep <name>` | Remove all except named sample |

### Configuration

| Command | Purpose |
|---------|---------|
| `/config list` (alias `/list configs`) | List configs in the table + stored extras (clones) |
| `/config clone <src> <dst>` | Copy a config to a new name (editable independently). `<dst>` must contain `<src>`'s config ID |
| `/config rows <id>` | List rows referencing `<id>` |
| `/show config <id>` | Show all parameters for a config |
| `/set config <id> <param> <value>` | Set a config parameter |
| `/set config all <param> <value>` | Apply to every config + sticky default for future ones |
| `/set <row> cfg <name>` | Reassign a row to a different (typically cloned) config; `none` clears (aliases: `config`, `configuration`) |
| `/set --sample <name> cfg <new>` | Bulk-reassign rows matching `<name>` |
| `/instrument show` | Calibration set per config: dark, flood, flux, detoffset, scalecomp, samoffset + source cycle |
| `/instrument list [run]` | Cycle inventory and what a given run resolves to |
| `/instrument apply [--force]` | Re-resolve now; `--force` overrides `/set config` values |
| `/instrument pin <cycle>` / `/instrument unpin` | Freeze to one cycle (reproducing old work) / release |
| `/instrument off` / `/instrument on` | Disable/enable automatic resolution |
| `/instrument check` | Verify referenced calibration files still exist |
| `/apply preset auto` | Auto-match closest preset to each config |
| `/apply preset <name> <config_id>` | Apply specific preset |
| `/set outputdir <path>` | Set output directory (propagates to all configs) |
| `/set drtsans <version>` | Set drtsans version: default, dev, qa |

Config IDs: `4m10a`, `2.5m2.5a`, `8m12a`, `4m10a30hz` (distance + wavelength + frequency)

**Masks** resolve per configuration: `mask*.nxs` in the folder eqsanscli was
started in → `/SNS/EQSANS/IPTS-<current>/shared/` → the cycle's
`<cycle>_mp/masks/*mask.nxs` default. Matched on the distance and wavelength in
the filename (`maskWS4m10A.nxs` → `4m10a`, `maskWS4m2p5A_FS.nxs` → `4m2.5a`); a
mask naming a different distance/wavelength is never borrowed. Never a mask from
another IPTS — unreadable to other users. `/matchruns` and autopilot print the
mask chosen per config; if none is found they name every folder searched and ask
you to create one and set it with `/set config <id> maskfilename <file>`.

**Instrument calibration files are resolved automatically — do not hand-set them.**
`sensitivityfilename`, `darkfilename`, `beamfluxfilename`, `detectoroffset`,
`scalecomponents.detector1` and `sampleoffset` come from
`/SNS/EQSANS/shared/NeXusFiles/EQSANS/<cycle>_mp/`, chosen by run number at
`/matchruns` and in autopilot (Step 4c):

- **Cycle** = newest whose calibration campaign started at or before the run;
  the whole set comes from that one cycle.
- **Sensitivity** follows the detector distance: 1.3 m → `1o3m`, 2.0/2.5 m →
  `2o5m`, 4 m *and anything longer* → `4m`. Preference within a cycle:
  `thinPMMA`, then undecorated tag, then highest run.
- **Never invented**: no AgBe values for runs before 2026A, no flux from more
  than one cycle back — the existing value stays and the reason is reported.
- A `/set config` value is never overwritten (reported as *kept*); use
  `/instrument apply --force` to override. Resolved values show as
  `mp:<cycle>` in `/show config`.
- `/instrument pin <cycle>` reproduces an earlier reduction; `/instrument off`
  hands full control back to the presets.

**Per-row variant workflow** (when only some rows at the same physical config need different params):

```
/config clone 4m10a 4m10a_v2
/set --sample MySample cfg 4m10a_v2
/set config 4m10a_v2 maskfilename mask_v2.nxs
```

`cfg` is the canonical row-field name (aliases: `config`, `configuration`).
The cloned config has its own entry in `state.configurations`; rows assigned to it
look up params there, while other rows at `4m10a` continue using the original.

Constraints (all enforced, with an explanatory error):

- `<dst>` must contain `<src>`'s config ID — `4m10a_v2`, `4m10a-mask2`,
  `porsil_4m10a`. `mask2` is rejected. Preset matching, cycle-file discovery and
  stitch ordering recover the physics from the name.
- A row only accepts a config with matching physics: `/set 3 cfg 4m10a_v2` fails
  when row 3 is `8m10a`.
- Output filenames are unaffected: always `<sample>_<physical config>_Iq.dat`.
  Cloned configs change reduction parameters, not file naming — so stitch
  grouping, `merged_*` outputs and `--continue` discovery are unchanged.
- Clones survive `/autopilot` even while unassigned; a `/set config` typo that
  names a nonexistent plain config ID is still cleaned up.

**Empty beam is mandatory.** It supplies the beam centre (`beamCenter.runNumber`)
as well as the empty transmission, so `/reduce` refuses up front for any selected
row without one, naming the rows and configurations and how to fix them. Missing
transmission or background is a warning only. Escape hatches:
`/reduce <rows> --skip-missing` (reduce the valid rows) and `/reduce <rows> --force`
(send them to drtsans anyway). `/autopilot` checks the same thing at Step 3 and
skips unreducible rows at reduction time.

**Masks:** `/mask create <run>` builds one from a uniformly illuminated run
(banjo, flood, empty cell) and writes `mask_<config>_<run>.nxs` into the current
folder, named so the resolver finds it automatically, plus a `_compare.png` to
review and a `.params.json` recording how it was made. It masks the beam stop
(masked as a circle in millimetres against real pixel positions), the low-response
bands at both tube ends, and tubes deviating within their front/back pack of four.

The stop is measured from **cross cuts**, as it would be by hand: a vertical cut
gives the centre's y (the deep valley), a horizontal cut through it gives the x,
and the horizontal valley width — wall summit to wall summit — is the diameter.
That survives a shadow filled in by halo or by gravity-dropped beam: at 9 m and
15 Å it gives 80 mm against a stop 90 mm across, and at 4 m 66 mm against a 68 mm
hand-made mask. Runs whose cuts have no flare walls fall back to the shadow
itself, grown slightly; the report says which was used. Counting statistics still
matter — ~90 counts/pixel is comfortable, ~4 is marginal. When neither estimator
is credible the beam is **not masked** and the reason is printed; `--beam-center <x>,<y>` and
`--beam-radius <mm>` state it explicitly. `--leak` also masks the gravity-dropped beam below the stop, one disc per lobe. `--dry-run` previews without writing,
`--tubes a,b` adds known-bad tubes (auto-detection is whole-tube, so a dead
*segment* averages out), `--tube-sigma` tunes sensitivity. `/mask list` shows what
is discoverable. Needs drtsans for the Mantid read/write.

### Reduction

| Command | Purpose |
|---------|---------|
| `/reduce <row>` | Reduce selected rows |
| `/reduce --sample <name>` | Reduce only rows matching sample name (use `*` for wildcard) |
| `/reduce --new` | Reduce only rows whose status is not `done` (newly added, modified, or errored) |
| `/autopilot <ipts> [options]` | Full automated pipeline (see Quick Path above for all options) |
| `/autopilot current [options]` | Use current IPTS/catalog from session (preserves `/reclass`) |
| `/autopilot <ipts> --continue` | Reduce only NEW runs, reuse saved calibration/configs |
| `/autopilot --continue` | Continue from saved session in outputdir |
| `/autopilot <ipts> --standard <name>` | Use named sample as calibration standard (default: porsil) |
| `/export script [file]` | Export standalone Python script |

### Stitching

| Command | Purpose |
|---------|---------|
| `/stitch build` | Build stitch table from reduced files |
| `/stitch show` | Display stitch table |
| `/stitch smart` | Auto-analyze and stitch (recommended) |
| `/stitch set <idx\|sample\|all> target <config_id>` | Set normalization target |
| `/stitch set <idx\|sample\|all> overlap auto` | Auto-detect overlap Q ranges (widens until >=2 pts per profile) |
| `/stitch run [sample]` | Execute stitching |
| `/stitch removerow <idx\|all\|--sample name>` | Remove stitch group(s) |
| `/stitch removeconfig <idx\|all> <config_id>` | Remove a config from group(s) |
| `/stitch reorder <idx\|all> <c1,c2,...>` | Reorder configs in group(s) |

### Data & Plotting

| Command | Purpose |
|---------|---------|
| `/list iq` | List reduced I(Q) files |
| `/plot <pattern> [flags]` | Plot data |
| `/share <pattern>` | Upload files, get 24h URL |
| `/zipnsend <email> [options]` | Zip files and email (--pattern, --dir, --subject) |
| `/confirm [ipts]` | Confirm IPTS data reduction complete (--comment) |

Plot flags: `--save <path>`, `--loglog`, `--linlin`, `--kratky`, `--guinier`, `--porod`, `--noerror`, `--title <text>`

### Session

| Command | Purpose |
|---------|---------|
| `/continue` | Resume previous session |
| `/session save [name]` | Save session (name optional) |
| `/session load <name>` | Load named session |
| `/save table [name]` | Save working table to disk |
| `/load table [name]` | Load table or list saved tables |

---

## Re-reduction and Status Tracking

Row status values: `ready` → `reducing` → `done` | `error` | `modified`

**Auto-modified status:** When you change a reduction-relevant parameter on a "done"
row, the status automatically resets to `modified`:
- Row fields: `/set` or `/assign bkg` changes trans, bkg, bkgtrans, emp, thickness
- Config parameters: `/set config` or `/apply preset` changes any config param

Autopilot treats `modified` rows the same as `ready` — they will be re-reduced.
Rows with status `done` are skipped (already reduced with current parameters).

**If you need to force re-reduction** (e.g., drtsans was updated, or you want
different output), use `--force`:
```
/autopilot 35884 --force
```

**You do NOT need `--force` when:**
- You changed background with `/assign bkg` → rows auto-reset to `modified`
- You changed a config param with `/set config` → rows auto-reset to `modified`
- You applied a preset with `/apply preset` → rows auto-reset to `modified`

---

## Error Recovery

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `/matchruns` shows missing trans/bkg/emp | Runs misclassified or don't follow naming convention | `/show catalog` to check Class column; `/reclass <runs> scatt` or `/reclass <runs> sample` to fix, then `/matchruns` |
| `/matchruns` warns multiple empty beams or bkg per config | Multiple runs classified as same role | User should pick one; use `/set <row> emp <run>` or `/assign bkg <sample>` |
| `/reduce` fails for some rows | Check `data.results` for `status: "error"` | Fix missing fields with `/set`, re-reduce failed rows |
| Autopilot skips rows (status "done") | Parameters changed but status not reset | Should auto-reset; if not, use `--force` |
| "No scattering runs found" | Empty catalog or wrong IPTS | Verify IPTS number, `/show catalog` |
| Preset not found | No matching preset in preset_configs/ | `/show presets` to list available, apply manually |
| Bad stitch overlap | Wrong target or overlap range | `/stitch set all overlap auto` (auto-widens to ensure >=2 pts per profile) |
| Stitch "insufficient Q values" | Overlap window too narrow for sparse data | Should not happen with auto-overlap; if manual, widen the Q range |
| Wrong output directory | outputdir not propagated | `/set outputdir <path>` re-propagates to all configs |

---

## Configuration Matching Rule

Every run belongs to a config (e.g., 4m10a, 2.5m2.5a). When assigning background,
transmission, or empty beam, the assigned run MUST be from the SAME config as the target row.

**For background:** Always use `/assign bkg <sample_name>` — it handles config matching automatically.

**For transmission/empty beam across multiple configs:** Use per-row `/set` commands:
```
/set <row_run> trans <trans_run_same_config>
```

**When there's only one config:** `/set --sample <name> trans <run>` is fine.

---

## Typical Agent Conversation Examples

### User: "Reduce IPTS 35884"

```
Agent tells user: "Starting autopilot for IPTS-35884..."
Agent sends: /autopilot 35884
Agent reads stderr progress, relays periodically:
  → "Loaded 120 runs. Matched 50 across 2 configs."
  → "Reducing... 10/50 done, ETA ~20min"
  → "30/50 done, 1 failure so far"
  → "Reduction complete: 48 succeeded, 2 failed."
Agent tells user about failures: "Failed: S-broken (4m10a) — missing empty beam"
Agent sends: /plot *_Iq.dat --save all_results.png
Agent sends: /share *.png
Agent tells user: "Here are your I(Q) plots: <URL>"
```

### User: "Reduce IPTS 36548 but skip the Y5 samples, thickness 0.15"

```
Agent sends: /autopilot 36548 --exclude Y5 --thickness 0.15
```

### User: "Reduce only the 8m config from 35884, use banjo as background"

```
Agent sends: /autopilot 35884 --config 8m12a --bkg banjo
```

### User: "Reduce 36548 with emptyticell as background, skip Y5 and Y6"

```
Agent sends: /autopilot 36548 --bkg emptyticell --exclude Y5,Y6
```

### User: "Load IPTS 35884 and show me the catalog"

```
Agent sends: /load ipts 35884
Agent sends: /show catalog
Agent reads: data.rows contains all runs
Agent formats and reports the catalog to the user
```

### User: "Change the background to emptyticell for all samples"

```
Agent sends: /assign bkg emptyticell
Agent reads: confirmation with count of rows updated
Agent reports: "Updated background to emptyticell for N rows across M configs."
```

### User: "Show me the reduced I(Q) plots"

```
Agent sends: /list iq
Agent reads: list of .dat files
Agent sends: /plot *_Iq.dat --save iq_plots.png
Agent sends: /share iq_plots.png
Agent reports: "Here are your I(Q) plots: <URL>"
```

### User: "What's the status of the working table?"

```
Agent sends: /show table
Agent reads: data.rows with all fields
Agent summarizes: N rows, M configs, any missing fields
```

---

## Relaying Output to the User

**CRITICAL:** You must keep the user informed as you work. Do NOT silently run the
entire pipeline and only report at the end. Reductions can take 30+ minutes — the
user needs to see progress.

### What to relay and when

| Event | What to tell the user |
|-------|----------------------|
| After `/load ipts` | "Loaded N runs from IPTS-XXXXX" |
| After `/matchruns` | "Matched N runs across M configs. X missing trans, Y missing bkg." |
| After any `/set` or `/assign` | "Updated N rows" (brief confirmation) |
| After `/apply preset auto` | "Applied presets: 4m10a ← conf_4m_10a_60hz, 2.5m2.5a ← ..." |
| During `/reduce` or `/autopilot` | Relay progress from stderr: "[5/50] done S-myprotein (4m10a) 32s" |
| After reduction completes | "Reduction complete: N succeeded, M failed out of T total" |
| If any rows failed | List the failed samples and error messages |
| After `/stitch run` | "Stitched N samples" |
| After `/plot --save` | "Plot saved" |
| After `/share` | **Always** send the URL to the user |

### Progress during long-running commands

`/reduce` and `/autopilot` stream progress to **stderr** with `progress:` prefix.
Relay these to the user periodically — at minimum every 5 rows or every 2 minutes.
You don't need to relay every single line, but the user should see:
- That work is happening (not stalled)
- Roughly how far along (e.g., "15/50 done, ~20 minutes remaining")
- Any failures as they occur

### Example: good relay behavior

```
User: "Reduce IPTS 35884"

Agent: "Starting autopilot for IPTS-35884..."
Agent sends: /autopilot 35884
Agent reads stderr: progress lines
Agent: "Loaded 120 runs. Matched 50 scattering runs across 2 configs (4m10a, 2.5m2.5a)."
Agent: "Applied presets. Reducing 50 runs..."
Agent: "Progress: 10/50 done, 2 failed so far. ETA ~15 minutes."
Agent: "Progress: 30/50 done. ETA ~8 minutes."
Agent: "Reduction complete: 47 succeeded, 3 failed."
Agent: "Failed: S-broken (4m10a) — missing empty beam, S-bad (2.5m2.5a) — drtsans error"
Agent sends: /plot *_Iq.dat --save results.png
Agent sends: /share *.png
Agent: "Here are your I(Q) plots: https://here.now/abc123"
```

### Example: bad relay behavior (DO NOT DO THIS)

```
User: "Reduce IPTS 35884"

[30 minutes of silence]

Agent: "Done. 47 out of 50 succeeded. Here are plots: <URL>"
```

---

## Important Notes

- Always use `/commands` with the `/` prefix. Never send natural language — the headless
  mode's built-in LLM is not reliable for agent use. Use explicit commands.
- After `/reduce` or `/autopilot`, always check for failures in the response data.
- After modifying the table (`/set`, `/remove`, `/assign`), verify with `/show table`.
- The `/share` command returns a URL — always pass this to the user.
- Session auto-saves after every command and after background jobs (`/reduce`, `/autopilot`). Use `/continue` on restart to resume.
- Reduction can take minutes per row. Monitor stderr for progress and relay to user.
- Default thickness is 0.1 cm. Only set `--thickness` if the user specifies differently.
