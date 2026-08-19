# The documentation site

Static HTML in this folder, servable straight from GitHub Pages.

## Publishing it

On GitHub: **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`**.
The site then appears at `https://cw-do.github.io/eqsanscli/`. Nothing else is
needed — no workflow, no build step on the server side. `.nojekyll` is present so
the files are served exactly as generated.

## Rebuilding it

```bash
python3 docs/generate.py
```

System python3, no dependencies. Commit the regenerated `*.html` and
`search-index.json` along with whatever change prompted them.

## What is generated and what is written by hand

| | Source |
|---|---|
| `commands.html` | `commands/registry.py` (the list), `SKILL.md` tables (one-liners), each command module's `_USAGE` (full help) |
| `parameters.html` | `services/script_exporter.py` (the `EQVar` mapping), `knowledge/configurations.md` (descriptions), `preset_configs/*.json` (values), `services/instrument_files.py` (which are machine-physics owned) |
| `protocol.html` | `services/protocol.py`, which parses `knowledge/protocol.md` |
| `knowledge.html` | the `knowledge/` documents |
| `changelog.html` | `docs/CHANGELOG.md` |
| `index.html`, `guide.html`, the parameters preamble | **hand-written**, in `docs/pages/*.md` |

So: to change a command's description edit `SKILL.md`, to change what a parameter
means edit `knowledge/configurations.md`, and to change the introduction or the
walkthrough edit `docs/pages/`. Nothing about the tool is described here that is
not described somewhere the tool itself can be checked against —
`tests/test_docs.py` fails if a command or parameter reaches the site with no
description, if the generator breaks, or if an internal link goes stale.

## Files

- `generate.py` — the builder
- `collect.py` — pulls content out of the code, one collector per source
- `md.py` — a small Markdown renderer (no dependency is available on the analysis machines)
- `pages/` — hand-written prose
- `site.css`, `search.js` — styling and client-side search over `search-index.json`
