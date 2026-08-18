---
name: eqsanscli
description: Interactive EQSANS data reduction tool for SNS/ORNL. Agents use slash commands to load experiments, match runs, configure parameters, reduce data, stitch, and plot.
---

# EQSANS CLI — Agent Skill

## What This Tool Does

eqsanscli reduces EQSANS small-angle neutron scattering (SANS) data at SNS/ORNL.
Input: raw neutron scattering runs from an experiment (IPTS number).
Output: reduced I(Q) profiles (`.dat` files), stitched across configurations, plotted.

## Interaction Model

eqsanscli is an interactive TUI. Commands are typed at the `eqsans>` prompt.
- All commands start with `/` (e.g., `/load ipts 35884`)
- Natural language without `/` is sent to the built-in LLM for translation
- For reliability, agents should always use explicit `/commands`, not natural language
- Commands are synchronous — wait for output before sending the next command
- Long-running commands (`/reduce`, `/autopilot`) show progress and can be cancelled with `Ctrl+X`

### Launch

```bash
cd /gpfs/neutronsfs/instruments/EQSANS/shared/script/eqsanstools-cli
source .venv/bin/activate
python -m eqsanscli
```

---

## Workflow Overview

```
/load ipts <N>        Load catalog from ONCat (adds run_class column)
        |
/show catalog         Review Class column (S/T/BkgS/BkgT/EmpT/N=ignored)
        |
[fix classes]         /reclass <runs> <class> (if titles are mislabeled)
                      Classes include 'ignore' (alias 'i' or 'n') — excluded from /matchruns
        |
/matchruns            Auto-match trans/bkg/empty using run_class
        |
/show table           Inspect — look for missing assignments
        |
[fix problems]        /set, /assign bkg, /remove
        |
/apply preset auto    Apply closest preset configs (preserves user-set params)
        |
/set outputdir <path> Set where output goes
        |
/reduce all           Run reduction (or /reduce --new for just new/errored rows)
        |
/stitch smart         Build stitch table + auto-detect overlap Q ranges
/stitch run           Execute stitching
        |
/plot *.dat           Plot results
```

Or skip everything with: `/autopilot <ipts>` (runs full pipeline automatically).
Use `/autopilot current` to run with the current session catalog (after `/reclass` etc.).

**Mid-experiment incremental flow** (when new runs are collected during the experiment):
```
/refresh catalog         Re-fetch from ONCat; PRESERVES /reclass overrides
/matchruns --update      Append new rows; preserves status=done rows
/reduce --new            Reduce only status != "done" rows
/stitch smart            Re-stitch with the new data
```

Or as a one-liner: `/autopilot --continue` does steps 1–4 above automatically and re-stitches.

**Quick reference panels:**
- `/help --simple` — inline 7-step quickstart
- `/guide` — dockable side pane with the quickstart (toggle with `/guide off`)

---

## Step-by-Step with Decision Logic

### Step 1: Load Catalog

```
/load ipts 35884
```

**Expect:** `Loaded N runs` message with run count.
**Failure:** ONCat network error — retry or check connectivity.
**Verify:** `/show catalog` — should list runs with columns: run number, title, config, type.

### Step 2: Match Runs

```
/matchruns
```

**Expect:** Summary with match counts:
```
Matched 50 scattering runs across 2 configurations.
  Configurations: 4m10a, 2.5m2.5a
  Transmission matched: 48/50
  Background matched: 50/50
  Empty beam matched: 45/50
```

**Decision tree after /matchruns:**

| Condition | Action |
|-----------|--------|
| All fields matched (trans, bkg, emp all N/N) | Proceed to Step 3 |
| Missing transmission | `/set --sample <name> trans <run>` or `/set <row> trans <run>` |
| Missing background | `/assign bkg <sample_name>` (preferred) or per-row `/set` |
| Missing empty beam | `/set <row> emp <run>` — find empty beam run from `/show catalog` |
| Mislabeled runs (title says T- but should be S-) | `/reclass <runs> scatt` then re-run `/matchruns` |
| Sample name contains bkg keyword (e.g. BkgG) | `/reclass --sample BkgG sample` — respects S-/T- prefix |
| Multiple empty beams or bkg per config | `/matchruns` will warn — use `/set <row> emp <run>` to pick one |
| Unwanted rows (e.g., test runs) | `/remove --sample <name>` |

**How to find the right run number:** Use `/show catalog` output. The Class column shows each run's classification:
- `S` = scattering, `T` = transmission, `BkgS`/`BkgT` = background, `EmpT` = empty beam
- If a run is misclassified, use `/reclass <run> <class>` to fix it before `/matchruns`

### Step 3: Verify Table

```
/show table
```

**What a healthy table looks like:** Every row has all fields filled (no `—` dashes):
- `Trans` column: has a run number
- `Bkg` column: has a run number
- `Emp` column: has a run number
- `Status` column: `ready`

