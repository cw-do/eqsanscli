# EQSANS CLI

Interactive terminal application for EQSANS data reduction at SNS/ORNL.

## Quick Start

```bash
# On analysis.sns.gov
cd /path/to/your/working/directory
PYTHONPATH=/gpfs/neutronsfs/instruments/EQSANS/shared/script/eqsanstools-cli/src \
  /SNS/users/ccd/miniforge3/envs/py312/bin/python3 -m eqsanscli
```

## Typical Workflow

```
/load ipts 35884                         # Fetch catalog from ONCat
/show catalog                            # View loaded catalog
/matchruns                               # Auto-match trans/bkg/empty runs
/show table                              # Review matched runs
/assign bkg s0                           # Reassign background sample
/set outputdir /SNS/EQSANS/IPTS-35884/shared/output/
/show presets                            # List available preset configs
/apply preset conf_4m_10a_60hz 4m10a     # Apply preset to config
/show config 4m10a                       # Review parameters
/set config 4m10a standardabsolutescale 0.14
/reduce all                              # Run reduction
/export script reduce_35884.py           # Or export as standalone script
/list iq                                 # List reduced files
/plot *_4m10a_Iq.dat --save plot.png     # Plot results
/save session myexperiment               # Save for later
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

### Working Table

| Command | Description |
|---------|-------------|
| `/show table` | Show current working table |
| `/matchruns` | Auto-match transmission/background/empty runs |
| `/assign bkg <sample>` | Reassign background sample for all rows |
| `/set <run> <field> <value>` | Set run association (`trans`, `bkg`, `bkgtrans`, `emp`, `thickness`) |
| `/set <run> bkg none` | Clear a field |
| `/remove <rows>` | Remove rows (`1,3,5` or `2-8` or `all --keep porsil`) |
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
| `/move <rows> <table>` | Move rows to another table |

### Calibration

| Command | Description |
|---------|-------------|
| `/calibrate <porsil_file>` | Calculate absolute scale from porsil data |
| `/calibrate <file> --ref NG3\|NG7` | Choose reference standard |
| `/calibrate <file> --qmin 0.01 --qmax 0.1` | Set Q range |
| `/calibrate --list-refs` | List available reference standards |

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

Config IDs are compact lowercase strings: `4m10a`, `4m2.5a`, `2.5m2.5a`. The 60Hz chopper frequency is omitted (default); 30Hz is shown: `4m10a30hz`. All matching is case-insensitive. Tab autocompletion is available.

### Presets

| Command | Description |
|---------|-------------|
| `/show presets` | List preset configurations from `preset_configs/` |
| `/show preset <name>` | Show preset parameters |
| `/apply preset <name> <config_id>` | Copy preset to active config |
| `/compare <a> <b>` | Side-by-side diff of two configs/presets |

Place JSON files in the `preset_configs/` folder. These are full `eqsans_reduction.json` files from previous experiments.

### Reduction

| Command | Description |
|---------|-------------|
| `/reduce <idx\|range\|all>` | Run data reduction (`/reduce 1`, `/reduce 1-4`, `/reduce all`) |
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
| `/stitch set <sample\|all> overlap <q1 q2 ...>` | Set overlap Q range (use `all` for all samples) |
| `/stitch set <sample\|all> target <idx\|config_id>` | Set normalization target (index or config like `4m10a`) |
| `/stitch run [sample]` | Execute stitching |
| `/stitch script [filename]` | Export stitch script |
| `/stitch save <name>` | Save stitch table |
| `/stitch load <name>` | Load stitch table |

**Smart Stitching:** The `/stitch smart` command analyzes overlap quality between curves and automatically removes redundant configurations:
- Requires 3-4 overlapping data points minimum
- Prefers overlaps in the middle region (not at edges)
- Detects when a middle config (mid-Q) adds no value
- Optionally consults LLM for complex decisions (`--llm` flag)
- Calculates quality scores (0-100) based on point count, error, and position

### Session

| Command | Description |
|---------|-------------|
| `/save session <name>` | Save full session (tables, configs, history) |
| `/load session <name>` | Restore session |
| `/help` | Show command reference |
| `/quit` | Exit (auto-saves session) |

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

### Run Matching

`/matchruns` groups runs by configuration, then matches by sample name:
- **All** scattering runs appear in the table (including background and empty beam)
- Background runs (banjo) get empty beam as their own background
- Transmission matched for every scattering run by sample name
- Use `/assign bkg <sample>` to change which sample is used as background

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
  models/         — Data models (run_metadata, working_table, session_state, config_id)
  integrations/   — External interfaces (oncat, json_builder, drtsans_runner)
  config/         — Presets and settings
  tui/widgets/    — TUI components (completable_input, catalog_table, working_table)
```

## Requirements

- Python 3.10+
- textual, rich, pandas, numpy, matplotlib, pyoncat
- `drtsans` CLI on PATH (for `/reduce`)
- Access to `/SNS/EQSANS/` filesystem and ONCat network
