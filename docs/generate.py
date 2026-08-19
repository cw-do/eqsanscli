#!/usr/bin/env python3
"""Build the eqsanscli documentation site into `docs/`.

    python3 docs/generate.py

Static HTML, no build tools and no CDN: it runs with the system python3 on the
analysis machines and the result is servable straight from GitHub Pages
(Settings -> Pages -> main branch, /docs folder).

The reference pages are **generated from the code**, so they cannot drift:
commands from `commands/registry.py`, parameters from the exported-script mapping
and the presets, rules from `knowledge/protocol.md`. Only the prose pages under
`docs/pages/` are written by hand.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import collect  # noqa: E402
import md  # noqa: E402

PAGES = [
    ("index.html", "Introduction"),
    ("guide.html", "Step-by-step guide"),
    ("commands.html", "Commands"),
    ("parameters.html", "Parameters"),
    ("protocol.html", "Protocol"),
    ("knowledge.html", "Instrument knowledge"),
    ("changelog.html", "Change log"),
]

SECTION_ORDER = [
    "Catalog & Loading", "Working Table", "Multiple working tables",
    "Configuration", "Masks", "Reduction", "Stitching", "Data & Plotting",
    "Session", "Notes and comparison", "Settings and shell", "The tool itself",
    "Other",
]

INDEX: list[dict] = []


def record(title: str, page: str, anchor: str, kind: str, detail: str = "") -> None:
    INDEX.append({"t": title, "p": page, "a": anchor, "k": kind, "d": detail[:160]})


def shell(page: str, title: str, body: str, *, toc: list | None = None,
          lede: str = "") -> str:
    links = []
    for href, label in PAGES:
        current = ' class="current"' if href == page else ""
        links.append(f'<a href="{href}"{current}>{label}</a>')
    nav = "\n".join(links)
    lede_html = f'<p class="lede">{lede}</p>' if lede else ""
    toc_html = ""
    if toc:
        items = "".join(
            f'<a href="#{a}" class="lvl{lvl}">{md.inline(t, link_rules=False)}</a>'
            for lvl, t, a in toc if lvl <= 3)
        toc_html = f'<nav class="toc"><div class="toc-title">On this page</div>{items}</nav>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — eqsanscli</title>
<link rel="stylesheet" href="site.css">
</head>
<body>
<header>
  <div class="masthead">
    <div class="bar">
      <div class="brand">
        <a href="index.html"><div class="title">eqsans<b>cli</b></div></a>
        <div class="tagline">Spallation Neutron Source &middot; Beam Line 6 &middot;
          data reduction tool &middot; v{collect.version()}</div>
      </div>
      <div class="spacer"></div>
      <div class="search-wrap">
        <input id="q" type="search" placeholder="Search commands, parameters, rules  (/)"
               autocomplete="off" spellcheck="false">
        <div id="results" hidden></div>
      </div>
    </div>
  </div>
  <nav class="subnav"><div class="bar"><div class="tabs">{nav}</div></div></nav>
</header>
<main>
  {toc_html}
  <article>
    <h1 class="page-title">{title}</h1>
    {lede_html}
    {body}
  </article>
</main>
<footer><div class="bar">
  <span>EQSANS &middot; SNS/ORNL &middot; <a href="https://github.com/cw-do/eqsanscli">github.com/cw-do/eqsanscli</a></span>
  <span>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} by <code>docs/generate.py</code></span>
</div></footer>
<script src="search.js"></script>
</body>
</html>
"""


# --------------------------------------------------------------------------

def page_from_markdown(filename: str, page: str, title: str, lede: str = "") -> str:
    source = open(os.path.join(HERE, "pages", filename)).read()
    body, headings = md.render(source, link_commands=True)
    for lvl, text, anchor in headings:
        if lvl <= 3:
            record(text, page, anchor, "page", title)
    return shell(page, title, body, toc=headings, lede=lede)


def commands_page() -> str:
    commands = collect.commands()
    by_section: dict[str, list] = {}
    for c in commands:
        by_section.setdefault(c.section if c.section in SECTION_ORDER else "Other", []).append(c)

    parts = [f'<p class="lede">All {len(commands)} commands — what each does, its '
             f'sub-forms and worked examples. <code>/help</code> in the tool gives the '
             f'same reference offline.</p>']
    toc = []
    for section in SECTION_ORDER:
        group = by_section.get(section)
        if not group:
            continue
        anchor = md.slug(section)
        toc.append((2, section, anchor))
        parts.append(f'<h2 id="{anchor}">{section}<a class="anchor" href="#{anchor}">#</a></h2>')
        for c in sorted(group, key=lambda x: x.name):
            a = f"cmd-{md.slug(c.name)}"
            toc.append((3, "/" + c.name, a))
            record("/" + c.name, "commands.html", a, "command", c.summary)
            parts.append(f'<section class="cmd" id="{a}">')
            parts.append(f'<h3>/{c.name}<a class="anchor" href="#{a}">#</a>'
                         f'<span class="src">{c.handler}.py</span></h3>')
            parts.append(f'<p class="summary">{md.inline(c.summary)}</p>')
            if c.variants:
                parts.append('<div class="table-wrap"><table><thead><tr><th>Form</th>'
                             '<th>What it does</th></tr></thead><tbody>')
                for phrase, text in c.variants:
                    record("/" + phrase, "commands.html", a, "command", text)
                    parts.append(f"<tr><td><code>/{phrase}</code></td>"
                                 f"<td>{md.inline(text)}</td></tr>")
                parts.append("</tbody></table></div>")
            if c.examples:
                parts.append("<pre class=\"example\"><code>" +
                             "\n".join(c.examples) + "</code></pre>")
            if c.usage:
                parts.append(f'<details><summary>Full in-CLI help</summary>'
                             f'<pre class="usage"><code>{md.html.escape(c.usage)}</code></pre>'
                             f'</details>')
            parts.append("</section>")
    return shell("commands.html", "Commands", "\n".join(parts), toc=toc)


