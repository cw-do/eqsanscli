---
topic: protocol
summary: The rules a reduction must satisfy. Authoritative — code and docs follow this file.
load: always
updated: 2026-08-17
---

# EQSANS reduction protocol

Numbered rules a catalog, working table, configuration set and stitch table must
satisfy for the reduction to be trustworthy. Each rule states its **severity** and
whether it is **enforced** in code today.

- **blocking** — the reduction is wrong or impossible; refuse.
- **warning** — proceed, but the user must see it and decide.
- **info** — worth stating so nobody is surprised later.

Enforcement:
- `enforced` — code checks it, file named.
- `advisory` — code reports it but does not act.
- `unenforced` — protocol only; nothing checks it yet.

Rule ids are permanent (see `README.md`, editing rule 4).

---

## CAT — catalog and classification

**CAT-01** · blocking · enforced (`commands/catalog.py`, `services/matching_service.py`)
Every run carries a `run_class` before matching: `scattering`, `transmission`,
`bkg_scatt`, `bkg_trans`, `empty_trans`, `empty_scatt`, or `ignore`. Classes come
from the title at load time and are correctable with `/reclass` — the title is a
hint, not the truth.

**CAT-02** · blocking · advisory (`match_runs` warns; nothing refuses)
Each configuration that has scattering runs must also have an `empty_trans` run
at the **same** configuration. Without it the rows cannot reduce (see EMP-01).

**CAT-03** · warning · enforced (`match_runs` warns)
More than one `empty_trans` in a configuration means a choice was made silently.
The first is used; the user picks explicitly with `/set --config <id> emp <run>`.

**CAT-04** · warning · enforced (`match_runs` warns)
Same for more than one `bkg_scatt` per configuration.

**CAT-05** · info · enforced (`classify_title`)
Background keywords are tested **before** the empty-beam pattern, so
`emptycell` / `emptyticell` / `ti-cell` / `banjo` / `bkg` / `background` classify
as background, not as empty beam. `empty` / `emp` / `emt` as standalone words, or
anything followed by `beam`, are empty beam.

**CAT-06** · warning · unenforced
A run whose title states a configuration that disagrees with its ONCat
`detector_distance` / `wavelength` is mislabelled. Trust the metadata, flag the
title. (Real case: 2026B's AgBe series had a 1.3 m block labelled 6 Å whose
scattering runs were at 2.5 Å.)

**CAT-07** · info · unenforced
Runs of implausibly short duration for their role (a flood of a few seconds, a
transmission of hours) are usually aborted or mislabelled measurements.
Duration thresholds: **TBD**.

---

## EMP — empty beam

**EMP-01** · blocking · enforced (`services/reduction_service.py:blocking_problems`, `/reduce`, autopilot Step 3)
Every row being reduced has an empty-beam run. It supplies **both** the beam
centre (`beamCenter.runNumber`) and the empty transmission
(`emptyTransmission.runNumber`) — there is no fallback for the beam centre.

**EMP-02** · blocking · enforced (`match_runs`, `/set --config … emp`)
The empty-beam run is from the same configuration as the row. A beam centre from
a different detector distance is meaningless.

**EMP-03** · info · enforced (`match_runs`, `assign_background`)
Empty beam is a calibration measurement, not a background. Background-cell and
empty-beam rows therefore get **no** background subtraction of their own.

---

## TBL — working table completeness

**TBL-01** · blocking · enforced (`blocking_problems`)
Every row has a scattering run.

**TBL-02** · warning · enforced (`advisory_problems`, autopilot Step 3)
Every sample row has its own transmission run, at the same configuration.
Reduction proceeds without one — drtsans accepts a transmission *value* instead —
but the result is not what most experiments intend.

**TBL-03** · warning · enforced (`advisory_problems`, autopilot Step 3)
Every sample row has a background scattering run, except the background sample
itself (EMP-03) and experiments that deliberately measure no background.

**TBL-04** · warning · enforced (`services/protocol.py`)
`bkgtrans` is present whenever `bkg` is. A background subtracted without its own
transmission correction is inconsistent with how the sample was treated.

**TBL-05** · warning · enforced (`advisory_problems`)
Thickness is a positive number. Typical range 0.01–1 cm; outside that, suspect a
unit error. Default when unstated: 0.1 cm.

**TBL-06** · blocking · enforced (`services/protocol.py`)
A run appears in only one role per configuration. The same run used as both
sample and background, or as both transmission and empty beam, is an error.

