from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from eqsanscli.config.settings import AppSettings

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

logger = logging.getLogger(__name__)

# Directories to search for knowledge.md (project root, then cwd)
_KNOWLEDGE_DIRS = [
    Path(__file__).resolve().parent.parent.parent.parent / "preset_configs",
    Path.cwd() / "preset_configs",
]


def _load_knowledge() -> str:
    """Load SANS domain knowledge from knowledge.md at runtime.

    Always reads fresh from disk so edits are picked up immediately.
    Returns empty string if file is not found.
    """
    for d in _KNOWLEDGE_DIRS:
        path = d / "knowledge.md"
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                return (
                    "SANS DOMAIN KNOWLEDGE (from knowledge.md — use this when suggesting "
                    "configuration parameters or answering questions about reduction settings):\n\n"
                    + text
                )
            except OSError as e:
                logger.warning("Could not read %s: %s", path, e)
    return ""


def _parse_config_id(config_id: str) -> dict[str, float | int]:
    """Extract distance, wavelength, frequency from a config ID string.

    Examples:
        '4m10a'      → {'distance': 4.0, 'wavelength': 10.0, 'frequency': 60}
        '2.5m2.5a'   → {'distance': 2.5, 'wavelength': 2.5, 'frequency': 60}
        '8m12a30hz'  → {'distance': 8.0, 'wavelength': 12.0, 'frequency': 30}
    """
    m = re.match(
        r"(\d+\.?\d*)m(\d+\.?\d*)a(?:(\d+)hz)?$",
        config_id.strip().lower(),
    )
    if not m:
        return {}
    return {
        "distance": float(m.group(1)),
        "wavelength": float(m.group(2)),
        "frequency": int(m.group(3)) if m.group(3) else 60,
    }

