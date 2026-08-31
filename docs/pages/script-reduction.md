This is the older, manual way to reduce EQSANS data: you edit a Python template
and run it through `drtsans`. It is the layer this tool automates — the same
`EQVar` / `reduceNow` wrapper the CLI drives, and exactly what
[`/export script`](commands.html#cmd-export-script) writes out. Use it when you want full
control, need to reproduce a reduction without the tool, or are following the
legacy [EQSANS site](https://sites.google.com/view/eqsans/script-reduction).

> **Not sure which to use?** The [step-by-step guide](guide.html) does all of this
> from the interactive tool, with the run pairing, calibration lookup and stitching
> handled for you. Reach for a script when you want to see and change every line —
> or feed the tool's [`/export script`](commands.html#cmd-export-script) output back in
> here as a starting point.

## 1 · Get onto the analysis cluster

Sign in to [analysis.sns.gov](https://analysis.sns.gov) with your XCAMS/UCAMS
credentials — the same login as the IPTS system — and open a terminal. Work in the
experiment's shared folder:

```
cd /SNS/EQSANS/IPTS-#####/shared/
```

Pull in the EQSANS reduction tools (note the space after the dot):

```
. /SNS/EQSANS/shared/usertools/eqsans_setup.sh
```

That puts the template scripts and helpers on your path. The wrapper itself lives
in `/SNS/EQSANS/shared/script/eqsanstools`.

## 2 · Copy and edit a template

Start from `reduce_template.py` (or `reduce_template2.py`) and edit it with `gedit`
or `pluma`. Look up run numbers at [oncat.ornl.gov](https://oncat.ornl.gov), or
ask your local contact for a template already pointed at the current cycle's
calibration files.

The template's header carries the machine-physics files for the cycle — the
sensitivity (flood), dark current, beam flux and the detector/sample offsets. **These
change every accelerator cycle**, so check them with your local contact before you
trust a template written for an earlier one:

```python
MP_DIR   = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025B_mp/"
FLOOD_4m = MP_DIR + "Sensitivity_patched_thinPMMA_4m_167517.nxs"
DARK_FILE = MP_DIR + "EQSANS_167516.nxs.h5"
FLUX_FILE = MP_DIR + "bl6_flux_2025B_Aug_rebinned_4m.txt"
```

## 3 · Describe one reduction with EQVar

Every reduced curve is one `EQVar` object: you set its runs and parameters, then
hand it to `reduceNow`. A minimal sample looks like:

```python
from eqsans_drtsans_script import EQVar, reduceNow

eq = EQVar()
eq._outputdir = '/SNS/EQSANS/IPTS-12345/shared/output/'
eq._ipts      = 12345
eq._thickness = 0.1                 # sample thickness, cm
eq._samscatt  = '10003'             # sample scattering run
eq._samtrans  = '20003'             # sample transmission run
eq._bkgscatt  = '10001'             # background scattering run
eq._bkgtrans  = '10002'             # background transmission run
eq._empty     = '10000'             # empty beam (beam centre + transmission ref)
eq._maskfilename = '/SNS/EQSANS/IPTS-12345/shared/useThisMask.nxs'
eq._numqbins  = 80
eq._filename  = 'sample1'           # output name base
reduceNow(eq)
```

A production template loops this over a list of runs, setting one `EQVar` per
configuration per sample — see `reduce_template.py` for the worked pattern.

### The runs

| Attribute | What it is |
|---|---|
| `_samscatt` | Sample scattering run number |
| `_samtrans` | Sample transmission run number |
| `_bkgscatt` | Background (blocked/solvent) scattering run |
| `_bkgtrans` | Background transmission run |
| `_empty` | Empty-beam run — supplies the beam centre and the transmission reference |
| `_beamcenter` | Beam-centre run, if measured separately from the empty beam |
| `_filterbytimestart` / `_filterbytimestop` | Reduce only a time window of the run |

### The sample

| Attribute | What it is |
|---|---|
| `_ipts` | IPTS number |
| `_thickness` | Sample thickness, cm |
| `_filename` | Output filename base (e.g. `sample1`) |
| `_instrumentname` | `EQSANS` |

### Output and binning

| Attribute | What it is | Typical |
|---|---|---|
| `_outputdir` | Output folder | — |
| `_numqbins` | Number of Q bins | 40–80 |
| `_qbintype` | `linear` or `log` | `log` |
| `_qmin` / `_qmax` | Output Q range | `0.006` / `0.1` |
| `_wavelengthstep` | Wavelength bin, Å | `0.1` |
| `_cuttofmin` / `_cuttofmax` | TOF cutoffs, µs | `1000` / `3000` |
| `_sampleaperturesize` | Sample aperture, mm | `10` |
| `_standardabsolutescale` | Absolute-scale factor (from a standard) | — |

### Masking and calibration

| Attribute | What it is |
|---|---|
| `_maskfilename` | Full path to a mask `.nxs` |
| `_usedefaultmask` | Use the instrument-managed default mask |
| `_sensitivityfilename` | Sensitivity (flood) file — cycle-specific |
| `_darkfilename` | Dark-current file — cycle-specific |
| `_beamfluxfilename` | Beam-flux file — cycle-specific |
| `_sampleoffset` / `_detectoroffset` | Geometry offsets — cycle-specific |
| `_scalecomponents` | Per-panel scale, e.g. `[0.975, 1.030, 1]` |

### Inelastic / incoherent correction

| Attribute | What it is |
|---|---|
| `_fitinelasticincoh` | Fit the inelastic incoherent correction |
| `_selectminincoh` | Search for the minimum incoherent level |
| `_incohfit_qmin` / `_incohfit_qmax` | Q window used for that fit |
| `_outputwavelengthdependentprofile` | Also write I(Q, λ) |
| `_elasticref` / `_elasticreftrans` / `_elasticrefthickness` | Elastic-reference run, its transmission and thickness |

The full list and the drtsans JSON key each one maps to is on the
[parameters](parameters.html) page — that table is the same mapping the exported
script uses, so it applies here verbatim.

## 4 · Run it

```
drtsans reduce_template.py
```

`drtsans` runs the current production build. Two other builds exist for testing new
features before they are released:

```
drtsans --qa  reduce_template.py     # release-candidate build
drtsans --dev reduce_template.py     # latest development build
```

Use the plain `drtsans` unless your local contact asks you to try `--qa` or
`--dev`.

## 5 · Read the output

Each reduction writes into `_outputdir`:

| File | Contents |
|---|---|
| `*_Iq.dat` | 1-D reduced I(Q) |
| `*_Iqxqy.dat` | 2-D I(qx, qy) |
| `*.png` | Plot images |
| `*.json` | The reduction parameters that were used |
| `*.out` | Reduction log |
| `*_trans.txt` | Fitted transmission |
| `*_raw_trans.txt` | Raw transmission |

## 6 · Stitch configurations

A template that measured a sample in more than one configuration merges them with
drtsans' `stitch_profiles`. Overlap windows are listed low-Q to high-Q and
`target_profile_index` picks which curve the others scale onto (0 = the first):

```python
from drtsans.stitch import stitch_profiles

overlap = [0.07, 0.08]              # [MergeAB_min, MergeAB_max, ...] increasing Q
stitched = stitch_profiles([iq1, iq2], overlap[0:2], target_profile_index=0)
save_iqmod(stitched, output_directory + 'merged_' + sample + '_Iq.txt',
           sep=' ', float_format='%.6E')
```

The merged curve is written as `merged_<sample>_Iq.txt`.

## Generate a starter script automatically

Since 2025 a helper drafts the whole thing from the catalog. After
`eqsans_setup.sh`:

```
drtsans eqsans_guesslist.py 12345
```

For IPTS-12345 it writes three files into the current folder:

- `catalog_12345.csv` — the full run catalog
- `runlist_12345.dat` — run numbers, transmission numbers and sample names
- `reduce12345_generated.py` — a reduction script, **for review before you run it**

Check the pairings and calibration files, then:

```
drtsans reduce12345_generated.py
```

This is the same job the interactive tool does with [`/load ipts`](commands.html#cmd-load)
+ [`/matchruns`](commands.html#cmd-matchruns) — and if you would rather stay in a
script but let the tool do the pairing, run those and
[`/export script`](commands.html#cmd-export-script) to get a filled-in template back.

## More

- Legacy guide with screenshots: [sites.google.com/view/eqsans/script-reduction](https://sites.google.com/view/eqsans/script-reduction)
- Setting up the Python tools (video): [youtu.be/O7DwtdnficI](https://youtu.be/O7DwtdnficI)
- Script-based reduction (video, older `python` syntax — use `drtsans`): [youtu.be/cmGThfVlpRU](https://youtu.be/cmGThfVlpRU)

> The script wrapper is a community tool and, as its own header notes, *not
> officially supported by SNS*. When something in the reduction looks wrong, the
> [protocol](protocol.html) page lists what a trustworthy reduction has to satisfy.