**TBL-07** · warning · enforced (`sync_state_configs` straddle check)
All rows in one configuration resolve to the same calibration cycle. Runs
spanning a cycle boundary would otherwise be reduced with one cycle's calibration
while belonging to another.

---

## BKG — background

See `background-selection.md` for how to choose one.

**BKG-01** · blocking · enforced (`services/protocol.py`)
The background run is from the same configuration as the row it serves.
`/assign bkg` guarantees this by construction; a manual per-row `/set` can break it.

**BKG-02** · blocking · enforced (`services/protocol.py`)
A row's background is not the row's own scattering run.

**BKG-03** · warning · unenforced
All non-background rows in an experiment use the *same* background sample unless
the user deliberately says otherwise. A table where some rows use `banjo` and
others `emptycell` is usually a mistake.

---

## CAL — calibration files

See `instrument-files.md` for the resolution order.

**CAL-01** · blocking · enforced (`instrument_files.verify_paths`, `/instrument check`)
Every referenced mask, flood, dark and flux file exists and is non-empty.

**CAL-02** · blocking · enforced (`flood_distance_for`)
The flood (sensitivity) matches the detector distance: 1.3 m → `1o3m`,
2.0/2.5 m → `2o5m`, 4 m **and anything longer** → `4m`.

**CAL-03** · warning · enforced (`resolve_for_run`, cycle-coherent selection)
Mask, flood, dark, flux and the AgBe offsets come from one cycle, chosen by run
number — not mixed across cycles, and not carried over from a previous
experiment's preset.

**CAL-04** · blocking · enforced (`resolve_mask`)
A mask is never taken from another IPTS's shared folder: those are frequently
unreadable to other users, and a mask from another experiment is the wrong mask.

**CAL-05** · warning · enforced (`resolve_for_run` reports it)
Detector offset, scale components and sample offset are only meaningful if an
AgBe calibration exists at or before the run. None exists before cycle 2026A —
older data reduces without them rather than with invented values.


---

## MSK — building a mask

Rules for `/mask create`, which produces the `maskfilename` CAL-01 then checks.
`instrument-files.md` carries the measurements and the reasoning; these are the
rules a mask must satisfy.

**MSK-01** · blocking · enforced (`services/mask_service.py`, `commands/mask.py`)
A mask is built from a **uniformly illuminated** run — banjo, flood or empty cell
— and belongs to the configuration that run was taken at. The configuration comes
from the run's own logs and goes into the filename (`mask_<config>_<run>.nxs`),
which is what makes the resolver find it (CAL-04).

**MSK-02** · blocking · enforced (`find_beam_stop`)
When the beam stop cannot be located credibly, **no beam mask is written** and the
reason is reported: nothing compact and dark, a core no darker than its
surroundings with no flare walls to fall back on, an implied radius beyond any
EQSANS stop, or a centre too far from the detector centre. Loosening a threshold
to force a detection is not the fix — state it with `--beam-center` /
`--beam-radius`, or leave it out with `--no-beam`. A wrong beam mask is worse than
none.

**MSK-03** · blocking · enforced (`beam_from_cross_cuts`)
The stop's **size** comes from the horizontal cut only — the valley width between
the flare wall summits. The vertical cut supplies the centre and nothing else,
because direct beam that fell under gravity lands inside the shadow and makes the
vertical width read narrow. A run whose cut has no flare walls is sized from the
shadow instead, and the report says which applied.

**MSK-04** · warning · enforced (`find_beam_stop`, reported by `how_sized`)
The mask extends past the **umbra** into the penumbra. The visibly dark disc is
where the stop blocks everything; outside it the beam is still partly blocked, and
those pixels bias the lowest-Q bins. A shadow-derived radius is therefore grown; a
measured valley width is not, since it already reaches the rim.

**MSK-05** · warning · enforced (`build_plan`, reported by `how_banded`)
Tube-end bands are measured — where response falls below half the plateau — and
then floored at the long-standing 11-pixel convention, which in practice is what
applies. An explicit `--top` / `--bottom` overrides the floor deliberately.

**MSK-06** · warning · enforced (`find_direct_beam_leaks`, `build_plan`)
Direct beam that fell past the stop is **always reported and never masked unless
asked**: covering it costs low-Q coverage, which is the instrument scientist's
call, not the tool's. `--leak` masks lobes **below** the stop only — neutrons fall,
so that is where fallen beam goes; a bright patch above it is rim flare and gets a
`--disc` line to copy instead.

