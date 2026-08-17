---
topic: stitching
summary: Combining I(Q) from several configurations into one profile.
load: on-demand
updated: 2026-08-17
---

# Stitching

A sample measured at several configurations yields several I(Q) files covering
different Q ranges. Stitching scales them onto a common target and merges them
into one `merged_<sample>_*_Iq.txt`.

## Ordering and target

Profiles are ordered **low-Q first**, which for standard configurations means
descending detector distance then descending wavelength (`4m10a` before
`2.5m2.5a`).

The normalisation target is the lowest-Q configuration, because it carries the
absolute scale (protocol STC-03). Priority when picking automatically: `4m10a`,
then any 8 m, then `4m2.5a`, then `2.5m2.5a`, else the first. If a configuration
was calibrated against a standard in this session, that one is preferred as the
target.

## Overlap regions

Each adjacent pair needs a Q window where both profiles have data, containing at
least two points of the target (protocol STC-02). The scale factor is the ratio of
summed intensities over that window.

Too narrow a window gives a noisy factor; too wide includes Q where one
configuration is unreliable (near its own limits). Autopilot starts from a
centred 6-point window and widens through 8, 10, 14, 20 points if stitching fails.

`/stitch smart` additionally scores overlap quality and can drop a configuration
whose Q range is redundant — worth reviewing rather than accepting blindly, since
a "redundant" configuration is sometimes the better-measured one.

## Frame skipping (30 Hz)

At 30 Hz each run produces two profiles, `frame_0` (low-Q, long wavelength) and
`frame_1` (high-Q, short wavelength). These stitch to **each other**, and a 30 Hz
sample is grouped separately from the same sample's 60 Hz data — never mixed
(protocol STC-04).

## Reading the result

Scale factors near 1 mean the configurations agree. A large factor is a signal
about the *reduction*, not the stitching: suspect the absolute scale, the
background, or the transmission for one of the configurations (protocol STC-05).

A visible step or kink at an overlap usually means one configuration's background
subtraction is off, or the overlap window sits where one profile is already
unreliable.

## What stitching does not fix

Stitching scales profiles onto each other. It cannot repair a wrong background, a
missing transmission, or a bad absolute scale — those produce a smooth-looking
merged curve that is quantitatively wrong. Review the per-configuration profiles
before merging.
