---
topic: index
summary: What lives in knowledge/, and the rules for editing it.
load: never
updated: 2026-08-17
---

# EQSANS reduction knowledge base

Instrument knowledge that eqsanscli — and any agent driving it — consults when
making a decision. **`protocol.md` is the authority**: if code, a preset, or a
doc disagrees with it, `protocol.md` wins and the other thing is a bug.

This folder replaced `preset_configs/knowledge.md`, a single 20 KB file that had
drifted into contradicting both itself and the code (it named 2025B cycle files
as current, described a mask fallback that no longer exists, and stated
`--sample` matching was substring-based two sections after correctly stating it
was exact-unless-wildcard).

## Files

| File | Holds | Loaded |
|---|---|---|
| `protocol.md` | numbered, checkable rules a reduction must satisfy | always |
| `instrument-files.md` | how mask / flood / dark / flux / offsets are chosen | on demand |
| `configurations.md` | per-configuration parameters and *why* those values | on demand |
| `background-selection.md` | what counts as a background and how it is paired | on demand |
| `absolute-scale.md` | standard-sample calibration to absolute intensity | on demand |
| `stitching.md` | combining configurations into one I(Q) | on demand |
| `troubleshooting.md` | failure signatures → cause → fix | on demand |

`load:` in each file's header controls whether `services/knowledge.py` includes
it in every LLM call (`always`) or only when a caller asks for that topic
(`on-demand`). Keep `always` to `protocol.md` alone — everything else is paid for
in tokens on every natural-language command.

## Editing rules

1. **One fact, one home.** If two files would state the same thing, one of them
   links instead. Contradiction is the failure mode this folder exists to stop.
2. **No command reference here.** How to *drive* eqsanscli (command syntax,
   natural-language mappings) lives in `services/llm_handler.py:_SYSTEM_PROMPT`,
   and for humans in `README.md`. This folder is about the *physics and the
   protocol*, not the CLI. Mentioning a command as the fix for a rule violation
   is fine; teaching command syntax is not.
3. **No hardcoded cycle paths or run numbers as current values.** Which flood,
   dark, flux, mask and offsets apply is resolved from the run number at runtime
   (`services/instrument_files.py`). Cite a filename only as a worked example,
   and say which cycle it came from.
4. **Rules carry ids and never get renumbered.** `EMP-01` means the same thing
   forever. Retire a rule by marking it `withdrawn`, do not reuse its id.
5. **Say whether a rule is enforced.** Each rule states `enforced` (code checks
   it today, with the file that does), `advisory` (reported but not blocking), or
   `unenforced` (protocol only — a human or agent has to check). Phase 1 of the
   review work turns `unenforced` rules into validators.
6. **Numbers need provenance.** A tolerance or typical value gets a source: a
   cycle's calibration report, a specific experiment, or "instrument scientist
   judgement". If nobody has decided yet, write `TBD` — never invent a number.
7. **Update the header** `updated:` date when you change a file.

## Who edits what

Physics, tolerances and protocol: the instrument scientist. An agent may draft,
but must not invent numbers or silently change a rule's severity — propose the
change and say what it is based on.
