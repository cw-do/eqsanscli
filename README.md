# EQSANS CLI

Interactive terminal application for EQSANS data reduction at SNS/ORNL.

## Quick Start

```bash
# On analysis.sns.gov
cd /gpfs/neutronsfs/instruments/EQSANS/shared/script/eqsanstools-cli
source .venv/bin/activate
python -m eqsanscli
```

## Typical Workflow

### Minimal (using auto-match)

```
/load ipts 35884                         # Fetch catalog from ONCat
/matchruns                               # Auto-match trans/bkg/empty runs
/show table                              # Review matched runs
/apply preset auto                       # Auto-match closest preset to each config
/set outputdir /SNS/EQSANS/IPTS-35884/shared/output/
/reduce all                              # Run reduction
/list iq                                 # List reduced files
/plot *_Iq.dat --save plot.png           # Plot results
/share *.png                             # Share via here.now (24h link)
/save session myexperiment               # Save for later
```

### With porsil calibration (manual, like autopilot)

```
/load ipts 35884
/matchruns
/apply preset auto
/set outputdir /SNS/EQSANS/IPTS-35884/shared/output/

# Reduce porsil first with scale=1.0
/set config 4m10a standardabsolutescale 1.0
/set config 2.5m2.5a standardabsolutescale 1.0
/reduce --sample porsil                  # Reduce only porsil rows

# Calibrate each config against the reduced porsil
/calibrate porsil_4m10a_Iq.dat           # Prints scale factor + ready-to-use /set command
/set config 4m10a standardabsolutescale 0.227588
/calibrate porsil_2.5m2.5a_Iq.dat
/set config 2.5m2.5a standardabsolutescale 0.191234

# Now reduce the actual samples with calibrated scales
/reduce all                              # Re-reduces everything (porsil "modified" auto-resets)

# Stitch and plot
/stitch smart
/stitch run
/plot merged_*.txt --save stitched.png
/share stitched.png
```

### Manual override (specific preset, custom scale)

```
/load ipts 35884
/matchruns
/apply preset conf_4m_10a_60hz 4m10a     # Apply specific preset
/set config 4m10a standardabsolutescale 0.14
/set outputdir /SNS/EQSANS/IPTS-35884/shared/output/
/reduce all
```

## Autopilot (Full Pipeline)

| Command | Description |
|---------|-------------|
| `/autopilot <ipts>` | Full automated reduction pipeline |
| `/autopilot <ipts> --samples <name1,name2>` | Only reduce specific samples |
| `/autopilot <ipts> --exclude <name1,name2>` | Reduce all except named samples |
| `/autopilot <ipts> --thickness <cm>` | Set sample thickness for all rows |
| `/autopilot <ipts> --bkg <sample>` | Use named sample as background (config-aware) |
| `/autopilot <ipts> --config <id>` | Reduce only the specified configuration |
| `/autopilot <ipts> --force` | Re-reduce all rows (ignore done/modified status) |
| `/autopilot <ipts> --exclude Y5 --bkg emptyticell --thickness 0.15` | Combined options |

All flags are composable. Execution order: thickness → bkg → samples → exclude → config.
Setup (thickness, bkg) applies to the full table first, then filters (samples, exclude, config) trim rows down.

### Re-reduction Status

When you change a row's parameters (`/set`, `/assign bkg`) or config parameters
(`/set config`, `/apply preset`) after reduction, affected rows automatically change
status from `done` to `modified`. Autopilot will re-reduce `modified` rows.
Use `--force` to re-reduce all rows regardless of status.

**Examples:**
```
/autopilot 35884                                         # Reduce everything
/autopilot 35884 --samples Bi1,Bi2                       # Only Bi1 and Bi2 (+ porsil)
/autopilot 35884 --exclude Y5,Y6                         # Everything except Y5 and Y6
/autopilot 35884 --bkg emptyticell                       # Use emptyticell as background
/autopilot 35884 --config 8m12a                          # Only the 8m12a configuration
/autopilot 35884 --thickness 0.15                        # All samples at 0.15 cm
/autopilot 35884 --bkg banjo --exclude Y5 --thickness 0.2   # Combined: set bkg, exclude Y5, 0.2 cm
/autopilot 35884 --bkg s0 --config 4m10a                 # s0 as bkg, only 4m10a config
/autopilot 36548 --bkg emptyticell --samples Bi1 --thickness 0.15  # emptyticell bkg, only Bi1, 0.15 cm
```

