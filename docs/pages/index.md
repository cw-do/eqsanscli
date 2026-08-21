> **Prefer to watch?** Twelve short screencasts walk through the whole tool — see
> the [video tutorials](tutorials.html): an end-to-end overview, then one clip per task.

## What it is

**eqsanscli** reduces EQSANS small-angle neutron scattering data at SNS/ORNL. You
give it an experiment number; it fetches the catalog from ONCat, works out which
runs go together, applies the right parameters for each instrument configuration,
runs the reduction through drtsans, stitches the configurations into one I(Q) and
plots the result.

The tedious parts it takes over:

- **Pairing runs.** Every scattering run needs its transmission, its background,
  that background's transmission, and an empty beam *from the same
  configuration*. Doing that by hand across 50 runs and 3 configurations is where
  mistakes come from.
- **Getting the calibration right.** Dark current, sensitivity, beam flux and the
  AgBe offsets change every accelerator cycle. The tool reads them from the
  machine-physics folders by run number, so a preset written last cycle does not
  quietly reduce this cycle's data with last cycle's flood.
- **Writing the script.** `/export script` produces a standalone Python file that
  reproduces exactly what was run — the same reduction, without the tool.

## Getting started

```bash
ssh analysis.sns.gov
cd /SNS/EQSANS/shared/script/eqsanstools-cli
source .venv/bin/activate
python -m eqsanscli
```

Commands are typed at the `eqsans>` prompt and all begin with `/`. Anything typed
without a `/` is sent to a language model that translates it into commands —
convenient, but explicit commands are what to use when it matters.

## The shortest possible reduction

```
/load ipts 38681          # fetch the catalog
/matchruns                # pair every scattering run, apply presets and calibration
/show table               # check what it decided
/reduce all               # run the reductions
/stitch smart             # combine configurations into one I(Q)
/plot merged_*.txt        # look at the result
```

Or, when the experiment is routine, the same thing in one command:

```
/autopilot 38681
```

The [step-by-step guide](guide.html) walks the same path with the output you
should expect at each stage, and what to do when a step reports a problem.

## How it decides things

| Question | Answer | Where |
|---|---|---|
| Which runs pair together? | classification from the run title, then matching on configuration | [protocol](protocol.html#sec-CAT) |
| Which calibration files? | the newest machine-physics cycle at or before the run | [knowledge](knowledge.html#kb-instrument-files) |
| Which parameters? | drtsans defaults < JSON preset < machine physics < your `/set config` | [parameters](parameters.html) |
| What must be true before reducing? | 48 numbered rules, 38 of them checked by code | [protocol](protocol.html) |

Every number the tool produces comes with its derivation — how a beam-stop radius
was measured, which cycle a flood came from, why a row cannot reduce. If you find
one that does not explain itself, that is a bug worth reporting.

## Finding things

The search box at the top of every page covers commands, parameters, protocol
rules and section headings. Press <kbd>/</kbd> from anywhere to jump into it.

- [Commands](commands.html) — all 52, with sub-forms and examples
- [Parameters](parameters.html) — what each reduction parameter is, and how it
  reaches the exported script as `eq._name`
- [Protocol](protocol.html) — the rules a trustworthy reduction satisfies
- [Instrument knowledge](knowledge.html) — detector geometry, calibration files,
  backgrounds, absolute scale, stitching
