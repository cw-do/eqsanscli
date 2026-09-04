---
topic: instrument-files
summary: How mask, flood, dark current, flux and the AgBe offsets are chosen for a run.
load: on-demand
updated: 2026-09-01
---

# Instrument calibration files

Six parameters are properties of the **accelerator cycle**, not of an instrument
configuration: `maskfilename`, `sensitivityfilename`, `darkfilename`,
`beamfluxfilename`, `detectoroffset`, `scalecomponents.detector1` (and
`sampleoffset`). They are resolved from the run number at runtime by
`services/instrument_files.py`.

**Do not write current filenames into this document or into a preset.** They go
stale within one cycle — that is exactly how the previous knowledge file ended up
naming 2025B files three cycles late. Filenames below are worked examples,
labelled with their cycle.

## When they are resolved — and when they are not

Resolution runs automatically at **`/matchruns`** (after presets are applied, so
the machine-physics files win over any preset values) and in **autopilot**
(step 4c, same resolver), and on demand at **`/instrument apply`**. It is gated by
`auto_instrument_files` (on by default; `/instrument off` disables it) and can be
locked to one cycle with `/instrument pin <cycle>`.

It does **not** run at **`/export script`** — that command emits whatever is
already in each config, so if the cycle's calibration has changed, run
`/matchruns` (or `/instrument apply`) *before* exporting or the script carries the
old files. `/instrument show` displays what is currently resolved.

**Precedence with presets.** `/apply preset <name|file.json>` **without** `--force`
never overwrites a value the config already has, so after `/matchruns` it leaves
the resolved calibration intact and only fills gaps. `/apply preset --force`
overwrites everything the preset carries — including these six params if a preset
(wrongly) contains them — and does **not** re-resolve afterwards; recover with
`/instrument apply --force`. Presets should not carry these six params at all.

**Re-resolving keeps your overrides.** A repeat `/matchruns` (or `/instrument
apply` without `--force`) updates the resolver-owned values to the newest files
but preserves an explicit `/set config` edit — the resolver treats a value it did
not write as a manual override and leaves it. Only `/instrument apply --force`
overrides a `/set config` edit.

## Where the files live

`/SNS/EQSANS/shared/NeXusFiles/EQSANS/<year><A|B>_mp/` per cycle:

| Artifact | Pattern | Example (2026B) |
|---|---|---|
| dark current | `EQSANS_<run>.nxs.h5` | `EQSANS_186198.nxs.h5` |
| flood / sensitivity | `Sensitivity_patched_<variant>_<tag>_<run>.nxs` | `Sensitivity_patched_thinPMMA_4m_186200.nxs` |
| beam flux | `bl6_flux_<cycle>_<month>_rebinned.txt` | `bl6_flux_2026B_aug_rebinned.txt` |
| AgBe calibration | `agbe_calibration/**/checkpoint.json` + `calibration_report.txt` | `detoffset = 66.763` |
| cycle mask | `masks/*mask.nxs` | `EQSANS_186104_mask.nxs` |

The machine-physics web page (`https://cw-do.github.io/eqsans_mp/`) is *generated
from* these folders by `<mp_root>/doc/generate.py`. The folder is the source of
truth; the page is a derived view with a publish lag.

## Which cycle applies

The newest cycle whose calibration campaign started at or before the data run —
its *anchor run*, the lowest dark/flood run in the folder. The whole set then
comes from that one cycle rather than being mixed (protocol CAL-03).

Anchor runs increase strictly across every cycle from 2011B (5702) to 2026B
(186198), so ordering by run number and ordering by cycle agree.

A data run can fall between a cycle's dark run and its flood runs — 186199 sits
between dark 186198 and floods 186200–186202. Taking the cycle as a unit is
deliberate: a flood characterises the detector, not the run, so using it for a
slightly earlier run is harmless, whereas pairing this cycle's dark with last
cycle's floods is not.

## Flood ↔ detector distance

Floods exist at three distances. Map the measured distance by clamping into that
range and taking the nearest, ties to the larger (protocol CAL-02):

| Measured | Flood |
|---|---|
| 1.3 m | `1o3m` |
| 2.0 m, 2.5 m | `2o5m` |
| 4 m | `4m` |
| beyond 4 m (5 m, 8 m, 9 m) | `4m` |

Within a cycle, prefer the `thinPMMA` variant. 2025B also carries `5mmPMMA` maps
whose run numbers are *higher*, so a purely run-driven pick would silently switch
variants. An undecorated distance tag beats a decorated one (`4m` over `4mSM`),
then the highest run — some cycles hold several flood generations (2022A has
four).

## Masks

A mask belongs to an **experiment**, not a configuration or a cycle. Search order,
first match wins:

