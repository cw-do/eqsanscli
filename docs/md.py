"""A small Markdown renderer — enough for the documentation in this repository.

No dependency is available on the analysis machines, and the input is our own
controlled Markdown: headings, fenced code, tables, lists, blockquotes, rules,
links, bold/italic and inline code. Anything fancier is not used, and would be
rendered literally rather than silently mangled.
"""

from __future__ import annotations

import html
import re

#: phrase -> anchor, filled in by the generator. Only these are auto-linked, so a
#: mention of an unknown command renders as code rather than a dead link.
COMMAND_ANCHORS: dict = {}

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RULE_ID = re.compile(r"\b([A-Z]{3}-\d{2})\b")
_COMMAND = re.compile(r"(?<![\w/])(/[a-z]+(?: [a-z]+)?)\b")


def slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", text) or "section"


def inline(text: str, *, link_rules: bool = True, link_commands: bool = False) -> str:
    """Inline markup. Code spans are protected before anything else runs."""
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        body = html.escape(m.group(1))
        if link_commands and body.startswith("/"):
            words = body.lstrip("/").strip().split()
            anchor = None
            if len(words) >= 2:
                anchor = COMMAND_ANCHORS.get(f"{words[0]} {words[1]}".lower())
            if anchor is None and words:
                anchor = COMMAND_ANCHORS.get(words[0].lower())
            if anchor:
                body = f'<a href="commands.html#{anchor}">{body}</a>' 
        spans.append(f"<code>{body}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    text = html.escape(text)
    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    if link_rules:
        text = _RULE_ID.sub(r'<a href="protocol.html#rule-\1" class="rule-ref">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def render(source: str, *, link_commands: bool = False) -> tuple[str, list[tuple[int, str, str]]]:
    """Markdown to HTML. Returns (html, headings) where headings are
    (level, text, anchor) so the caller can build a table of contents."""
    out: list[str] = []
    headings: list[tuple[int, str, str]] = []
    lines = source.splitlines()
    i = 0
    seen: dict[str, int] = {}

    def anchor_for(title: str) -> str:
        base = slug(title)
        seen[base] = seen.get(base, 0) + 1
        return base if seen[base] == 1 else f"{base}-{seen[base]}"

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):                      # fenced code
            lang = line[3:].strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i]); i += 1
            i += 1
            cls = f' class="lang-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre{cls}><code>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        if re.match(r"^\s*(---+|\*\*\*+)\s*$", line):
            out.append("<hr>"); i += 1; continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            a = anchor_for(title)
            headings.append((level, re.sub(r"[*`]", "", title), a))
            out.append(f'<h{level} id="{a}">{inline(title, link_commands=link_commands)}'
                       f'<a class="anchor" href="#{a}">#</a></h{level}>')
            i += 1
            continue

        if line.lstrip().startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<div class=\"table-wrap\"><table><thead><tr>" +
                       "".join(f"<th>{inline(c, link_commands=link_commands)}</th>" for c in head) +
                       "</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>" + "".join(
                    f"<td>{inline(c, link_commands=link_commands)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        if re.match(r"^\s*>\s?", line):
            body = []
            while i < len(lines) and re.match(r"^\s*>\s?", lines[i]):
                body.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            inner, _ = render("\n".join(body), link_commands=link_commands)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                item = [re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i])]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                        and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                    item.append(lines[i].strip()); i += 1
                items.append(" ".join(item))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(
                f"<li>{inline(t, link_commands=link_commands)}</li>" for t in items) + f"</{tag}>")
            continue

        if not line.strip():
            i += 1; continue

        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(\s*[-*+]\s|\s*\d+\.\s|#{1,6}\s|```|\s*\||\s*>)", lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{inline(' '.join(para), link_commands=link_commands)}</p>")

    return "\n".join(out), headings


def strip_front_matter(text: str) -> tuple[dict, str]:
    """Split a `---` YAML-ish header off a knowledge document."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[end + 4:].lstrip("\n")