**MSK-07** · warning · enforced (`find_deviant_tubes`)
Tube health is judged from the **median** along a tube against a **local** baseline
of same-pack neighbours, with the statistical test applied only where counts
support it. When a run cannot support the judgement at all, no tubes are flagged
and the reason is printed — masking noise is worse than masking nothing.
Detection is whole-tube, so a dead *segment* needs `--tubes`.

**MSK-08** · blocking · enforced (`write_mask`)
A written mask is read back through the path drtsans itself uses and the masked
pixel count must match what was requested. A mask that cannot be read back fails
at creation, not during a reduction.

**MSK-09** · info · enforced (`shapes_to_mask`)
Beam stop and discs are masked in **millimetres against real pixel positions**;
only the tube-end bands are index-space, because pixel index is linear in y while
tube index is not a spatial coordinate at all. Coordinates are millimetres from
the detector centre, `+y` up.

**MSK-10** · warning · unenforced
Every mask is reviewed against its `_compare.png` before it is used in a
reduction: the overlay should cover the beam, both tube ends and any bad tubes,
and nothing else. Nothing checks that a review happened.

**MSK-11** · warning · unenforced
A mask should be rebuilt when the beam stop or its position changes within an
experiment. Nothing compares a stored mask against the run it is about to serve.

---

## CFG — configuration parameters

See `configurations.md` for values and rationale.

**CFG-01** · blocking · enforced (`services/protocol.py`)
`qmin < qmax`, and both lie inside the Q range the configuration can actually
measure.

**CFG-02** · warning · unenforced
When `fitinelasticincoh` is on, `incohfit_qmin`/`incohfit_qmax` lie inside the
configuration's Q range and away from its edges — every wavelength bin must
produce Q values within that window.

**CFG-03** · info · enforced (`config_manager`, `instrument_files`)
Parameters resolve in four tiers: drtsans template defaults < JSON preset <
machine-physics instrument files (run-aware) < explicit `/set config`. A value the
user set is never overwritten automatically.

**CFG-04** · warning · unenforced
A custom TOF cut (`cuttofmin`/`cuttofmax` narrowed for a monochromatic effect) is
recorded in the output filename, so the profile is not confused with a
full-band reduction. Convention: suffix `_tofcut`.

---

## SCL — absolute scale

See `absolute-scale.md`.

**SCL-01** · warning · enforced (autopilot Steps 6–8 report it)
Absolute intensity requires a standard sample (porsil by default) reduced at
scale 1.0 and calibrated against the reference. Without one, output is on a
relative scale — say so rather than implying absolute units.

**SCL-02** · blocking · unenforced
Each configuration's `standardabsolutescale` comes from a standard measured **in
that configuration**.

**SCL-03** · warning · unenforced
A calibrated scale factor far from the values seen in recent cycles indicates a
bad fit or the wrong reference. Plausible range: **TBD** (recent presets carry
≈0.19–0.23 for 4 m 10 Å).

---

## STC — stitching

See `stitching.md`.

**STC-01** · info · enforced (`merge_service`)
A sample needs two or more configurations to stitch; one is passed through.

**STC-02** · blocking · enforced (`_scaling_factor` raises)
Each adjacent pair has a non-empty overlap containing at least two points of the
target profile. Autopilot widens the window (6, 8, 10, 14, 20 points) before
giving up.

**STC-03** · warning · enforced (`_default_target_index`)
The normalisation target is the lowest-Q configuration, since it carries the
absolute scale.

**STC-04** · blocking · enforced (`build_stitch_table` group keys)
30 Hz frame-skipping data stitches its own `frame_0` + `frame_1` pair and is
never mixed with 60 Hz data for the same sample.

**STC-05** · warning · unenforced
Scale factors applied while stitching stay near 1 — a large factor means the
configurations disagree, usually from a wrong background, transmission or
absolute scale rather than a stitching problem. Threshold: **TBD**.

---

## Open items for the instrument scientist

Rules marked **TBD** need a number: CAT-07 (durations), SCL-03 (scale-factor
range), STC-05 (stitch scale-factor tolerance). Rules marked `unenforced` are the
backlog, and `services/protocol.py:unenforced_rules()` lists them from code so the
backlog cannot rot unnoticed. MSK-10 and MSK-11 are among them: both need a
decision from the instrument scientist about what "reviewed" and "changed" should
mean mechanically.

The rules `services/protocol.py` checks are decidable from session state alone.
The rest need a run's metadata, the reduced output, or a judgement — `check()`
running clean does **not** mean the protocol is satisfied, only that the
mechanical part is.