1. the folder eqsanscli was started in — any `mask*.nxs`
2. `/SNS/EQSANS/IPTS-<current>/shared/`
3. `<cycle>_mp/masks/*mask.nxs` — the cycle default

Never another IPTS's shared folder (protocol CAL-04). Matching within a folder
uses the filename: the distance must agree, a matching wavelength is preferred,
`_FS` breaks ties for 30 Hz. `2p5` and `2o5` both mean 2.5 Å.

Worked example, IPTS-38773: `maskWS4m10A.nxs` serves `4m10a` and
`maskWS4m2p5A_FS.nxs` serves `4m2.5a`. A mask naming a different distance or
wavelength is not borrowed — a token-less mask (the cycle default) serves any
configuration.

Build one from a uniformly illuminated run (banjo, flood, empty cell) with
`/mask create <run>` — the run number alone locates the file, since the archive is
searched for it as Mantid would. It masks three things, each measured from the run
and then bounded by a convention:

| | measured | bound |
|---|---|---|
| beam stop | valley width between the flare walls in a horizontal cut through it | `× 1.0 + 1 pixel`; with no flare, the shadow `× 1.2 + 1 pixel` |
| tube-end bands | where the along-tube profile falls below **half the plateau** | floored at **11 pixels** |
| deviant tubes | tube median against a local same-pack baseline | dead below 0.3×, hot above 3×; the 5σ test only where the baseline exceeds 20 counts |

It writes `mask_<config>_<run>.nxs` into the working folder — named so the search
above finds it — and prints the arithmetic behind each size.

The band threshold is 0.5 and only 0.5. On every run measured so far it lands at
pixel 8-11, so the 11-pixel convention is what actually applies. Outside the band
a tube end still reads 15-20% below plateau (0.80 at pixel 11, 0.85 at pixel 13 on
run 186621) — that residual is the sensitivity map's job, not the mask's, which is
why the band stops where response *starts* rather than where it is complete.

At long wavelength and long flight path the direct beam **falls under gravity**,
by an amount going as the square of the wavelength, so some of it misses the stop
and lands above or below it: on a 9 m 15 Å banjo a broad
lobe of ~200 counts sits 60 mm below the stop against a plateau of 1. `/mask
create` finds and reports it but does not mask it unless asked (`--leak`), since
covering it costs low-Q coverage — a decision for the instrument scientist, not
the tool. `--leak` masks lobes **below** the stop, one disc each: neutrons fall,
so fallen beam is below, and `--leak-scale` enlarges those discs when the peak's
faint tail matters. A bright patch above the stop is rim flare or the
short-wavelength end of the band, is an arc rather than a blob, and gets a
`--disc` line to copy rather than a disc drawn round it.

The beam stop is measured from **cross cuts**, the procedure used by hand:

1. a vertical cut through the stop gives the centre of the deep valley — the
   centre's y;
2. a horizontal cut through that y gives the centre's x;
3. the **horizontal** valley width is the stop's diameter.

A cut through the stop shows a valley between two walls of flare, and the wall's
summit is the rim: flare is brightest just clear of the stop's edge. The width is
taken from the horizontal cut alone, because vertically the direct beam that fell
under gravity lands inside the shadow and makes it read narrow. Measured this way,
run 186636 (9 m, 15 Å) gives an 80 mm valley against a stop the instrument
scientist measures at 90 mm across, and run 186631 gives 66 mm at 4 m, where the
mask made by hand for that cycle is 68 mm across — two configurations, two
independent checks.

Three details are load-bearing, each from a real failure:

- The cut is anchored **on the beam**, not on the profile's minimum. Outside the
  flare the detector plateau is *darker* than the filled-in shadow — 1 count
  against 9 on 186636 — so the darkest point of the cut is 77 mm away from the
  stop. The shadow is a local dip between two walls, not the darkest place around.
- Cuts are sampled **per tube and per pixel row**, not binned by position: tubes
  sit 5.49 mm apart but their index order interleaves packs of four, so binning at
  the pitch aliases and moved the measured centre by 5 mm.
- A wall's summit is read as the intensity-weighted centre of its brightest bins,
  bounded to two bins either side. Unbounded, the vertical cut's lower wall — the
  gravity-dropped beam, merged with the rim flare and far broader — pulls the
  centre 6 mm down the detector.

The mask is deliberately wider than the visibly dark disc. That disc is the
umbra; around it the stop blocks part of the beam, and those pixels bias the
lowest-Q bins. On run 186621 (1.3 m, 1 Å) the dark disc ends at r ≈ 30 mm where
counts are still 0.30 of the surrounding level, reaching 0.88 at the 40.7 mm mask
edge. `/mask create` prints the measurement, scale and pad behind every radius.

