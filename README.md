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
/load ipts 35884                         # Fetch catalog from ONCat (adds run_class)
/show catalog                            # Review catalog with Class column
/reclass 172804-172810 scatt             # Fix any misclassified runs (optional)
/matchruns                               # Auto-match trans/bkg/empty using run_class
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

# Calibrate each config and auto-apply the scale factor
/calibrate porsil_4m10a_Iq.dat --applynow
/calibrate porsil_2.5m2.5a_Iq.dat --applynow

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
| `/autopilot current` | Use current IPTS/catalog from session (preserves `/reclass` overrides) |
| `/autopilot <ipts> --continue` | Reduce only NEW runs (reuse saved calibration/configs/bkg) |
| `/autopilot --continue` | Continue from saved session in outputdir (infers IPTS) |
| `/autopilot <ipts> --standard <name>` | Use named sample as calibration standard (default: auto-detect porsil) |
| `/autopilot <ipts> --samples <name1,name2>` | Only reduce specific samples |
| `/autopilot <ipts> --exclude <name1,name2>` | Reduce all except named samples |
| `/autopilot <ipts> --thickness <cm>` | Set sample thickness for all rows |
| `/autopilot <ipts> --bkg <sample>` | Use named sample as background (config-aware) |
| `/autopilot <ipts> --config <id>` | Reduce only the specified configuration |
| `/autopilot <ipts> --force` | Re-reduce all rows (ignore done/modified status) |
| `/autopilot <ipts> --fresh` | Force a clean catalog reload + table re-match (ignore in-memory state). Does NOT clear `/set config` overrides |
| `/autopilot current --from <N>` | Skip steps 1..(N-1) of autopilot. Requires catalog + working table already in session. See `/autopilot` for the 13-step list. Common: `--from 5` (skip catalog/match/presets) |
| `/autopilot <ipts> --exclude Y5 --bkg emptyticell --thickness 0.15` | Combined options |

All flags are composable. Execution order: thickness → bkg → samples → exclude → config.
Setup (thickness, bkg) applies to the full table first, then filters (samples, exclude, config) trim rows down.

### Incremental Reduction (`--continue`)

After the initial autopilot run, if you collect more data on the same IPTS:
```
/autopilot 35884 --continue
```
This refreshes the catalog from ONCat, merges new runs into the saved table, and reduces only new data. Calibration scale factors, config parameters, and background/empty beam assignments are reused from the previous run. Stitching is re-run on all data (old + new).

At the end of each autopilot, a full session is saved to `{outputdir}/autopilot_session.json`. This file is also loadable via `/session load {path}` for manual inspection and modification.

### Re-reduction Status

When you change a row's parameters (`/set`, `/assign bkg`) or config parameters
(`/set config`, `/apply preset`) after reduction, affected rows automatically change
status from `done` to `modified`. Autopilot will re-reduce `modified` rows.
Use `--force` to re-reduce all rows regardless of status.

