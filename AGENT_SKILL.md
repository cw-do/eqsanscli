# Merged into SKILL.md

The agent documentation is now a single file: **[`SKILL.md`](SKILL.md)**.

It covers both front ends — the interactive TUI and the headless JSON protocol
this file used to describe — with one command reference, one set of rules and one
workflow. Read that instead.

**Why:** two hand-maintained copies diverged in both directions. Each had gained
commands the other never learned (`/refresh catalog`, `/reclass`, `/stitch
reorder` on one side; `/list iqxqy`, `/session list`, `/settings` and the shell
commands on the other), and the headless copy still described preset application
as a mandatory manual step, which `/matchruns` has done automatically since
v0.10.0.

This stub stays so anything pointing at the old path lands here rather than
reading a half-copy.
