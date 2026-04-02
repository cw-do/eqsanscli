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

### Quick Path (one command)

If the user just wants everything reduced with defaults:
```
/autopilot <ipts>
```
Options (all composable):
- `--thickness <cm>` — set thickness for all rows (default 0.1)
- `--bkg <sample>` — use named sample as background (config-aware)
- `--samples <a,b>` — keep only these samples (+ porsil)
- `--exclude <a,b>` — remove these samples
- `--config <id>` — reduce only this configuration (e.g., `8m12a`)

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

This handles everything automatically. Skip to "Sharing Results" below.

### Manual Path (full control)

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

#### Step 3: Apply Presets

```
/apply preset auto
```

**Check:** message shows which presets matched each config.
If any config shows "no matching preset found", tell the user — they may need to provide parameters.

#### Step 4: Set Output Directory

```
/set outputdir /SNS/EQSANS/IPTS-<number>/shared/output/
```

#### Step 5: Reduce

```
/reduce all
```

**Check `data.results`** — each entry has `status: "done"` or `status: "error"`.
If any failed, report the error messages to the user.

#### Step 6: Stitch (if multiple configs)

```
/stitch build
/stitch set all target 4m10a
/stitch set all overlap auto
/stitch run
```

Or use `/stitch smart` for automatic quality analysis.

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

---

## Command Reference

### Row Selection

Many commands accept a `<row>` argument. It can be:
- Row index: `3`
- Run number: `172815`
- Range: `1-5` or `1,3,5`
- All rows: `all`

### Sample Name Matching

`--sample` flags use exact match by default (case-insensitive). Add `*` for wildcard:
- `empty` → matches only "empty"
- `empty*` → matches "empty", "emptycupbox"
- `*3b*` → matches "S-3b", "S-3b-2"

### Catalog & Loading

| Command | Purpose |
|---------|---------|
| `/load ipts <N>` | Fetch experiment catalog from ONCat |
| `/show catalog` | Display all runs with metadata |
| `/show ipts` | Show current IPTS number |
| `/list ipts *` | List all EQSANS experiments |
| `/list ipts <text>` | Search experiments by title |

### Working Table

| Command | Purpose |
|---------|---------|
| `/matchruns` | Auto-match trans/bkg/empty runs from catalog |
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
| `/list configs` | List configs in the table |
| `/show config <id>` | Show all parameters for a config |
| `/set config <id> <param> <value>` | Set a config parameter |
| `/apply preset auto` | Auto-match closest preset to each config |
| `/apply preset <name> <config_id>` | Apply specific preset |
| `/set outputdir <path>` | Set output directory (propagates to all configs) |
| `/set drtsans <version>` | Set drtsans version: default, dev, qa |

Config IDs: `4m10a`, `2.5m2.5a`, `8m12a`, `4m10a30hz` (distance + wavelength + frequency)

### Reduction

| Command | Purpose |
|---------|---------|
| `/reduce <row>` | Reduce selected rows |
| `/autopilot <ipts> [options]` | Full automated pipeline (see Quick Path above for all options) |
| `/export script [file]` | Export standalone Python script |

### Stitching

| Command | Purpose |
|---------|---------|
| `/stitch build` | Build stitch table from reduced files |
| `/stitch show` | Display stitch table |
| `/stitch smart` | Auto-analyze and stitch |
| `/stitch set <sample\|all> target <config_id>` | Set normalization target |
| `/stitch set <sample\|all> overlap auto` | Auto-detect overlap Q ranges |
| `/stitch run [sample]` | Execute stitching |

### Data & Plotting

| Command | Purpose |
|---------|---------|
| `/list iq` | List reduced I(Q) files |
| `/plot <pattern> [flags]` | Plot data |
| `/share <pattern>` | Upload files, get 24h URL |

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

## Error Recovery

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `/matchruns` shows missing trans/bkg/emp | Catalog runs don't follow naming convention | Use `/show catalog`, find correct runs, use `/set` |
| `/reduce` fails for some rows | Check `data.results` for `status: "error"` | Fix missing fields with `/set`, re-reduce failed rows |
| "No scattering runs found" | Empty catalog or wrong IPTS | Verify IPTS number, `/show catalog` |
| Preset not found | No matching preset in preset_configs/ | `/show presets` to list available, apply manually |
| Bad stitch overlap | Wrong target or overlap range | `/stitch set all target <lowest_q_config>`, `/stitch set all overlap auto` |
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
Agent sends: /autopilot 35884
Agent reads: progress lines on stderr, then final JSON on stdout
Agent reports: "Reduction complete. X samples reduced across Y configs. Z failures."
Agent sends: /plot *_Iq.dat --save all_results.png
Agent sends: /share *.png
Agent reports: "Here are your results: <URL>"
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

## Important Notes

- Always use `/commands` with the `/` prefix. Never send natural language — the headless
  mode's built-in LLM is not reliable for agent use. Use explicit commands.
- After `/reduce` or `/autopilot`, always check for failures in the response data.
- After modifying the table (`/set`, `/remove`, `/assign`), verify with `/show table`.
- The `/share` command returns a URL — always pass this to the user.
- Session auto-saves after every command. Use `/continue` on restart to resume.
- Reduction can take minutes per row. Monitor stderr for progress.
- Default thickness is 0.1 cm. Only set `--thickness` if the user specifies differently.