## Commands

### Catalog & Data Loading

| Command | Description |
|---------|-------------|
| `/load ipts <number>` | Fetch catalog from ONCat |
| `/show catalog` | Display loaded catalog |
| `/show ipts` | Show current IPTS number |
| `/save catalog <file>` | Export catalog to CSV |
| `/load catalog <file>` | Load catalog from CSV |
| `/list ipts *` | List all EQSANS experiments (cached after first fetch) |
| `/list ipts <text>` | Search experiments by title or member name (from cache) |
| `/list ipts refresh` | Re-fetch experiment list from ONCat (clears cache) |

### Working Table

| Command | Description |
|---------|-------------|
| `/show table` | Show current working table |
| `/show table --sample <name>` | Show only rows matching sample name (read-only filter) |
| `/matchruns` | Auto-match transmission/background/empty runs |
| `/assign bkg <sample>` | Reassign background sample for all rows (config-aware, sets bkg+bkgtrans) |
| `/set <row> <field> <value>` | Set row field. `<row>` = index, run number, range (`1-5`, `1,3,5`), or `all` |
| `/set <row> <field> none` | Clear a field |
| `/set --sample <name> <field> <value>` | Set field for all rows matching sample name (exact match; use `*` for wildcard) |
| `/remove <row>` | Remove rows. `<row>` = index, run number, range (`1-5`, `1,3,5`), or `all --keep porsil` |
| `/remove --sample <name>` | Remove rows matching sample name (exact; `*` for wildcard) |
| `/save table <name>` | Save working table |
| `/load table <name>` | Load saved table |

### Multi-Table

| Command | Description |
|---------|-------------|
| `/table list` | List all tables |
| `/table new <name>` | Create and switch to new table |
| `/table <name>` | Switch active table |
| `/table clone <src> <dst>` | Clone a table |
| `/table rename <old> <new>` | Rename a table |
| `/table delete <name>` | Delete a table |
| `/move <row> <table>` | Move rows to another table. `<row>` = index, run number, range, or `all` |

### Calibration

| Command | Description |
|---------|-------------|
| `/calibrate <porsil_file>` | Calculate absolute scale from porsil data (default Q range: 0.01–0.03) |
| `/calibrate <file> --ref NG3\|NG7` | Choose reference standard |
| `/calibrate <file> --qmin 0.01 --qmax 0.03` | Set Q range (defaults shown) |
| `/calibrate --list-refs` | List available reference standards |

### Share

| Command | Description |
|---------|-------------|
| `/share <file\|pattern>` | Share files via here.now (anonymous, 24h link) |
| `/share *.png` | Share all PNG files |
| `/share *_4m10a_Iq.dat` | Share matching I(Q) files |