**Examples:**
```
/autopilot 35884                                         # Reduce everything
/autopilot current                                       # Use current session (after /reclass etc.)
/autopilot current --bkg emptyticell --exclude Y5        # Current session + options
/autopilot 35884 --continue                              # Only new runs, reuse saved calibration
/autopilot --continue --samples NewSample                # Continue + filter to new sample only
/autopilot current --standard porsilb1                   # Use porsilb1 as calibration standard
/autopilot 38397 --standard agb1 --bkg banjo             # Custom standard + custom bkg
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
| `/load ipts <number>` | Fetch catalog from ONCat (REPLACES current catalog, wipes `/reclass` overrides) |
| `/refresh catalog` | Re-fetch the current IPTS catalog while PRESERVING `/reclass` overrides; reports new runs since last fetch. Use mid-experiment. |
| `/show catalog` | Display loaded catalog (with Class column: S, T, BkgS, BkgT, EmpT, N=ignored) |
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
| `/reclass <runs> <class>` | Override run classification. Classes: `scatt`, `trans`, `bkg`, `bkgtrans`, `empty`, `emptyscatt`, `sample`, `ignore` (aliases `i`, `n`) |
| `/reclass --sample <name> <class>` | Reclass all runs whose title contains `<name>` (e.g. `--sample BkgG sample`, `--sample banjo i`) |
| `/matchruns` | Auto-match transmission/background/empty runs using `run_class`. REBUILDS the table (resets row status) |
| `/matchruns --update` | Add only new scattering runs to the EXISTING table; preserves `done` rows and assignments. Use after `/refresh catalog` |
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
| `/calibrate <file> --applynow` | Calculate AND auto-apply scale to matching config in working table |
| `/calibrate <file> --ref NG3\|NG7` | Choose reference standard |
| `/calibrate <file> --qmin 0.01 --qmax 0.03` | Set Q range (defaults shown) |
| `/calibrate --list-refs` | List available reference standards |

### Share & Email

| Command | Description |
|---------|-------------|
| `/share <file\|pattern>` | Share files via here.now (anonymous, 24h link) |
| `/share *.png` | Share all PNG files |
| `/share *_4m10a_Iq.dat` | Share matching I(Q) files |
| `/zipnsend <email>` | Zip `merged*.txt` from outputdir and email |
| `/zipnsend <email> --pattern <glob>` | Zip custom file pattern and email |
| `/zipnsend <email> --dir <path>` | Zip from specific directory |
| `/zipnsend <email> --subject <text>` | Custom email subject |
| `/confirm [ipts]` | Confirm IPTS data reduction is complete |
| `/confirm --comment <text>` | Confirm with comment |

**Share:** Files are uploaded to [here.now](https://here.now) using only Python stdlib (no external packages). Anonymous uploads expire in 24 hours. Max 50 MB total. Searches output directory first, then current directory.

**Zipnsend:** Zips matching files and emails using `mailx`/`mail`. Max 25 MB (suggests `/share` if larger). Default pattern is `merged*.txt` from the output directory.

**Confirm:** Calls `/SNS/software/nses/bin/confirm-data` to mark IPTS data reduction as complete in the SNS experiment tracking system. Autopilot calls this automatically at the end.

```
/zipnsend ccd@ornl.gov                                  # merged files
/zipnsend ccd@ornl.gov --pattern "*_Iq.dat"             # all Iq files
/zipnsend ccd@ornl.gov --pattern "*.png" --subject "IPTS-38397 plots"
```

### LLM

| Command | Description |
|---------|-------------|
| `/models` | List available LLM models |
| `/models <name>` | Switch LLM model |

### Configuration

| Command | Description |
|---------|-------------|
| `/config list` (alias: `/list configs`) | List configs in the table plus any stored extras (e.g. unassigned clones) |
| `/config clone <src> <dst>` | Copy a config to a new name so it can be edited independently (`<dst>` must contain `<src>`'s config ID: `4m10a` → `4m10a_v2`) |
| `/config rows <id>` | List rows currently referencing `<id>` |
| `/show config <id>` | Show all reduction parameters (75 params from eqsans_reduction.json) |
| `/set config <id> <param> <value>` | Set a config parameter |
| `/set config all <param> <value>` | Apply to every config in the table; sticky default for future ones |
| `/set <row> cfg <name>` | Reassign a row to a different (typically cloned) config; `none` clears (aliases: `config`, `configuration`) |
| `/set --sample <name> cfg <new>` | Bulk-reassign rows matching `<name>` |
| `/show outputdir` | Show output directory |
| `/set outputdir <path>` | Set output directory |
| `/set ipts <number>` | Set IPTS number |
| `/set drtsans <version>` | Set drtsans version (`default`, `dev`, `qa`) |

Config IDs are compact lowercase strings: `4m10a`, `4m2.5a`, `2.5m2.5a`. The 60Hz chopper frequency is omitted (default); 30Hz is shown: `4m10a30hz`. All matching is case-insensitive. Tab autocompletion is available.

**Per-row config variants.** Use `/config clone` when only a subset of rows at the
same physical config needs different params (e.g. a different mask file):

```
/config clone 4m10a 4m10a_v2                    # create the variant
/set --sample MySample cfg 4m10a_v2             # point only those rows at it
/set config 4m10a_v2 maskfilename mask_v2.nxs   # diverge from 4m10a
/set <row> cfg none                             # clear override → use physical config
```

Three rules keep variants predictable:

- **The clone name must contain the source config ID** — `4m10a` → `4m10a_v2`,
  `4m10a-mask2`, `porsil_4m10a`. A bare name like `mask2` is rejected: preset
  matching, cycle-file discovery and low-Q-first stitch ordering read the physics
  back out of the config name.
- **A row can only take a config with the same physics.** Assigning a `4m10a` row
  to `8m10a` parameters is rejected — an override changes reduction parameters,
  not the measured geometry.
- **Output filenames never change.** They stay
  `<sample>_<physical config>_Iq.dat`, so stitching, `merged_*` files and
  `/autopilot --continue` behave the same whether or not a row uses a clone.

### Instrument calibration files (machine physics)

Dark current, sensitivity (flood), beam flux, and the AgBe-derived detector
offset / scale components / sample offset are **cycle**-specific: they live in
`/SNS/EQSANS/shared/NeXusFiles/EQSANS/<cycle>_mp/` and change every cycle.
eqsanscli resolves them from each config's **run number** — automatically at
`/matchruns` and in autopilot — so you never edit a preset path by hand again.

| Command | Description |
|---------|-------------|
| `/instrument show` | What each config resolves to, which cycle it came from, and what `apply` would change |
| `/instrument list [run]` | Cycle inventory (dark / floods / flux / AgBe per cycle) plus what a run resolves to |
| `/instrument apply [--force]` | Re-resolve now. `--force` also replaces values you set with `/set config` |
| `/instrument pin <cycle>` | Always use one cycle (e.g. `2026A`), ignoring run numbers — for reproducing earlier work |
| `/instrument unpin` | Back to run-number selection |
| `/instrument off` / `on` | Disable/enable the automatic resolution |
| `/instrument check` | Verify every referenced calibration file still exists |

**Masks.** A mask belongs to an *experiment*, not to an instrument
configuration, so it is never taken from another IPTS's shared folder — those
are frequently unreadable to other users. Search order, first match wins:

1. the folder you started eqsanscli in — any `mask*.nxs`
2. `/SNS/EQSANS/IPTS-<current>/shared/` — the current experiment's own folder
3. `<cycle>_mp/masks/*mask.nxs` — the cycle's default mask

Within a folder the file whose name best describes the configuration wins: the
distance must agree, a matching wavelength is preferred, and `_FS` breaks ties
for 30 Hz frame-skipping. So with `maskWS4m10A.nxs` and `maskWS4m2p5A_FS.nxs`
present, `4m10a` takes the first and `4m2.5a` the second. A mask naming a
*different* distance or wavelength is never borrowed; a mask with no tokens at
all (like the cycle default `EQSANS_186104_mask.nxs`) serves any configuration.

`/matchruns` and autopilot print which mask each configuration will use. If none
is found, you get a warning naming every location searched plus the command to
set one:

```
Masks per configuration:
  4m10a     maskWS4m10A.nxs      (from IPTS-38773/shared)
  4m2.5a    maskWS4m2p5A_FS.nxs  (from IPTS-38773/shared)
  1.3m2.5a  EQSANS_186104_mask.nxs  (from 2026B masks/; cycle default)
```

**How a run maps to files.** The chosen cycle is the newest one whose
calibration campaign started at or before the run (its lowest dark/flood run),
and the whole set comes from that one cycle — this cycle's dark is never paired
with last cycle's floods. Sensitivity is then picked for the detector distance:

| Measured distance | Flood used |
|---|---|
| 1.3 m | `1o3m` |
| 2.0 m | `2o5m` |
| 2.5 m | `2o5m` |
| 4 m | `4m` |
| 8 m, or any distance beyond 4 m | `4m` |

Within a cycle: `thinPMMA` is preferred over other flood variants, an
undecorated tag beats a decorated one (`4m` over `4mSM`), then the highest run
number — some cycles hold several flood generations.

**What it will not do.** It never overwrites a value you set with
`/set config` (those show as *kept*; use `--force` to override). It never
invents AgBe calibration for runs before 2026A, and never reaches back more
than one cycle for a flux file — in both cases the existing value stays and the
reason is reported. Values it owns are marked `mp:<cycle>` in `/show config`.

The `preset_configs/*.json` files still carry these six parameters as an
offline fallback for `/instrument off`; when resolution is on, the
machine-physics folder wins over the preset.

**Empty beam is mandatory.** It supplies the beam centre (`beamCenter.runNumber`)
as well as the empty transmission, so `/reduce` refuses up front for any selected
row without one, naming the rows and configurations and how to fix them. Missing
transmission or background is a warning only. Escape hatches:
`/reduce <rows> --skip-missing` (reduce the valid rows) and `/reduce <rows> --force`
(send them to drtsans anyway). `/autopilot` checks the same thing at Step 3 and
skips unreducible rows at reduction time.

## Building a mask

`/mask create <run>` builds a detector mask from a run's own 2D count image —
use a uniformly illuminated run (banjo, flood, empty cell). It masks:

1. the **beam-stop shadow** — the low-count blob near the centre, as a physical
   circle (an ellipse in index space, since pixels are finer along a tube than
   tubes are apart);
2. the **low-response bands** at both ends of every tube, measured but never
   smaller than the long-standing 11-pixel convention;
3. **deviant tubes** — compared within their front/back group. Front and back
   tubes alternate in *packs of four* on this detector: grouping that way gives a
   median absolute deviation of 2.7 counts against 19.9 for odd/even, so
   comparing odd-to-odd hides real outliers.

The file lands in the folder you started eqsanscli in, named for the
configuration read from the run's own logs — `mask_4m2o5a_186104.nxs` — which is
exactly what the resolver reads back, so `/matchruns` and `/instrument` pick it
up with no further action. Alongside it go a `_compare.png` (raw vs overlay —
always look at it) and a `.params.json` recording how it was made.

| Option | |
|---|---|
| `--ipts <n>` | experiment holding the run (default: the session's) |
| `--dry-run` | preview PNG only, no mask file |
| `--beam-scale <f>` / `--beam-pad <f>` | enlarge the beam circle (scale multiplies; pad is in pixels along a tube) |
| `--no-beam` | skip the beam stop |
| `--top <n>` / `--bottom <n>` | force band sizes |
| `--tubes <a,b>` / `--tube-sigma <f>` / `--no-tubes` | control tube masking |
| `--outdir <dir>` | write elsewhere (then it is not auto-discovered) |

`/mask list` shows every mask discoverable from where you are, in the order the
resolver prefers them.

Mantid does the reading and writing, via the `drtsans` command — the same way
`/reduce` runs. The geometry itself is computed in eqsanscli, and the written
file is verified by reading it back through `Load` + `ExtractMask`, the path
drtsans itself uses.

## Knowledge base

Instrument knowledge lives in `knowledge/`, one file per decision domain, with
`knowledge/protocol.md` as the authority — numbered rules (`EMP-01`, `BKG-03`, …)
each carrying a severity and whether code enforces it today. If code, a preset or
a doc disagrees with `protocol.md`, the other thing is the bug.

| File | Holds |
|---|---|
| `protocol.md` | the rules a reduction must satisfy (loaded on every LLM call) |
| `instrument-files.md` | how mask / flood / dark / flux / offsets are chosen |
| `configurations.md` | per-configuration parameters and why |
| `background-selection.md` | what counts as a background and how it pairs |
| `absolute-scale.md` | standard-sample calibration |
| `stitching.md` | combining configurations |
| `troubleshooting.md` | failure signatures → cause → fix |

`knowledge/README.md` states the editing rules: one fact one home, no command
reference (that lives in `llm_handler`), no hardcoded cycle paths, rule ids are
permanent, numbers need provenance or `TBD`. `tests/test_knowledge.py` enforces
the structural half of that, including that rule cross-references resolve and
that the docs still agree with the code.

This replaced `preset_configs/knowledge.md`, a single file that had drifted into
contradicting itself and the code.

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
| `/reduce --new` | Reduce only rows whose status is not `done` (newly added, modified, or previously errored) |
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

**Preset overlaps:** `/stitch smart` looks up predefined overlap Q ranges for known config pairs in `preset_configs/stitch_overlaps.json` BEFORE falling back to the auto-overlap algorithm. Add your own entries there for configs you use regularly. Current presets include:
- `4m10a` ↔ `2.5m2.5a`: `[0.05, 0.06]`
- `4m10a` ↔ `4m2.5a`: `[0.04, 0.045]`
- `8m12a` ↔ `4m10a`: `[0.025, 0.028]`
- `8m12a` ↔ `2.5m2.5a`: `[0.04, 0.05]`
- `frame0` ↔ `frame1` (30Hz frame-skipping): `[0.05, 0.06]`

When displayed in `/stitch smart` output, pairs using preset overlaps are marked `(preset)`, others `(auto)`.

**30Hz frame-skipping support:** Both `/stitch build` and `/stitch smart` detect rows where `frequency=30` and split them into `frame_0` (low-Q, ~4m 9.5Å) and `frame_1` (high-Q, ~4m 2.5Å) entries. The frame files are expected to be named `{sample}_{config}_frame_0_Iq.dat` and `{sample}_{config}_frame_1_Iq.dat`. 30Hz groups are kept separate from 60Hz configs for the same sample.

**Config ordering (low-Q → high-Q):** Stitch groups automatically sort configs from lowest-Q to highest-Q:
- Larger detector distance first (8m → 4m → 2.5m → 1.3m)
- For same distance, longer wavelength first (4m10a → 4m2.5a)

The stitch algorithm assumes this ordering. If you manually reorder with `/stitch reorder`, you must preserve low-Q → high-Q.

**Default stitch target (reference config):** `/stitch build` and `/stitch smart` choose the target in this priority order:
1. `4m10a` (if present)
2. Any `8m*` config
3. `4m2.5a`
4. `2.5m2.5a`
5. First config in the group (lowest-Q)

Override with `/stitch set <idx|sample|all> target <config_id>`.

**Merged output filename:** `merged_{sample}_{lowq_config}_..._{highq_config}_Iq.txt`
The config names appear in the filename in low-Q → high-Q order (e.g., `merged_porsil_8m12a_4m10a_2.5m2.5a_Iq.txt`).

### Session

| Command | Description |
|---------|-------------|
| `/continue` | Resume most recent session (autosave or named). Cross-cwd via breadcrumb at `~/.eqsanscli/last_autosave` |
| `/session list` | List saved sessions with save date/time (sorted newest-first) |
| `/session save [name]` | Save current session |
| `/session load <name>` | Load a saved session (accepts an absolute path too) |
| `/help` | Show full command reference (long) |
| `/help --simple` | Show inline 7-step quickstart workflow |
| `/guide` | Toggle a side pane with the quickstart steps (auto-scrolls when content exceeds height) |
| `/quit` | Exit (auto-saves session) |

**Auto-save:** Session is saved automatically after every command, after background jobs complete (`/reduce`, `/autopilot`), and on exit. The autosave file lives at `{cwd}/.eqsanscli/sessions/_autosave.json` — i.e. it follows the working folder. `/continue` also reads a global breadcrumb at `~/.eqsanscli/last_autosave` (written whenever a non-empty session autosaves) so it can find your most recent work even if you re-launched from a different directory. On startup, if a previous session exists, you'll see a hint to type `/continue` to resume.

### Note (per-outputdir log)

| Command | Description |
|---------|-------------|
| `/note add "<text>"` | Add a manual timestamped note to `{outputdir}/NOTE.md` |
| `/note show [N]` | Show the last N entries (default 30) |
| `/note path` | Print the NOTE.md path |
| `/note clear --yes` | Delete NOTE.md |

All state-changing commands are auto-logged to `NOTE.md` (read-only commands like `/show`, `/help`, `/note` are skipped). Format includes timestamp and IPTS tag. The intent is "replay the listed commands in order to reproduce this reduction".

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

**Status bars:**
- **Header:** session name, IPTS, active table, row count, output directory, LLM token usage
- **Footer:** LLM model, drtsans version (`drtsans`, `drtsans --dev`, `drtsans --qa`), keyboard shortcuts

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

**Run Classification (`run_class`):** When a catalog is loaded (`/load ipts`), each run is
automatically classified based on its title prefix (S-, T-) and keywords (banjo, empty, etc.).
The classification is stored as a `run_class` column in the catalog:

| Class | Label | Description |
|-------|-------|-------------|
| `scattering` | S | Sample scattering |
| `transmission` | T | Sample transmission |
| `bkg_scatt` | BkgS | Background scattering (banjo, emptyticell, emptycell, ti-cell, bkg, etc.) |
| `bkg_trans` | BkgT | Background transmission |
| `empty_trans` | EmpT | Empty beam transmission (required for reduction) |
| `empty_scatt` | EmpS | Empty beam scattering (rare) |

**Classification keywords:**
- **Empty beam:** standalone `empty`, `emp`, `emt`, or followed by `beam` (word boundary — won't match `emptyticell`)
- **Background:** `bkg`, `banjo`, `background`, `emptycell`, `emptyticell`, `ti-cell`, `ticell`
- Background keywords are checked **before** empty beam, so `emptyticell` → background, not empty beam

If a run is mislabeled (e.g. title says `T-` but it's actually scattering), use `/reclass`:
```
/reclass 172804 scatt               # Fix single run
/reclass 172804-172810 scatt        # Fix a range
/reclass 172804,172806 trans        # Fix specific runs
/reclass 172804-172810 sample       # Treat as normal sample (S-→scatt, T-→trans)
/reclass --sample BkgG sample       # All BkgG runs: S-BkgG→scatt, T-BkgG→trans
/reclass --sample Bkg* sample       # Wildcard matching
/reclass --sample emptyticell bkg   # Force all emptyticell runs to background
```

The `sample` target is useful when a sample name contains a background keyword (e.g. `S-BkgG`).
Instead of forcing all runs to scattering, it respects the S-/T- prefix in each title.

The `run_class` persists across session save/load. After reclassing, run `/matchruns` to
rebuild the working table.

`/matchruns` reads `run_class` from the catalog, groups runs by configuration, then matches by sample name:
- **All** scattering-type runs appear in the table (including bkg/empty scattering)
- Background runs (banjo) get empty beam as their own background
- Transmission matched for every scattering run by sample name within the same config
- Use `/assign bkg <sample>` to change which sample is used as background
- **Warnings** are shown if multiple empty beams or multiple backgrounds are found in the same configuration — user should decide which to use

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