_SYSTEM_PROMPT = """You are an AI assistant for the EQSANS data reduction CLI at SNS/ORNL.

You have two modes:
1. COMMAND MODE: If the user wants to perform an action, return CLI command(s) starting with /
   Return one command per line, no explanation.
2. CHAT MODE: If the user is asking a question, greeting, or having a conversation,
   respond naturally as a helpful assistant. Do NOT return a / command.
   IMPORTANT: When the user asks about current settings or configuration values,
   first check the session state provided to you and give a direct, concise answer
   (e.g., "Yes, you are using incoherent inelastic correction for the 2.5m2.5a
   configuration."). Then provide any additional explanation or details afterward.
   Always lead with the direct answer — do not bury it in a long explanation.

You know about SANS (Small-Angle Neutron Scattering) data reduction, I(Q) profiles,
detector configurations, transmission measurements, background subtraction, and stitching.

Available commands:

CATALOG:
/load ipts <number>             - Fetch catalog from ONCat
/list ipts *                    - List all EQSANS experiments from ONCat
/list ipts <text>               - Search experiments by title or team member name
/show catalog                   - Display loaded catalog
/show ipts                      - Show current IPTS number
/save catalog <file>            - Save catalog CSV
/load catalog <file>            - Load catalog CSV

WORKING TABLE:
/show table                     - Show working table
/matchruns                      - Auto-match trans/bkg/empty runs
/assign bkg <sample>            - Reassign background sample
/set <run> <field> <value>      - Set run field (trans, bkg, bkgtrans, emp, thickness)
/set <run> <field> none         - Clear a field
/remove <rows>                  - Remove rows (1, 1-3, 1,4,7)
/remove all --keep <sample>     - Remove all rows EXCEPT named sample
/remove --sample <name>         - Remove all rows matching sample name
/save table <name>              - Save table
/load table <name>              - Load table
/list tables                    - List tables

CONFIGURATION:
/list configs                   - List configurations
/show config <id>               - Show config params (id like 4m10a, 2.5m2.5a)
/set config <id> <param> <val>  - Set config parameter
/show outputdir                 - Show output directory
/set outputdir <path>           - Set output directory
/set ipts <number>              - Set IPTS number
/show ipts                      - Show IPTS number

PRESETS:
/show presets                   - List preset configurations
/show preset <name>             - Show preset params
/apply preset <name> <config>   - Apply preset to config
/compare <a> <b>                - Compare two configs/presets

REDUCTION:
/reduce <idx|range|all>         - Run reduction (1, 1-4, 1,3,5, all)
/export script [filename]       - Export .py reduction script

DATA & PLOTTING:
/list iq [path]                 - List I(Q) files
/list iqxqy [path]              - List I(Qx,Qy) files
/plot <file|pattern> [flags]    - Plot data (flags: --logx --logy --linx --liny --kratky --guinier --porod --save <path> --title <text>)

STITCH:
/stitch build                   - Build stitch table
/stitch smart                   - Smart stitch with overlap quality analysis
/stitch show                    - Show stitch table
/stitch set <sample|all> overlap <q1 q2 ...> - Set overlap (use "all" for all samples)
/stitch set <sample|all> overlap auto [n=4] - Auto-compute centered overlap (3-5 pts)
/stitch set <sample|all> target <idx|config_id> - Set target (accepts index like 0,1,2 or config_id like 4m10a)
/stitch run [sample]            - Run stitching
/stitch removerow <idx|all>     - Remove a stitch group row entirely
/stitch removeconfig <idx|all> <config_id> - Remove one config from stitch group(s)
/stitch reorder <idx|all> <config1,config2,...> - Reorder configs in stitch group(s)
/stitch script [file]           - Export stitch script
/stitch save <name>             - Save stitch table
/stitch load <name>             - Load stitch table

STITCH EXAMPLES (important for natural language):
- "set all stitch target to 1" → /stitch set all target 1
- "set all stitch target to 4m10a" → /stitch set all target 4m10a
- "set stitch target for all samples to 4m10a" → /stitch set all target 4m10a
- "set target index to 0 for all" → /stitch set all target 0
- "change the reference target to 2.5m2.5a for all samples" → /stitch set all target 2.5m2.5a
- "set overlap for all to 0.01 0.02" → /stitch set all overlap 0.01 0.02
- "auto overlap for all" → /stitch set all overlap auto
- "set mysample target to 4m10a" → /stitch set mysample target 4m10a
- "remove 4m10a from the stitch table" → /stitch removeconfig all 4m10a
- "remove 4m2.5a config from stitch" → /stitch removeconfig all 4m2.5a
- "remove 4m10a from row 2" → /stitch removeconfig 2 4m10a
- "remove row 3 from stitch" → /stitch removerow 3
- "remove row 3 from stitch, then auto overlap, then run" →
  /stitch removerow 3
  /stitch set all overlap auto
  /stitch run
- "reorder configs to conf0,conf1" → /stitch reorder all conf0,conf1
- "swap the config order in row 2 to highq,lowq" → /stitch reorder 2 highq,lowq
- "reorder all stitch groups to 8m12a,4m10a,4m2.5a" → /stitch reorder all 8m12a,4m10a,4m2.5a
- "change config order for row 0" → /stitch reorder 0 <configs in desired order>

NOTE: When user says "all" or "the stitch table" in context of stitch, use literal "all" as the sample/idx parameter.
The target can be either an integer index (0, 1, 2) or a config_id string (4m10a, 2.5m2.5a).
When removing a config by name, ALWAYS use "all" as the index unless the user specifies a row number.

LLM:
/models                         - List available LLM models
/models <name>                  - Switch model (gpt-5-mini, gemini-3-flash, claude-opus-4.6, gpt-4o)

SHELL:
/ls [path]                      - List directory
/cd <path>                      - Change directory
/pwd                            - Print working directory
/mkdir <path>                   - Create directory
/cat <file>                     - Show file contents
/head <file> [n]                - Show first n lines
/tail <file> [n]                - Show last n lines
/cp <src> <dst>                 - Copy file/directory
/mv <src> <dst>                 - Move/rename
/rm <file>                      - Remove file/directory
/sh <command>                   - Run shell command

CALIBRATION:
/calibrate <porsil_file>        - Calculate absolute scale
/calibrate <file> --ref NG3|NG7 - Choose reference standard
/calibrate --list-refs          - List available references

AUTOPILOT:
/autopilot <ipts>               - Full automated reduction (load, match, configure, reduce, calibrate, stitch, plot)
/autopilot <ipts> --samples <name1,name2,...>  - Autopilot only for specific samples (case-insensitive, comma-separated)

AUTOPILOT EXAMPLES (important for natural language):
- "autopilot ipts 34648" → /autopilot 34648
- "run autopilot for ipts 34648 only for Bi1 samples" → /autopilot 34648 --samples Bi1
- "reduce only Bi1 and Bi2 in ipts 34648 using autopilot" → /autopilot 34648 --samples Bi1,Bi2
- "autopilot 35884 just sample S1" → /autopilot 35884 --samples S1
NOTE: When user mentions specific sample names with autopilot, ALWAYS use --samples flag.

SETTINGS:
/settings                       - Show current settings
/settings textwrap <width>      - Set text wrap width (40-200)
/settings figsize <w> <h>       - Set default plot size (e.g. 8 6)
/settings dpi <value>           - Set default plot DPI (50-600)
/settings plotscale <scale>     - Set default axis scale (loglog, linlin, loglin, linlog)
/settings errorbars <on|off>    - Toggle default error bars
/settings linestyle <style>     - Set default line style (line, marker, line+marker)

SESSION:
/save session <name>            - Save session
/load session <name>            - Load session
/help                           - Help
/quit                           - Exit

For multi-step requests, return one command per line.
Config IDs are compact: 4m10a, 4m2.5a, 2.5m2.5a, 8m12a30hz
"""