Files are uploaded to [here.now](https://here.now) using only Python stdlib (no external packages). Anonymous uploads expire in 24 hours. Max 50 MB total. Searches output directory first, then current directory.

### LLM

| Command | Description |
|---------|-------------|
| `/models` | List available LLM models |
| `/models <name>` | Switch LLM model |

### Configuration

| Command | Description |
|---------|-------------|
| `/list configs` | List configurations in current table |
| `/show config <id>` | Show all reduction parameters (75 params from eqsans_reduction.json) |
| `/set config <id> <param> <value>` | Set a config parameter |
| `/show outputdir` | Show output directory |
| `/set outputdir <path>` | Set output directory |
| `/set ipts <number>` | Set IPTS number |
| `/set drtsans <version>` | Set drtsans version (`default`, `dev`, `qa`) |

Config IDs are compact lowercase strings: `4m10a`, `4m2.5a`, `2.5m2.5a`. The 60Hz chopper frequency is omitted (default); 30Hz is shown: `4m10a30hz`. All matching is case-insensitive. Tab autocompletion is available.

### Presets

| Command | Description |
|---------|-------------|
| `/show presets` | List preset configurations from `preset_configs/` |
| `/show preset <name>` | Show preset parameters |
| `/apply preset <name> <config_id>` | Copy preset to active config |
| `/apply preset auto` | Auto-match closest preset to each config in the table |
| `/compare <a> <b>` | Side-by-side diff of two configs/presets |

Place JSON files in the `preset_configs/` folder. These are full `eqsans_reduction.json` files from previous experiments.

### Reduction

| Command | Description |
|---------|-------------|
| `/reduce <row>` | Run data reduction. `<row>` = index, run number, range, or `all` |
| `/reduce --sample <name>` | Reduce only rows matching sample name (exact; `*` for wildcard) |
| `/export script [filename]` | Generate standalone .py reduction script |

### Data & Plotting

| Command | Description |
|---------|-------------|
| `/list iq` | List reduced I(Q) files in output directory |
| `/list iqxqy` | List I(Qx,Qy) files |
| `/plot <file\|pattern> [flags]` | Plot I(Q) data |

Plot flags:

| Flag | Description |
|------|-------------|
| `--logx`, `--logy` | Log scale (default: both on) |
| `--linx`, `--liny` | Linear scale |
| `--loglog`, `--linlin` | Set both axes at once |
| `--kratky` | Kratky plot: Q² × I(Q) vs Q |
| `--guinier` | Guinier plot: ln(I) vs Q² |
| `--porod` | Porod plot: I × Q⁴ vs Q |
| `--noerror` | Hide error bars |
| `--grid` | Show grid lines |
| `--offset <factor>` | Vertical offset between curves |
| `--xmin/xmax/ymin/ymax <val>` | Set axis range |
| `--title <text>` | Custom title |
| `--save <path>` | Save to PNG/PDF/SVG |
| `--dpi <val>` | Resolution (default: 150) |

### Stitch/Merge

| Command | Description |
|---------|-------------|
| `/stitch build` | Auto-build stitch table from reduced I(Q) files |
| `/stitch smart [--llm]` | Smart stitch with overlap quality analysis |
| `/stitch show` | Display stitch table |
| `/stitch set <idx\|sample\|all> overlap <q1 q2 ...>` | Set overlap Q range |
| `/stitch set <idx\|sample\|all> target <idx\|config_id>` | Set normalization target (index or config like `4m10a`) |
| `/stitch removerow <idx\|all\|--sample name>` | Remove stitch group by index, all, or sample name |
| `/stitch removeconfig <idx\|all> <config_id>` | Remove a config from stitch group(s) |
| `/stitch reorder <idx\|all> <c1,c2,...>` | Reorder configs in stitch group(s) |
| `/stitch run [sample]` | Execute stitching |
| `/stitch script [filename]` | Export stitch script |
| `/stitch save <name>` | Save stitch table |
| `/stitch load <name>` | Load stitch table |

**Smart Stitching:** The `/stitch smart` command analyzes overlap quality between curves and automatically removes redundant configurations:
- Prefers overlaps in the middle region (not at edges)
- Detects when a middle config (mid-Q) adds no value
- Optionally consults LLM for complex decisions (`--llm` flag)
- Calculates quality scores (0-100) based on point count, error, and position

**Auto-overlap algorithm:** `/stitch set all overlap auto` computes a centered overlap window for each adjacent pair. The window starts with 6 pooled Q values centered in the intersection, then widens symmetrically until both profiles have at least 2 data points inside. This ensures reliable scaling regardless of data sparsity or which config is used as the normalization target.

### Session

| Command | Description |
|---------|-------------|
| `/continue` | Resume most recent session (autosave or named) |
| `/session list` | List saved sessions |
| `/session save [name]` | Save current session |
| `/session load <name>` | Load a saved session |
| `/help` | Show command reference |
| `/quit` | Exit (auto-saves session) |

**Auto-save:** Session is saved automatically after every command and on exit. On startup, if a previous session exists, you'll see a hint to type `/continue` to resume.

### Settings

| Command | Description |
|---------|-------------|
| `/settings` | Show current settings |
| `/settings textwrap <width>` | Set text wrap width (40-200) |
| `/settings figsize <w> <h>` | Set default plot size (e.g. `8 6`) |
| `/settings dpi <value>` | Set default plot DPI (50-600) |
| `/settings plotscale <scale>` | Set axis scale (`loglog`, `linlin`, `loglin`, `linlog`) |
| `/settings errorbars <on\|off>` | Toggle default error bars |
| `/settings linestyle <style>` | Set line style (`line`, `marker`, `line+marker`) |
| `/settings multiprocessing <n>` | Set parallel reduction jobs (1-4, default 1) |

### Shell Commands

| Command | Description |
|---------|-------------|
| `/ls [path]` | List directory contents (color-coded) |
| `/cd <path>` | Change directory |
| `/pwd` | Print working directory |
| `/mkdir <path>` | Create directory (with parents) |
| `/cat <file>` | Display file contents |
| `/head <file> [n]` | Show first n lines (default 10) |
| `/tail <file> [n]` | Show last n lines (default 10) |
| `/cp <src> <dst>` | Copy file or directory |
| `/mv <src> <dst>` | Move/rename file |
| `/rm <file> [...]` | Remove files or directories |
| `/sh <command>` | Run any shell command (30s timeout) |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate command history |
| `Tab` | Auto-complete commands, config IDs, presets |
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear output log |
| `Escape` | Focus command input |

## Key Concepts

### Configuration = (distance, wavelength, frequency)

Each configuration is identified by three parameters from ONCat metadata:
- Detector distance (e.g., 4m)
- Wavelength (e.g., 2.5A)
- Chopper frequency (60Hz default, omitted; 30Hz shown)

Format examples: `4m10a`, `4m2.5a`, `2.5m2.5a`, `8m12a30hz`

The same ID is used for table display, commands, and output filenames (e.g., `porsil_4m10a_Iq.dat`).

### Index vs Name Resolution

Commands that accept `<row>` or `<idx|sample|all>` (e.g., `/set`, `/reduce`, `/stitch set`)
try **index first**, then fall back to sample/run name. If a sample name happens to be a
bare integer (e.g., `"3"`), it will be interpreted as an index. Use `--sample 3` to force
sample-name matching where available (`/set --sample`, `/remove --sample`).

### Run Matching

`/matchruns` groups runs by configuration, then matches by sample name:
- **All** scattering runs appear in the table (including background and empty beam)
- Background runs (banjo) get empty beam as their own background
- Transmission matched for every scattering run by sample name
- Use `/assign bkg <sample>` to change which sample is used as background

**Transmission matching with temperature:** When run titles include temperature
(e.g., "r1 4m 10A 110C" → sample name `r1_110C`), matching works in two tiers:
1. **Exact match:** `r1_110C` looks for `T-r1_110C`
2. **Base fallback:** If no exact match, strips temperature → `r1` → looks for `T-r1`

This means one transmission run can serve samples at different temperatures
(transmission doesn't change with temperature).

**Configuration matching:** When assigning background/transmission/empty beam across
multiple configurations, assignments MUST match by configuration. A background run
from 4m10a should not be assigned to a 2.5m2.5a sample. Use per-row `/set` commands
instead of `/set --sample` when configs differ.

### drtsans Version

```
/set drtsans dev                        # Use dev version
/set drtsans qa                         # Use QA version
/set drtsans default                    # Use standard drtsans
/set drtsans                            # Show current version
```

### Natural Language

The built-in LLM understands natural language. Type any of these directly:
```
reduce all data except Y5 from ipts 36548
use emptyticell as background for all samples
set all thickness to 0.1 cm
apply transmission 172804 to all 3b samples
remove SDS from stitch table
```

The LLM translates these into CLI commands and executes them in sequence. Each generated command is shown with a `→` prefix before execution, so you can see exactly what runs. If any command fails, the sequence stops.

You can also execute commands directly with the `/` prefix for faster, more predictable results. LLM examples and patterns are defined in `preset_configs/knowledge.md`.

**How it works:** The LLM receives the full session context (working table, catalog, configurations) and domain knowledge, then returns one or more `/commands`. It never executes actions directly — only the command router does. For safety, the LLM cannot generate `/sh`, `/rm`, or `/mv` commands.

**Configuration matching:** When the LLM assigns background/transmission across multiple configurations (e.g., 4m10a + 2.5m2.5a), it emits per-row `/set` commands matching each row's config. This is the most complex NL→command translation and is documented extensively in `knowledge.md`.

### Output Directory

The output directory controls where reduced I(Q) files are written.

- **Default:** `./output/`
- **`/set outputdir <path>`** updates the global setting AND propagates to all existing config `outputdir` values.
- **`/matchruns`** initializes new configs with the current global `outputdir`.
- **`/autopilot`** always syncs the global `outputdir` to all configs before reducing.
- **Config-level `outputdir`** is written into each `.json` reduction file. drtsans reads this to decide where to write output.

**Typical usage:**
```
/set outputdir /SNS/EQSANS/IPTS-35884/shared/my_output/
/matchruns            # new configs inherit the outputdir above
/reduce all           # all output goes to my_output/
```

If you change `outputdir` after configs are loaded, run `/set outputdir` again to update all configs.

### Sample Name Matching

All `--sample` flags use **exact match** by default (case-insensitive). Use `*` for wildcard:

| Pattern | Matches | Does NOT match |
|---------|---------|----------------|
| `empty` | `empty` | `emptycupbox` |
| `empty*` | `empty`, `emptycupbox` | `notempty` |
| `*3b*` | `S-3b`, `S-3b-2` | `S-4b` |

This applies to: `/set --sample`, `/remove --sample`, `/remove all --keep`, `/show table --sample`, `/stitch removerow --sample`.

### Sample Thickness

Each working table row has a `thickness` field (default: 0.1 cm), shown in the "Thick" column. Set it with:
```
/set 3 thickness 0.2            # single row by index
/set 172815 thickness 0.2       # single row by run number
/set 1-5 thickness 0.2          # range
/set all thickness 0.15         # all rows
/set --sample porsil thickness 0.1  # by sample name
```

### Run Numbers as Strings

Run numbers are stored as strings to support comma-separated multi-run:
```
/set 172815 trans "172804, 172805"
```
drtsans will combine these runs for better statistics.

### Preset Configs

Place full `eqsans_reduction.json` files in `preset_configs/`:
```
preset_configs/
  conf_4m_10a_60hz.json
  conf_2.5m_2.5a_60hz_inc.json
  conf_8m_12a_60hz.json
  conf_8m_12a_60hz_inc.json
```

Apply with `/apply preset conf_4m_10a_60hz 4m10a`, then review differences with `/compare`.

## Project Structure

```
src/eqsanscli/
  __init__.py, __main__.py, app.py
  commands/       — Command handlers (catalog, config, data, matching, preset, reduction, export, session, shell, stitch)
  services/       — Business logic (catalog, matching, config_manager, preset, reduction, script_exporter, plotting, merge_service)
  models/         — Data models (run_metadata, working_table, session_state, config_id, sample_match)
  integrations/   — External interfaces (oncat, json_builder, drtsans_runner, share_service)
  config/         — Presets and settings
  tui/widgets/    — TUI components (completable_input, catalog_table, working_table)
preset_configs/   — Preset JSON configs + knowledge.md (LLM examples/patterns)
SKILL.md          — AI agent skill documentation (TUI-oriented)
AGENT_SKILL.md    — Agent integration spec (headless JSON protocol)
```

LLM-to-instruction execution pipeline:
- `src/eqsanscli/commands/router.py` — dispatches NL input to LLM, then executes returned commands
- `src/eqsanscli/services/llm_handler.py` — builds LLM prompt with session context, calls API, returns commands
- `preset_configs/knowledge.md` — domain knowledge + NL→command translation examples injected into LLM prompt

## Headless Mode (Agent Integration)

eqsanscli can run without the TUI for programmatic use by agents, bots, or scripts.

### Quick Start (Headless)

```bash
# On analysis.sns.gov
cd /SNS/EQSANS/IPTS-35884/shared/
cp /SNS/EQSANS/shared/script/eqsanstools-cli/eqsanscli-headless ./
./eqsanscli-headless
```

This starts a JSON-over-stdin/stdout protocol:
- **Send:** one `/command` per line to stdin
- **Receive:** one JSON object per line from stdout: `{"success": bool, "message": str, "data": dict|null}`
- **Progress:** long-running commands stream to stderr with `progress:` prefix

### Agent Skill Documents

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | Humans | User guide and command reference |
| `SKILL.md` | AI agents (TUI) | Workflow, decisions, command returns |
| `AGENT_SKILL.md` | AI agents (headless) | Full integration spec: SSH connection, JSON protocol, decision trees, conversation examples |

To connect an AI agent (Slack bot, OpenClaw, etc.):
1. SSH into `analysis.sns.gov`
2. Navigate to the IPTS workspace: `cd /SNS/EQSANS/IPTS-<N>/shared/`
3. Copy and run: `cp /SNS/EQSANS/shared/script/eqsanstools-cli/eqsanscli-headless ./`
4. Launch: `./eqsanscli-headless`
5. Load `AGENT_SKILL.md` into the agent's system prompt
6. Send `/commands` to stdin, read JSON from stdout
7. Use `/share` to get URLs for plots and data files to send to users

## Requirements

- Python 3.10+
- textual, rich, pandas, numpy, matplotlib, pyoncat
- `drtsans` CLI on PATH (for `/reduce`)
- Access to `/SNS/EQSANS/` filesystem and ONCat network
