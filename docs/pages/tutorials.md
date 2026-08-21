Every clip is the real terminal tool, driven live against one experiment —
IPTS&#8209;38603 — from raw counts to a shared, absolute-scale curve. Watch the
overview once end to end, then jump to any single task. Commands in the tables
link through to their full reference on the [Commands](commands.html) page.

## Start with the overview

| Video | What it covers | Length |
|---|---|---|
| **[The complete reduction, start to finish](https://www.youtube.com/watch?v=8acMTzVWoGU&list=PLa6AxzTbd0qI)** | Load the catalog, verify the run classes, match the working table, reduce (or export a runnable script), and stitch the configurations — then `/autopilot` runs the whole thirteen-step pipeline in a single command. | 3:07 |

## One task at a time

| Video | What it covers | Length |
|---|---|---|
| **[Just ask: natural-language control](https://www.youtube.com/watch?v=wOkLcJjeH0o&list=PLa6AxzTbd0qI)** | Type a request in plain English; the assistant shows the slash command it picked and runs it — `/load`, `/reclass`, `/matchruns`, even `/autopilot`. | 1:30 |
| **[Get the run classes right](https://www.youtube.com/watch?v=bZKJBk-zlEw&list=PLa6AxzTbd0qI)** | Read the Class column — empty, background, transmission, sample — and fix mistakes with `/reclass` by range, by list, or by whole sample. | 1:18 |
| **[Where every number comes from](https://www.youtube.com/watch?v=wYPZIy9FN4w&list=PLa6AxzTbd0qI)** | Presets and the four-layer parameter model behind `/show config` — drtsans default, preset, machine-physics file, and your own override, with which one wins. | 1:30 |
| **[Calibration files, resolved for you](https://www.youtube.com/watch?v=WS-nt1dmiL4&list=PLa6AxzTbd0qI)** | `/instrument` resolves sensitivity, dark current, beam flux and the detector offset per run and cycle — inspect them, pin a cycle, or take over by hand. | 1:18 |
| **[Put I(Q) on an absolute scale](https://www.youtube.com/watch?v=hxUabXguyrQ&list=PLa6AxzTbd0qI)** | `/calibrate` a porsil standard against a primary reference (NG3 / NG7) to find the scale factor and apply it to the configuration. | 1:19 |
| **[Build a detector mask — and check it](https://www.youtube.com/watch?v=5fcSuZ36e8Q&list=PLa6AxzTbd0qI)** | `/mask create` from a run's own image, then read the raw-vs-overlay plot: the beam stop, the dim tube-end bands, and any dead tubes. | 1:25 |
| **[Reduce your way, safely](https://www.youtube.com/watch?v=d52A2lhJlLo&list=PLa6AxzTbd0qI)** | Scope `/reduce` — everything, one sample, or only what's new — the empty-beam preflight that refuses bad rows, and run-now-in-parallel versus `/export script`. | 1:16 |
| **[Stitch the configurations together](https://www.youtube.com/watch?v=w7QWOMBZ09o&list=PLa6AxzTbd0qI)** | `/stitch` build and smart overlap analysis, manual control of the overlap window and configuration order, then merge into one curve per sample. | 1:25 |
| **[See, find, and share your results](https://www.youtube.com/watch?v=iCa7bt0_beI&list=PLa6AxzTbd0qI)** | `/plot` any curve from the prompt, `/list iq` your reduced files, and hand results off — a short share link, a zipped email, or a reduction-complete confirmation. | 1:11 |
| **[Autopilot, your way](https://www.youtube.com/watch?v=vlA-EklNncE&list=PLa6AxzTbd0qI)** | The `/autopilot` control surface — setup, filter and resume flags, plus `--from` to re-enter at any of the thirteen steps. | 1:17 |
| **[Pick up where you left off](https://www.youtube.com/watch?v=5NdCHzWO3ls&list=PLa6AxzTbd0qI)** | `/session save` and `/continue` so a multi-day reduction never loses its setup, and `--continue` to fold in newly collected runs without redoing the work. | 1:12 |

All twelve are on the [YouTube playlist](https://youtube.com/playlist?list=PLa6AxzTbd0qI&si=CxaD7iJVhCTF13sM). They pair with the written [step-by-step guide](guide.html) and the full [command reference](commands.html).