**What needs fixing:** Any `—` in Trans/Bkg/Emp columns. Use `/show table --sample <name>` to filter and inspect specific samples.

### Step 4: Apply Presets

```
/apply preset auto
```

**Expect:** One line per config showing which preset was matched:
```
  ✓ 4m10a ← conf_4m_10a_60hz
  ✓ 2.5m2.5a ← conf_2.5m_2.5a_60hz
  ⚠ 1.3m1a — no matching preset found
```

**If no preset found:** Manually set key parameters:
```
/set config <id> qmin <value>
/set config <id> qmax <value>
/set config <id> numqbins <value>
```

Or apply a specific preset: `/apply preset <name> <config_id>`

**Verify:** `/show config <id>` — check that qmin, qmax, numqbins, sensitivityfilename, darkfilename, beamfluxfilename are set.

### Step 5: Set Output Directory

```
/set outputdir /SNS/EQSANS/IPTS-35884/shared/output/
```

This propagates to all configs. Default is `./output/`.

### Step 6: Reduce

```
/reduce all
```

**Expect:** Progress lines for each row:
```
  [1/50] ⟳ S-myprotein (4m10a) → S-myprotein_4m10a.json  49 left  ETA ~25m
  [1/50] ✓ S-myprotein (4m10a) — 32s  → S-myprotein_4m10a_Iq.dat
  [2/50] ✗ S-failed (2.5m2.5a) — error message here
```

**Success indicator:** `✓` with output filename.
**Failure indicator:** `✗` with error message. Common causes:
- Missing empty beam run → go back and fix with `/set`
- drtsans error → check parameters with `/show config <id>`
- File not found → check calibration file paths

**Verify after reduction:**
```
/list iq                    # Lists all reduced I(Q) .dat files
```

### Step 7: Stitch (if multiple configs)

```
/stitch build               # Auto-build stitch groups from reduced files
/stitch show                # Inspect stitch table
/stitch set all target 4m10a    # Set normalization target (usually the lowest-Q config)
/stitch set all overlap auto    # Auto-detect overlap Q ranges
/stitch run                 # Execute stitching
```

**Expect:** Merged files: `merged_<sample>_Iq.txt`

**Alternative:** `/stitch smart` does overlap quality analysis and may remove redundant configs automatically.

### Step 8: Plot

```
/plot *_Iq.dat --save all_iq.png
/plot merged_*.txt --save stitched.png
```

**Key flags:** `--loglog` (default), `--linlin`, `--kratky`, `--guinier`, `--save <path>`

---

## Critical Rules

### Configuration Matching

Every run belongs to a specific config (e.g., 4m10a, 2.5m2.5a). When assigning
bkg/trans/emp, the assigned run MUST be from the SAME config as the target row.

**Use `/assign bkg <sample>`** for background — it handles config matching automatically.
**Use per-row `/set`** only when targeting a subset of rows or assigning trans/emp.

### Sample Name Matching

`--sample` flags use exact match by default (case-insensitive). Add `*` for wildcard:
- `empty` matches only "empty", not "emptycupbox"
- `empty*` matches "empty", "emptycupbox"
- `*3b*` matches "S-3b", "S-3b-2"

### Row Selection

`<row>` everywhere accepts: index (`3`), run number (`172815`), range (`1-5`, `1,3,5`), or `all`.

---

## Commands Reference

### Catalog
| Command | Returns |
|---------|---------|
| `/load ipts <N>` | Loads catalog, reports run count |
| `/show catalog` | Table: run_number, title, config, type |
| `/show ipts` | Current IPTS number |
| `/list ipts *\|<text>` | Search all EQSANS experiments |

### Working Table
| Command | Returns |
|---------|---------|
| `/matchruns` | Match summary with counts per field |
| `/show table` | Full table with all row fields and status |
| `/show table --sample <name>` | Filtered view (read-only, no deletion) |
| `/assign bkg <sample>` | Count of rows updated, configs applied |
| `/set <row> <field> <value>` | Confirmation: field=value for N row(s) |
| `/set --sample <name> <field> <value>` | Same, filtered by sample name |
| `/remove <row>` | Count removed, remaining row count |
| `/remove --sample <name>` | Same, filtered by sample name |

Fields: `trans`, `bkg`, `bkgtrans`, `emp`, `thickness`, `sample`/`name`, `cfg`

To reassign a row to a different (typically cloned) config:
```
/set <row> cfg <name>             # name must already exist (see /config list)
/set <row> cfg none               # clear override → use physics-derived config
/set --sample <name> cfg <new>    # bulk
```
`cfg` is canonical; `config` and `configuration` are accepted aliases. Prefer
`cfg` to avoid visual collision with the `/set config <id> <param> <val>` form.

