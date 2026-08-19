A **configuration** is one instrument setting — detector distance, wavelength and
chopper frequency — written compactly as `4m10a`, `2.5m2.5a`, `8m12a`. Every
parameter below belongs to a configuration, not to a run, and every row reduced
in that configuration uses the same set.

## Where a value comes from

Four tiers, each overriding the one above:

1. **drtsans template defaults** — whatever the reduction package assumes.
2. **JSON presets** in `preset_configs/` — the starting point for a known
   configuration, applied automatically by `/matchruns`.
3. **Machine-physics files** — the six cycle-specific calibration values, resolved
   from the run number at match time. These change every cycle and are never
   hand-edited into a preset.
4. **Your edits** — `/set config <id> <name> <value>`. These win over everything
   and are preserved when the resolver runs again.

`/show config <id>` prints the effective value of every parameter with the tier it
came from, and `/instrument show` explains the machine-physics choices.

## How a parameter reaches the reduction

`/export script` writes a standalone Python file that drives the drtsans wrapper.
Each parameter becomes an attribute on an `EQVar` object:

```python
from eqsans_drtsans_script import EQVar, reduceNow

for i in range(len(samscatt)):
    eq = EQVar()
    eq._outputdir = output_directory
    eq._qmin = 0.005              # <- a configuration parameter
    eq._qmax = 0.9
    eq._numqbins = 100
    eq._maskfilename = '/SNS/EQSANS/IPTS-38681/shared/mask_4m10a.nxs'
    eq._samscatt = str(samscatt[i])
    eq._samtrans = str(samtrans[i])
    eq._bkgscatt = str(bkgscatt[i])
    eq._bkgtrans = str(bkgtrans[i])
    eq._empty    = emptybeam[i]
    eq._thickness = float(sample_thick[i])
    reduceNow(eq)
```

So the three names for one setting are: `qmin` in the tool, `eq._qmin` in the
exported script, and `configuration.Qmin` in the drtsans JSON. The table below
gives all three.

To change one, edit it in the tool and re-export rather than editing the script —
the tool records provenance, the script does not:

```
/set config 4m10a qmin 0.006
/export script
```