def parameters_page() -> str:
    params = collect.parameters()
    intro = open(os.path.join(HERE, "pages", "parameters.md")).read()
    body, headings = md.render(intro, link_commands=True)
    toc = list(headings) + [(2, "Every parameter", "every-parameter")]

    rows = []
    for p in params:
        record(p.name, "parameters.html", f"param-{md.slug(p.name)}", "parameter",
               p.description or (f"eq.{p.eqvar}" if p.eqvar else p.owner))
        seen = sorted({str(v) for v in p.values.values()})
        if p.owner == "machine physics":
            # The presets do carry values for these, but the resolver replaces
            # them per run — showing the preset path would be showing a stale one.
            values = '<span class="unset">resolved per run</span>'
        elif len(seen) == 1:
            values = f"<code>{md.html.escape(seen[0][:48])}</code>"
        elif seen:
            values = '<span class="varies">varies by config</span>'
        else:
            values = '<span class="unset">not in presets</span>'
        rows.append(
            f'<tr id="param-{md.slug(p.name)}">'
            f'<td><code>{p.name}</code><br><span class="pdesc">{md.inline(p.description)}</span></td>'
            f'<td>{f"<code>eq.{p.eqvar}</code>" if p.eqvar else "&mdash;"}</td>'
            f'<td>{f"<code>{p.json_key}</code>" if p.json_key else "&mdash;"}</td>'
            f'<td><span class="owner owner-{md.slug(p.owner)}">{p.owner}</span></td>'
            f"<td>{values}</td></tr>")

    body += ('<h2 id="every-parameter">Every parameter'
             '<a class="anchor" href="#every-parameter">#</a></h2>'
             '<p>Set any of these with <code>/set config &lt;id&gt; &lt;name&gt; &lt;value&gt;</code>. '
             'The <em>in the script</em> column is the attribute the exported reduction '
             'script assigns on its <code>EQVar</code> object. Parameters marked '
             '<em>machine physics</em> are resolved from the cycle folders by run number '
             'at <code>/matchruns</code> time — whatever a preset says for those is '
             'ignored.</p>'
             '<div class="table-wrap"><table class="params"><thead><tr>'
             '<th>Parameter</th><th>In the script</th><th>drtsans JSON key</th>'
             '<th>Owned by</th><th>Preset value</th></tr></thead><tbody>'
             + "".join(rows) + "</tbody></table></div>")

    # per-configuration values for the parameters that actually differ
    varying = [p for p in params if len({str(v) for v in p.values.values()}) > 1]
    if varying:
        configs = sorted({c for p in varying for c in p.values})
        head = "".join(f"<th>{c}</th>" for c in configs)
        body += ('<h2 id="by-configuration">Values by configuration'
                 '<a class="anchor" href="#by-configuration">#</a></h2>'
                 '<p>What the shipped presets in <code>preset_configs/</code> actually contain, '
                 'for the parameters that differ between configurations.</p>'
                 f'<div class="table-wrap"><table class="params"><thead><tr><th>Parameter</th>'
                 f'{head}</tr></thead><tbody>')
        for p in varying:
            cells = "".join(
                f"<td>{md.html.escape(str(p.values.get(c, '—'))[:28])}</td>" for c in configs)
            body += f"<tr><td><code>{p.name}</code></td>{cells}</tr>"
        body += "</tbody></table></div>"
        toc.append((2, "Values by configuration", "by-configuration"))

    for lvl, text, anchor in headings:
        record(text, "parameters.html", anchor, "page", "Parameters")
    return shell("parameters.html", "Parameters", body, toc=toc,
                 lede="Every reduction parameter: what it is, who sets it, and how it "
                      "reaches the exported script.")