### Configuration
| Command | Returns |
|---------|---------|
| `/config list` (alias `/list configs`) | Configs in the table + stored extras (clones) |
| `/config clone <src> <dst>` | Confirmation; copied param count (`<dst>` must contain `<src>`'s config ID) |
| `/config rows <id>` | Rows referencing `<id>` |
| `/show config <id>` | All ~75 parameters with values |
| `/set config <id> <param> <value>` | Confirmation |
| `/set config all <param> <value>` | Per-config apply summary + sticky default |
| `/instrument show` | Per-config calibration set + source cycle + pending changes |
| `/instrument list [run]` | Cycle inventory and what a run resolves to |
| `/instrument apply [--force]` | Re-resolve; `--force` overrides your `/set config` values |
| `/instrument pin <cycle>` / `unpin` | Freeze to one cycle / release |
| `/instrument off` / `on` | Disable/enable auto resolution |
| `/instrument check` | Verify referenced calibration files exist |
| `/apply preset auto` | Per-config match result (exact/partial/distance/none) |
| `/apply preset <name> <config_id>` | Parameter count applied |
| `/set outputdir <path>` | Confirms path, propagation to N configs |

**Per-row config variants** — use when only a subset of rows at the same physical
config needs different params (e.g. a different mask):
```
/config clone 4m10a 4m10a_v2
/set --sample MySample cfg 4m10a_v2
/set config 4m10a_v2 maskfilename mask_v2.nxs
```
**Masks** resolve per configuration: `mask*.nxs` in the folder eqsanscli was
started in → `/SNS/EQSANS/IPTS-<current>/shared/` → the cycle's
`<cycle>_mp/masks/*mask.nxs` default. Matched on the distance and wavelength in
the filename (`maskWS4m10A.nxs` → `4m10a`, `maskWS4m2p5A_FS.nxs` → `4m2.5a`); a
mask naming a different distance/wavelength is never borrowed. Never a mask from
another IPTS — unreadable to other users. `/matchruns` and autopilot print the
mask chosen per config; if none is found they name every folder searched and ask
you to create one and set it with `/set config <id> maskfilename <file>`.

**Instrument calibration files** — dark, flood, flux, detoffset, scalecomp and
samoffset resolve automatically from the machine-physics cycle folders by run
number at `/matchruns` and in autopilot. Sensitivity follows the detector
distance (1.3 m → `1o3m`, 2.5 m → `2o5m`, 4 m and longer → `4m`); the whole set
comes from one cycle; `thinPMMA` is preferred. Your `/set config` values are
never overwritten, and pre-2026A runs get no AgBe values rather than invented
ones. Inspect with `/instrument show`, freeze with `/instrument pin <cycle>`.

- Clone names must contain the source config ID (`4m10a_v2` ✓, `mask2` ✗).
- A row only accepts a config with the same physics (`4m10a` row ✗ `8m10a` params).
- Output filenames stay `<sample>_<physical config>_Iq.dat` — clones change
  parameters, not file naming.

**Empty beam is mandatory.** It supplies the beam centre (`beamCenter.runNumber`)
as well as the empty transmission, so `/reduce` refuses up front for any selected
row without one, naming the rows and configurations and how to fix them. Missing
transmission or background is a warning only. Escape hatches:
`/reduce <rows> --skip-missing` (reduce the valid rows) and `/reduce <rows> --force`
(send them to drtsans anyway). `/autopilot` checks the same thing at Step 3 and
skips unreducible rows at reduction time.

**Masks:** `/mask create <run>` builds one from a uniformly illuminated run (the run number alone is enough — the archive is searched for it, so no `/load ipts` is needed first)
(banjo, flood, empty cell) and writes `mask_<config>_<run>.nxs` into the current
folder, named so the resolver finds it automatically, plus a `_compare.png` to review —
millimetres on the bottom and left axes (what `--disc` takes), tube and pixel
index on the top and right (what `--tubes` and `--top`/`--bottom` take), drawn with tube index ascending left to right so the mm axis descends and a `.params.json` recording how it was made. It masks the beam stop
(masked as a circle in millimetres against real pixel positions), the low-response
bands at both tube ends, and tubes deviating within their front/back pack of four.

The stop is measured from **cross cuts**, as it would be by hand: a vertical cut
gives the centre's y (the deep valley), a horizontal cut through it gives the x,
and the horizontal valley width — wall summit to wall summit — is the diameter.
That survives a shadow filled in by halo or by gravity-dropped beam: at 9 m and
15 Å it gives 80 mm against a stop 90 mm across, and at 4 m 66 mm against a 68 mm
hand-made mask. Runs whose cuts have no flare walls fall back to the shadow
itself, grown slightly; the report prints the arithmetic behind every size.
The tube-end bands are measured where response falls below half the plateau and
floored at the 11-pixel EQSANS convention — in practice the floor is what
applies. README's *What sets each size* table lists every threshold. Counting statistics still
matter — ~90 counts/pixel is comfortable, ~4 is marginal. When neither estimator
is credible the beam is **not masked** and the reason is printed; `--beam-center <x>,<y>` and
`--beam-radius <mm>` state it explicitly. `--leak` also masks the gravity-dropped beam below the stop, one disc per lobe, and `--leak-scale <f>` grows those discs to catch the faint tail. `--dry-run` previews without writing,
`--tubes a,b` adds known-bad tubes (auto-detection is whole-tube, so a dead
*segment* averages out), `--tube-sigma` tunes sensitivity. `/mask list` shows what
is discoverable. Needs drtsans for the Mantid read/write.

### Reduction
| Command | Returns |
|---------|---------|
| `/reduce <row>` | Progress per row (✓/✗), output filenames |
| `/autopilot <ipts> [options]` | Full pipeline with step-by-step progress |
| `/autopilot current [options]` | Use current session IPTS/catalog (preserves `/reclass`) |
| `/autopilot --continue` | Reduce only NEW runs, reuse saved calibration/configs/bkg |
| `/export script [file]` | Standalone .py script path |

Autopilot options: `--samples <a,b>`, `--exclude <a,b>`, `--thickness <cm>`

### Stitch
| Command | Returns |
|---------|---------|
| `/stitch build` | Stitch group count, samples, configs per group |
| `/stitch show` | Full stitch table |
| `/stitch set <sample\|all> target <id>` | Confirmation |
| `/stitch set <sample\|all> overlap auto` | Computed overlap Q ranges |
| `/stitch run [sample]` | Merged file paths |
| `/stitch smart` | Quality analysis + auto-cleanup |

### Data & Plotting
| Command | Returns |
|---------|---------|
| `/list iq` | List of reduced I(Q) .dat files |
| `/list iqxqy` | List of 2D I(Qx,Qy) .dat files |
| `/plot <pattern> [flags]` | Plot displayed or saved to file |
| `/share <pattern>` | Upload URL (24h anonymous link) |
| `/zipnsend <email> [options]` | Zip files and email (--pattern, --dir, --subject) |
| `/confirm [ipts]` | Update IPTS reduction status in SNS system |

Plot flags: `--logx`, `--logy`, `--linx`, `--liny`, `--loglog`, `--linlin`,
`--kratky`, `--guinier`, `--porod`, `--save <path>`, `--title <text>`, `--noerror`

### Session
| Command | Returns |
|---------|---------|
| `/continue` | Restores most recent session |
| `/session save [name]` | Save path |
| `/session load <name>` | Restored state summary |
| `/session list` | Available sessions |
| `/save table [name]` | Save path |
| `/load table [name]` | Table loaded or list of saved tables |

### Shell (read-only recommended)
| Command | Returns |
|---------|---------|
| `/ls [path]` | Directory listing |
| `/cat <file>` | File contents |
| `/head <file> [n]` | First n lines |
| `/pwd` | Current directory |

### Settings
| Command | Returns |
|---------|---------|
| `/settings` | All current settings |
| `/settings multiprocessing <n>` | Parallel job count (1-4) |

---

## Error Recovery Patterns

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| Reduction ✗ for specific rows | `/show table --sample <name>` — check for missing fields | Fill missing trans/bkg/emp with `/set` |
| "No scattering runs found" after `/matchruns` | Catalog may be empty or runs misclassified | `/show catalog` to check Class column; `/reclass <runs> scatt` to fix, then re-run `/matchruns` |
| Wrong absolute scale | Porsil calibration needed | `/calibrate <porsil_Iq.dat>` then `/set config <id> standardabsolutescale <value>` |
| Stitched curves don't overlap well | Bad overlap range or wrong target | `/stitch set all overlap auto` or manually set `/stitch set <sample> overlap <q1> <q2>` |
| "Preset not found" | Preset name doesn't match any file in `preset_configs/` | `/show presets` to list available presets |
| Output in wrong directory | outputdir not set or not propagated | `/set outputdir <path>` (propagates to all configs) |

---

## Output Files

```
{sample}_{config}_Iq.dat        # 1D reduced I(Q)
{sample}_{config}_Iqxqy.dat     # 2D reduced I(Qx,Qy)
{sample}_{config}.json          # drtsans reduction input
merged_{sample}_Iq.txt          # Stitched I(Q) across configs
```

All written to the configured output directory (`/set outputdir` or `./output/` default).

---

## Config IDs

Compact encoding of detector configuration:
- `4m10a` = 4m distance, 10A wavelength, 60Hz (default freq omitted)
- `2.5m2.5a` = 2.5m, 2.5A, 60Hz
- `4m10a30hz` = 4m, 10A, 30Hz

Case-insensitive. Used in table display, commands, and output filenames.
