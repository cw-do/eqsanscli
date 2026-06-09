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

Fields: `trans`, `bkg`, `bkgtrans`, `emp`, `thickness`

### Configuration
| Command | Returns |
|---------|---------|
| `/list configs` | Config IDs in the table |
| `/show config <id>` | All ~75 parameters with values |
| `/set config <id> <param> <value>` | Confirmation |
| `/apply preset auto` | Per-config match result (exact/partial/distance/none) |
| `/apply preset <name> <config_id>` | Parameter count applied |
| `/set outputdir <path>` | Confirms path, propagation to N configs |

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
