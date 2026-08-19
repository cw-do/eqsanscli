"""Pull documentation content out of the code and the canonical documents.

Nothing here invents facts. Each collector names its single source:

  commands   — `commands/registry.py` for the list, `SKILL.md` tables for the
               one-line summary, the module's own `_USAGE` for full help
  parameters — `services/script_exporter.py` for the EQVar mapping,
               `preset_configs/*.json` for real values, `instrument_files` for
               which parameters the machine-physics resolver owns
  rules      — `services/protocol.py`, which parses `knowledge/protocol.md`
  knowledge  — the `knowledge/` documents themselves

If a fact has no source here, it belongs in one of those places first.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts)) as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

@dataclass
class Command:
    name: str                     # "set config"
    summary: str = ""             # one line, from SKILL.md
    section: str = "Other"        # grouping, from SKILL.md headings
    usage: str = ""               # the in-CLI /help text, when the module has one
    examples: list[str] = field(default_factory=list)
    handler: str = ""             # module that implements it
    variants: list = field(default_factory=list)   # (phrase, description) sub-forms


def registered_commands() -> dict[str, str]:
    """command name -> handler module, from the single registry."""
    source = _read("src", "eqsanscli", "commands", "registry.py")
    handlers = dict(re.findall(r"from eqsanscli\.commands\.(\w+) import ([^\n]+)", source))
    owner = {}
    for module, names in handlers.items():
        for n in re.findall(r"\w+", names):
            owner[n] = module
    out = {}
    for name, handler in re.findall(r'router\.register\("([^"]+)",\s*(\w+)\)', source):
        out[name] = owner.get(handler, "")
    return out


def _skill_tables() -> tuple[dict[str, str], dict[str, str]]:
    """(summary, section) per command phrase, from SKILL.md's reference tables.

    A cell can name several commands (`/ls [path]`, `/pwd`, ...), so every
    `/command` token in the first cell takes the row's description.
    """
    summary, section = {}, {}
    current = "Other"
    for line in _read("SKILL.md").splitlines():
        head = re.match(r"^#{2,3}\s+(.*)$", line)
        if head:
            current = re.sub(r"[*`]", "", head.group(1)).strip()
            continue
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        text = cells[-1]
        if text.lower() in ("purpose", "returns"):
            continue
        for token in re.findall(r"/[a-z]+(?:\s+[a-z]+)?", cells[0]):
            phrase = token.strip().lstrip("/").strip()
            # "/set outputdir" is a form of /set, not a command of its own; the
            # registry is the authority on which phrases are real commands.
            summary.setdefault(phrase, text)
            section.setdefault(phrase, current)
    return summary, section


#: Commands SKILL.md covers in prose rather than in a table.
_PROSE_SUMMARY = {
    "cd": "Change the working directory (filesystem passthrough).",
    "cp": "Copy a file (filesystem passthrough).",
    "mv": "Move a file (filesystem passthrough).",
    "rm": "Remove a file (filesystem passthrough).",
    "mkdir": "Create a directory (filesystem passthrough).",
    "sh": "Run a shell command.",
    "refresh": "Re-fetch the current IPTS catalog, keeping /reclass overrides.",
}


#: Rich console markup used in the help text. Listed explicitly: a general
#: `[...]` strip would eat `[options]` out of the usage line.
_RICH_TAGS = re.compile(
    r"\[/?(?:bold|dim|italic|underline|green|yellow|red|cyan|blue|magenta|white)"
    r"(?: \w+)*\]")


def _usage_text(module: str) -> str:
    """The module's own `/help` text, with Rich markup removed.

    Read through the AST and `literal_eval`, not by unescaping by hand: the help
    strings contain real UTF-8 (em dashes, Ångström) and an escaped `\\[options]`,
    both of which a manual unescape corrupts.
    """
    import ast

    path = os.path.join(ROOT, "src", "eqsanscli", "commands", f"{module}.py")
    if not os.path.exists(path):
        return ""
    for node in ast.parse(open(path).read()).body:
        if (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_USAGE"):
            try:
                text = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return ""
            if not isinstance(text, str):
                return ""
            return _RICH_TAGS.sub("", text).replace("\\[", "[").strip()
    return ""


#: Worked examples. Kept here rather than in the tool because they are teaching
#: material, not reference — the flags themselves are documented by `_USAGE`.
EXAMPLES: dict[str, list[str]] = {
    "load ipts": ["/load ipts 38681", "/show catalog"],
    "matchruns": ["/matchruns"],
    "reclass": ["/reclass 186517 empty", "/reclass --sample BkgG sample"],
    "set": ["/set 3 trans 186520", "/set --sample porsil thickness 0.1",
            "/set --config 4m10a emp 186517"],
    "assign": ["/assign bkg emptyticell"],
    "show table": ["/show table", "/show table --sample porsil"],
    "set config": ["/set config 4m10a qmin 0.005",
                   "/set config 4m10a maskfilename /path/to/mask.nxs"],
    "config": ["/config list", "/config clone 4m10a 4m10a_thin"],
    "instrument": ["/instrument show", "/instrument apply", "/instrument check"],
    "mask": ["/mask create 186636 --dry-run", "/mask create 186636 --leak",
             "/mask list"],
    "reduce": ["/reduce all", "/reduce --sample porsil", "/reduce 1-5"],
    "calibrate": ["/calibrate porsil_4m10a_Iq.dat --applynow"],
    "stitch": ["/stitch smart", "/stitch build", "/stitch run"],
    "plot": ["/plot *_Iq.dat --save all.png --loglog"],
    "autopilot": ["/autopilot 38681",
                  "/autopilot 38681 --bkg emptyticell --exclude Y5 --thickness 0.15"],
    "export script": ["/export script", "/export script my_reduction.py"],
    "share": ["/share *_Iq.dat"],
}


#: Registered by each front end rather than by registry.py, but typed like any
#: other command — see ENTRY_POINT_COMMANDS in commands/registry.py.
ENTRY_POINTS = {
    "help": ("Command reference inside the tool; `/help <command>` for one command.", "app"),
    "guide": ("Built-in walkthrough of a typical reduction.", "app"),
    "version": ("Which build is running.", "app"),
    "list": ("Usage stub — see `/list iq`, `/list ipts`, `/list tables`.", "app"),
    "exit": ("Leave the tool (`/quit`, `/q`).", "app"),
}


def commands() -> list[Command]:
    summary, section = _skill_tables()
    registered = registered_commands()
    out = []
    for name, module in sorted(registered.items()):
        first = name.split()[0]
        # Sub-forms of this command that SKILL.md documents separately
        # (`/mask create`, `/config clone`) become the entry's variants.
        variants = sorted((phrase, text) for phrase, text in summary.items()
                          if phrase.split()[0] == first and phrase != name
                          and phrase not in registered)
        text = (summary.get(name)
                or (variants[0][1] if variants else "")
                or _PROSE_SUMMARY.get(name, ""))
        out.append(Command(
            name=name,
            summary=text,
            section=section.get(name) or (section.get(variants[0][0]) if variants else None)
                    or section.get(first) or "Other",
            usage=_usage_text(module),
            examples=EXAMPLES.get(name, []),
            handler=module,
            variants=variants,
        ))
    for name, (text, module) in ENTRY_POINTS.items():
        out.append(Command(name=name, summary=text, section="The tool itself",
                           handler=module))
    return sorted(out, key=lambda c: c.name)


# Configuration parameters
# --------------------------------------------------------------------------

@dataclass
class Parameter:
    name: str                     # eqsanscli name, e.g. "qmin"
    description: str = ""         # from knowledge/configurations.md
    eqvar: str = ""               # attribute in the exported script, e.g. "_qmin"
    json_key: str = ""            # drtsans template key, e.g. "configuration.Qmin"
    owner: str = "preset"         # preset | machine physics | user | drtsans default
    values: dict = field(default_factory=dict)   # config id -> value seen in presets


def eqvar_map() -> dict[str, str]:
    source = _read("src", "eqsanscli", "services", "script_exporter.py")
    block = re.search(r"eqvar_map = \{(.*?)\}", source, re.S).group(1)
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block))


def managed_params() -> tuple[str, ...]:
    from eqsanscli.services.instrument_files import MANAGED_PARAMS
    return tuple(MANAGED_PARAMS)


def preset_values() -> dict[str, dict[str, object]]:
    """parameter (lower-cased leaf) -> {config id: value} across the presets."""
    values: dict[str, dict[str, object]] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "preset_configs", "conf_*.json"))):
        label = os.path.basename(path)[len("conf_"):-len(".json")]
        data = json.load(open(path))

        def walk(node, prefix=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}" if prefix else k)
            else:
                leaf = prefix.split(".")[-1].lower()
                values.setdefault(leaf, {})[label] = node
                values.setdefault(prefix, {})[label] = node
        walk(data)
    return values


def parameter_descriptions() -> dict[str, str]:
    """One line per parameter, from knowledge/configurations.md — its home."""
    out: dict[str, str] = {}
    for line in _read("knowledge", "configurations.md").splitlines():
        row = re.match(r"^\|\s*(`[^|]+`)\s*\|\s*(.+?)\s*\|\s*$", line)
        if not row:
            continue
        text = row.group(2)
        if text.lower() in ("what it is", "typical"):
            continue
        for name in re.findall(r"`([^`]+)`", row.group(1)):
            out[name.strip()] = text
    return out


def parameters() -> list[Parameter]:
    mapping, managed, values = eqvar_map(), managed_params(), preset_values()
    described = parameter_descriptions()
    json_keys = {k.split(".")[-1].lower(): k for k in values if "." in k}
    out = []
    for name, attr in mapping.items():
        out.append(Parameter(
            name=name, description=described.get(name, ""),
            eqvar=attr, json_key=json_keys.get(name, ""),
            owner="machine physics" if name in managed else "preset",
            values={c: v for c, v in (values.get(name) or {}).items() if v not in (None, "")},
        ))
    for name in managed:                       # e.g. scalecomponents.detector1
        if name not in mapping:
            out.append(Parameter(name=name, description=described.get(name, ""),
                                 owner="machine physics",
                                 json_key=json_keys.get(name.split(".")[0], ""),
                                 values=values.get(name.split(".")[-1].lower(), {})))
    return sorted(out, key=lambda p: p.name)


# --------------------------------------------------------------------------
# Protocol rules and knowledge documents
# --------------------------------------------------------------------------

def rules() -> list:
    from eqsanscli.services.protocol import load_rules
    return sorted(load_rules().values(), key=lambda r: r.id)


def knowledge_docs() -> list[tuple[str, str, str]]:
    """(topic, summary, markdown) for each knowledge document except the index."""
    import md
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "knowledge", "*.md"))):
        name = os.path.basename(path)
        if name in ("README.md", "protocol.md"):
            continue
        meta, body = md.strip_front_matter(open(path).read())
        out.append((meta.get("topic", name[:-3]), meta.get("summary", ""), body))
    return out


def version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', _read("src", "eqsanscli", "__init__.py"))
    return m.group(1) if m else "?"