def _build_context(state: SessionState) -> str:
    parts = []
    if state.ipts:
        parts.append(f"Current IPTS: {state.ipts}")
    table = state.current_table
    if table.rows:
        parts.append(f"Table '{table.name}': {len(table.rows)} rows")
        parts.append(f"Configs: {', '.join(table.configurations)}")
        sample_names = sorted(set(r.sample_name for r in table.rows))
        parts.append(f"Samples: {', '.join(sample_names[:20])}")
        for cfg in table.configurations:
            meta = _parse_config_id(cfg)
            if meta:
                parts.append(
                    f"  {cfg}: distance={meta['distance']}m, "
                    f"wavelength={meta['wavelength']}A, "
                    f"frequency={meta['frequency']}Hz"
                )
    _KEY_PARAMS = [
        "usedefaultmask", "usemask", "usedarkfilename", "usethetadependenttransmission",
        "usesensitivityfilename", "fitframeskipping", "useslicer",
        "doazimuthalaverage1d", "doincoherentinelasticcorrection",
        "absolutescalemethod", "standardabsolutescale",
        "qmin", "qmax", "numqbins", "qstep",
        "annularbeginradius", "annularendradius",
        "tofstart", "tofend", "lowqcuttof", "highqcuttof",
        "beamfluxfilename", "sensitivityfilename", "darkfilename",
    ]
    for cfg_id, params in state.configurations.items():
        interesting = {k: v for k, v in params.items() if k.lower() in _KEY_PARAMS and v not in (None, "", "None")}
        if interesting:
            parts.append(f"  {cfg_id} params: {interesting}")
    if state.output_directory != "./output/":
        parts.append(f"Output dir: {state.output_directory}")
    stitch_groups = getattr(state, "stitch_groups", [])
    if stitch_groups:
        sample_names = [g.sample_name for g in stitch_groups[:5]]
        configs_example = stitch_groups[0].configs if stitch_groups else []
        parts.append(f"Stitch table: {len(stitch_groups)} groups (samples: {', '.join(sample_names)}{'...' if len(stitch_groups) > 5 else ''})")
        if configs_example:
            parts.append(f"Available configs in stitch: {', '.join(configs_example)}")
    if parts:
        return "Current session state:\n" + "\n".join(parts)
    return "Session is empty. No IPTS loaded, no working table, no configurations. User needs to /load ipts <number> first."


async def parse_natural_language(user_input: str, state: SessionState) -> list[str]:
    """Runs the LLM call in a thread so the Textual event loop stays responsive."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    settings = AppSettings.load()
    if not settings.llm.is_configured:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return []

    client = OpenAI(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
    )

    context = _build_context(state)
    knowledge = _load_knowledge()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    if knowledge:
        messages.append({"role": "system", "content": knowledge})
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": user_input})

    def _call_llm() -> list[str]:
        for model in [settings.llm.model, settings.llm.fallback_model]:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500,
                )
                if response.usage:
                    state.llm_tokens_used += response.usage.total_tokens
                state.llm_calls += 1
                text = response.choices[0].message.content.strip()
                commands = [line.strip() for line in text.split("\n") if line.strip()]
                if commands:
                    return commands
            except Exception as e:
                logger.warning("LLM call failed with %s: %s", model, e)
                continue
        return []

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(ThreadPoolExecutor(max_workers=1), _call_llm)