A side that rises onto the plateau and stays up is not a wall, and a run with no
flare (186104 at 2.5 Å) is sized from the shadow instead: its equal-area radius or
half its longest extent, grown by 1.2 to compensate a threshold that stops short
of the rim. That path gives 34 mm on 186104, matching the mask made by hand for
that cycle. A measured valley width is not grown that way.

The shadow is still needed to seed the cuts, and is found by **local** contrast —
the image smoothed over ~5 pixels against ~41 — so a region qualifies by being
darker than its own surroundings. A global threshold cannot serve both a bright
run (core 12× below plateau) and a dim one (core ~2× below plateau, while Poisson
noise at a median of 4 counts puts ~9% of the detector under any cut). Among dark
regions, one whose own centroid does not lie inside it is discarded: it is a *ring*
of low contrast surrounding a bright complex, an artefact of the wide surround
window. On run 186636 such a ring covered 3804 px over 385 × 376 mm and was
otherwise chosen over the real 110 px shadow. When nothing credible is found the
beam is **not masked** and the reason is reported; `--beam-center` and
`--beam-radius` state it explicitly.

**Detector geometry, measured from the instrument definition.** 192 tubes ×
256 pixels over an active face of ~1049 × 1042 mm, so a pixel is 5.49 mm across
a tube and 4.09 mm along one — not square. Two consequences:

- Tube health is judged from the **median** along each tube against a **local**
  baseline of same-group neighbours: a mean is moved by the broad bright halo
  around the beam stop at long wavelength, which once flagged 29 tubes across the
  centre of a 15 Å run. Dead (<30% of baseline) and hot (>3×) are caught at any
  count level; the statistical test applies only where counts support it and the
  deviation exceeds 25%, since 10-20% gain variation is normal and is what the
  sensitivity map corrects.
- Front and back tubes alternate in **packs of four**. Physical order by x runs
  0, 4, 1, 5, 2, 6, 3, 7, 8, 12, …, consecutive *indices* are 10.94 mm apart
  while physical neighbours are 5.49 mm apart, and **x is not monotonic in tube
  index**. Tube comparisons are therefore made within a pack group; comparing
  odd-to-odd mixes the two populations and hides real outliers.
- The preview carries both scales: millimetres on the bottom and left, tube and
  pixel index on the top and right, with tube ticks placed at the tubes' real
  positions. Tube labels are exact only at the ticks, since the interleave makes
  index non-linear in x. It is drawn with tube index ascending left to right, so
  the millimetre axis descends: tube 0 sits at +x on this detector. The view is
  mirrored, not the coordinates — `--disc` and `--beam-center` stay in Mantid's
  frame.
- A circle drawn in index space is **not** a circle on the detector. For run
  186104's beam stop it agreed with the true disc only 87%, covering a region
  82.6 × 69.5 mm. The beam stop is masked in millimetres against the real pixel
  positions. `--beam-pad` keeps the machine-physics tool's units — pixels along a
  tube, ~4.09 mm — and is converted to millimetres internally; `--beam-scale`
  multiplies the fitted radius. Pixel index *is* linear in y, so the tube-end
  bands stay in index space.

The same mask is often reusable across detector distances, so a single
`mask_4m.nxs` in the working folder is a legitimate setup — it just cannot be
*assumed*, which is why an unmatched configuration warns rather than guessing.

## Offsets and scale components

`detoffset`, `scalecomp` and `samoffset` come from the cycle's AgBe calibration,
determined at the start of the cycle by the instrument scientist. `scalecomp` is
the `detector1` array `[x, y, z]` where `y = scale_all × scale_y`.

Worked examples: 2026B `scalecomp = [1.004251, 1.057915, 1]`, `detoffset = 66.763`,
`samoffset = 285.0`. 2026A `[1.003571, 1.052902, 1]`, `detoffset = 77.244`.
Historical, from `202502_agbe/34965/banjo`: `scalecomp = [1.002, 1.0728155533894388, 1]`,
`detoffset = 84.38081`, `samoffset = 300` (banjo rack, ti-rack).

`samoffset` is the most experiment-dependent of the six: it tracks the sample
rack / stage in use, which in practice **changes from experiment to experiment**,
not just from cycle to cycle. Treat the cycle's AgBe value as a starting point and
override it per experiment with `/set config <id> sampleoffset <mm>`. That
override is preserved across a later `/matchruns` (the resolver treats it as a
manual edit), so you set it once — only `/instrument apply --force` would reset it
back to the cycle value.

No AgBe calibration exists before cycle 2026A. Older data reduces without these
values rather than with invented ones (protocol CAL-05).