def protocol_page() -> str:
    rules = collect.rules()
    groups: dict[str, list] = {}
    for r in rules:
        groups.setdefault(r.prefix, []).append(r)
    names = {"CAT": "Catalog and classification", "EMP": "Empty beam",
             "TBL": "Working-table completeness", "BKG": "Background",
             "CAL": "Calibration files", "MSK": "Building a mask",
             "CFG": "Configuration parameters", "SCL": "Absolute scale",
             "STC": "Stitching"}
    enforced = sum(1 for r in rules if r.enforcement == "enforced")
    parts = [f'<p class="lede">{len(rules)} rules a reduction must satisfy. '
             f'{enforced} are checked by code today; the rest are the backlog. '
             f'This page is generated from <code>knowledge/protocol.md</code>, which is the '
             f'authority — if code disagrees with a rule, the code is the bug.</p>']
    toc = []
    for prefix, group in sorted(groups.items()):
        anchor = f"sec-{prefix}"
        title = f"{prefix} — {names.get(prefix, prefix)}"
        toc.append((2, title, anchor))
        parts.append(f'<h2 id="{anchor}">{title}<a class="anchor" href="#{anchor}">#</a></h2>')
        for r in group:
            a = f"rule-{r.id}"
            record(r.id, "protocol.html", a, "rule",
                   r.text.splitlines()[0] if r.text else "")
            body, _ = md.render(r.text, link_commands=True)
            parts.append(
                f'<section class="rule" id="{a}">'
                f'<div class="rule-head"><code class="rule-id">{r.id}</code>'
                f'<span class="badge sev-{r.severity}">{r.severity}</span>'
                f'<span class="badge enf-{r.enforcement}">{r.enforcement}</span>'
                + (f'<span class="enf-by">{md.inline(r.enforced_by)}</span>'
                   if r.enforced_by else "")
                + f'<a class="anchor" href="#{a}">#</a></div>{body}</section>')
    return shell("protocol.html", "Protocol", "\n".join(parts), toc=toc)


def knowledge_page() -> str:
    parts = ['<p class="lede">Instrument physics and conventions the tool consults when it '
             'makes a decision — geometry, calibration files, backgrounds, absolute scale, '
             'stitching. Generated from the <code>knowledge/</code> folder.</p>']
    toc = []
    for topic, summary, body_md in collect.knowledge_docs():
        anchor = f"kb-{md.slug(topic)}"
        toc.append((2, topic, anchor))
        record(topic, "knowledge.html", anchor, "knowledge", summary)
        body, headings = md.render(body_md, link_commands=True)
        for lvl, text, _a in headings:
            if lvl <= 3:
                record(text, "knowledge.html", anchor, "knowledge", topic)
        parts.append(f'<h2 id="{anchor}">{topic}<a class="anchor" href="#{anchor}">#</a></h2>')
        if summary:
            parts.append(f'<p class="summary">{md.inline(summary)}</p>')
        parts.append(f'<div class="kb">{body}</div>')
    return shell("knowledge.html", "Instrument knowledge", "\n".join(parts), toc=toc)


def changelog_page() -> str:
    source = open(os.path.join(os.path.dirname(HERE), "docs", "CHANGELOG.md")).read()
    body, headings = md.render(source, link_commands=True)
    return shell("changelog.html", "Change log", body,
                 toc=[h for h in headings if h[0] <= 2][:40],
                 lede="Every revision, newest first.")


def main() -> None:
    # Auto-linking only fires for commands that really have an entry, so a
    # mention of a sub-form (`/mask create`) points at its parent's section and
    # nothing renders as a dead link.
    commands = collect.commands()
    for c in commands:
        anchor = f"cmd-{md.slug(c.name)}"
        md.COMMAND_ANCHORS[c.name] = anchor
        for phrase, _text in c.variants:
            md.COMMAND_ANCHORS.setdefault(phrase, anchor)

    written = []
    written.append(("index.html", page_from_markdown(
        "index.md", "index.html", "Introduction",
        "An interactive tool for reducing EQSANS data — catalog, match, reduce, "
        "stitch and plot, without hand-writing a reduction script.")))
    written.append(("guide.html", page_from_markdown(
        "guide.md", "guide.html", "Step-by-step guide",
        "One experiment from raw runs to a stitched I(Q), with what to check at "
        "each step.")))
    written.append(("commands.html", commands_page()))
    written.append(("parameters.html", parameters_page()))
    written.append(("protocol.html", protocol_page()))
    written.append(("knowledge.html", knowledge_page()))
    written.append(("changelog.html", changelog_page()))

    for name, html_text in written:
        with open(os.path.join(HERE, name), "w") as fh:
            fh.write(html_text)

    with open(os.path.join(HERE, "search-index.json"), "w") as fh:
        json.dump(INDEX, fh, separators=(",", ":"))
    open(os.path.join(HERE, ".nojekyll"), "w").close()

    kinds: dict[str, int] = {}
    for e in INDEX:
        kinds[e["k"]] = kinds.get(e["k"], 0) + 1
    print(f"{len(written)} pages, {len(INDEX)} search entries "
          f"({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})")


if __name__ == "__main__":
    main()
