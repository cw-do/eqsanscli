"""Preset command handlers — /show presets, /show preset, /apply preset, /compare."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import base_config_id, normalize_config_id
from eqsanscli.services.config_manager import get_config, list_config_params
from eqsanscli.services.preset_service import (
    compare_configs,
    find_closest_preset,
    get_preset_name_from_path,
    list_presets,
    load_preset,
    load_preset_raw,
    preset_dir_path,
    resolve_preset_source,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _mark_config_rows_modified(state: SessionState, config_id: str) -> int:
    """Mark 'done' rows as 'modified' when their config parameters change."""
    norm = normalize_config_id(config_id)
    n = 0
    for row in state.current_table.rows:
        if row.status == "done" and normalize_config_id(row.configuration) == norm:
            row.status = "modified"
            n += 1
    return n


async def handle_show_presets(args: list[str], state: SessionState) -> CommandResult:
    """Handle /show presets — list available preset configurations."""
    presets = list_presets()
    if not presets:
        return CommandResult(
            success=True,
            message="No presets found. Place JSON files in preset_configs/ folder.",
        )

    rows = []
    for p in presets:
        rows.append({
            "Name": p["name"],
            "Description": p["description"],
        })

    return CommandResult(
        success=True,
        message=f"Available presets ({len(presets)}):",
        data={"type": "preset_list", "rows": rows},
    )


async def handle_show_preset(args: list[str], state: SessionState) -> CommandResult:
    """Handle /show preset <name> — display preset parameters."""
    if not args:
        return await handle_show_presets([], state)

    name = "_".join(args)  # Handle spaces: "4m 10a 60hz" -> "4m_10a_60hz"
    resolved = get_preset_name_from_path(name)
    if resolved is None:
        return CommandResult(success=False, message=f"Preset not found: {name}")

    # Non-config presets (e.g. stitch_overlaps.json) carry an "overlaps" list, not
    # a "configuration" section — render them their own way instead of an empty table.
    raw = load_preset_raw(resolved)
    if raw and isinstance(raw.get("overlaps"), list):
        return _show_overlaps_preset(resolved, raw)

    params = load_preset(resolved)
    if params is None:
        return CommandResult(success=False, message=f"Failed to load preset: {resolved}")

    rows = []
    for param in sorted(params.keys()):
        val = params[param]
        rows.append({
            "Parameter": param,
            "Value": str(val) if val is not None else "—",
            "Src": "",
        })

    return CommandResult(
        success=True,
        message=f"Preset: {resolved}",
        data={"type": "config_table", "rows": rows, "config_id": f"preset:{resolved}"},
    )


def _show_overlaps_preset(resolved: str, raw: dict) -> CommandResult:
    """Render the stitch-overlaps preset: the config pairs and how to edit them."""
    entries = raw.get("overlaps", [])
    pairs = []
    for entry in entries:
        cfgs = entry.get("configs", [])
        ov = entry.get("overlap", [])
        pairs.append((
            " → ".join(str(c) for c in cfgs) if cfgs else "?",
            f"[{ov[0]}, {ov[1]}]" if len(ov) == 2 else str(ov),
            str(entry.get("note", "")),
        ))
    hdr_pair, hdr_ov = "Config pair (low-Q → high-Q)", "Overlap Q [min,max]"
    wpair = max([len(p[0]) for p in pairs] + [len(hdr_pair)])
    wov = max([len(p[1]) for p in pairs] + [len(hdr_ov)])

    lines = [
        f"[bold]Stitch overlaps[/bold] ({resolved}) — predefined overlap Q-ranges used",
        "by smart stitch (/stitch smart, autopilot). A listed pair OVERRIDES the",
        "auto-computed overlap; any pair not listed falls back to auto.",
        "",
        f"  {hdr_pair:<{wpair}}  {hdr_ov:<{wov}}  Note",
        f"  {'-' * wpair}  {'-' * wov}  {'-' * 4}",
    ]
    for pair, window, note in pairs:
        lines.append(f"  {pair:<{wpair}}  {window:<{wov}}  {note}")

    pdir = preset_dir_path()
    loc = f"{pdir}/{resolved}.json" if pdir else f"{resolved}.json"
    lines += [
        "",
        f"[dim]To change: edit {loc}[/dim]",
        '[dim]  each entry: {"configs": ["<lowQ>", "<highQ>"], "overlap": [qmin, qmax], "note": "..."}[/dim]',
        "[dim]  configs are normalized ids (4m10a, 2.5m2.5a) low-Q → high-Q, or frame0/frame1 for 30Hz.[/dim]",
        "[dim]  Saved changes are picked up on the next /stitch smart run.[/dim]",
    ]
    return CommandResult(success=True, message="\n".join(lines))


async def handle_apply_preset(args: list[str], state: SessionState) -> CommandResult:
    """Handle /apply preset <preset_or_file> <config_id> — copy params to a config.

    <preset_or_file> is either a preset name from preset_configs/ OR a path to your
    own eqsans reduction .json (an existing .json file wins over a same-named
    preset). All configuration parameters in it are copied to <config_id>.

    Special case: /apply preset auto — auto-match presets to all configs in the table.

    By default, values DO NOT overwrite parameters the user has already set on the
    config (acts as a fill-in for defaults). Pass --force to overwrite too.

    Examples:
        /apply preset conf_4m_10a_60hz 4m10a
        /apply preset ./my_reduction.json 2.5m2.5a   ← copy all params from a file
        /apply preset auto
        /apply preset auto --force
    """
    force = False
    if "--force" in args:
        force = True
        args = [a for a in args if a != "--force"]

    if not args:
        return CommandResult(
            success=False,
            message="Usage: /apply preset <preset_name> <config_id> [--force]\n"
            "       /apply preset auto [--force]    — auto-match presets to all configs\n"
            "  --force overwrites parameters the user has already set\n"
            "  Example: /apply preset conf_4m_10a_60hz 4m10a",
        )

    # --- /apply preset auto ---
    if args[0].lower() == "auto":
        table = state.current_table
        configs = table.configurations
        if not configs:
            return CommandResult(
                success=False,
                message="No configurations in the working table. Use /matchruns first.",
            )

        presets = list_presets()
        if not presets:
            return CommandResult(
                success=False,
                message="No presets found. Place JSON files in preset_configs/ folder.",
            )

        preset_names = [p["name"] for p in presets]
        lines: list[str] = []
        applied = 0

        total_preserved = 0
        for cfg in configs:
            # Resolve clone names ("4m10a_v2") to their physics ID so they match
            # the same preset as the config they were cloned from.
            best, match_type = find_closest_preset(
                base_config_id(cfg) or cfg, preset_names
            )
            if best:
                resolved = get_preset_name_from_path(best)
                if resolved:
                    params = load_preset(resolved)
                    if params:
                        if cfg not in state.configurations:
                            state.configurations[cfg] = {}
                        existing = state.configurations[cfg]
                        n_new = 0
                        n_preserved = 0
                        for key, value in params.items():
                            if value is None:
                                # JSON nulls aren't a meaningful preset value —
                                # skip so they don't shadow defaults or user values.
                                continue
                            if not force and key in existing:
                                n_preserved += 1
                                continue
                            existing[key] = value
                            n_new += 1
                        total_preserved += n_preserved
                        applied += 1
                        n_reset = _mark_config_rows_modified(state, cfg)
                        reset_note = f" ({n_reset} rows modified)" if n_reset else ""
                        preserved_note = (
                            f" [dim]({n_preserved} user-set params kept)[/dim]"
                            if n_preserved else ""
                        )
                        if match_type == "exact":
                            lines.append(f"  [green]✓[/green] {cfg} ← {resolved}{preserved_note}{reset_note}")
                        elif match_type == "partial":
                            lines.append(f"  [green]✓[/green] {cfg} ← {resolved} [dim](partial match)[/dim]{preserved_note}{reset_note}")
                        elif match_type == "distance":
                            lines.append(f"  [yellow]~[/yellow] {cfg} ← {resolved} [dim](same distance, closest available)[/dim]{preserved_note}{reset_note}")
                        continue
            lines.append(f"  [yellow]⚠[/yellow] {cfg} — no matching preset found")

        header = f"Auto-applied presets to {applied}/{len(configs)} config(s):"
        if total_preserved and not force:
            header += f"  [dim](kept {total_preserved} user-set param(s); use --force to overwrite)[/dim]"
        return CommandResult(
            success=True,
            message=header + "\n" + "\n".join(lines),
        )

    # --- /apply preset <name> <config_id> ---
    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /apply preset <preset_or_file.json> <config_id>\n"
            "       /apply preset auto    — auto-match presets to all configs\n"
            "  Example: /apply preset conf_4m_10a_60hz 4m10a\n"
            "           /apply preset ./my_reduction.json 2.5m2.5a",
        )

    preset_name = args[0]
    config_id = " ".join(args[1:])

    # Accept either a preset_configs/ name or a path to the user's own JSON file
    # (an existing .json wins over a same-named preset).
    params, resolved, is_file = resolve_preset_source(
        preset_name, base_dirs=[state.output_directory],
    )
    if params is None:
        if is_file or preset_name.lower().endswith(".json") or "/" in preset_name:
            return CommandResult(
                success=False,
                message=f"Could not read JSON config file: {preset_name}\n"
                "  Give a path to an eqsans reduction .json, or a preset name from "
                "preset_configs/.",
            )
        return CommandResult(success=False, message=f"Preset not found: {preset_name}")
    source_desc = f"file '{resolved}'" if is_file else f"preset '{resolved}'"

    # Apply preset params, preserving user-set values unless --force was given
    if config_id not in state.configurations:
        state.configurations[config_id] = {}
    existing = state.configurations[config_id]

    count = 0
    preserved = 0
    for key, value in params.items():
        if value is None:
            # JSON nulls aren't a meaningful preset value — skip so they
            # don't shadow defaults or user values.
            continue
        if not force and key in existing:
            preserved += 1
            continue
        existing[key] = value
        count += 1

    n_reset = _mark_config_rows_modified(state, config_id)
    msg = f"Applied {source_desc} to config '{config_id}' ({count} parameters)."
    if preserved and not force:
        msg += (
            f"\n  Kept {preserved} user-set parameter(s) — pass --force to overwrite."
        )
    if n_reset:
        msg += f"\n  ⚠ {n_reset} row(s) marked as modified — will be re-reduced."

    return CommandResult(success=True, message=msg)


async def handle_compare(args: list[str], state: SessionState) -> CommandResult:
    """Handle /compare <a> <b> — side-by-side comparison of two configs/presets.

    Arguments can be preset names or active config IDs.
    Examples:
        /compare conf_4m_10a_60hz 4.0m 10.0A 60Hz
        /compare conf_8m_12a_60hz conf_8m_12a_60hz_inc
    """
    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /compare <config_or_preset_A> <config_or_preset_B>\n"
            "  Example: /compare conf_4m_10a_60hz 4.0m 10.0A 60Hz",
        )

    # Parse the two config names — tricky because config IDs have spaces
    # Strategy: first arg is always a single token (preset or config),
    # remaining args form the second name
    name_a = args[0]
    name_b = " ".join(args[1:])

    # Resolve each to a param dict
    params_a = _resolve_params(name_a, state)
    params_b = _resolve_params(name_b, state)

    if params_a is None:
        return CommandResult(success=False, message=f"Not found: {name_a}")
    if params_b is None:
        return CommandResult(success=False, message=f"Not found: {name_b}")

    rows = compare_configs(params_a, params_b, name_a, name_b)

    # Count differences
    n_diff = sum(1 for r in rows if r["diff"] == "diff")
    n_same = sum(1 for r in rows if r["diff"] == "same")
    n_only_a = sum(1 for r in rows if r["diff"] == "only_a")
    n_only_b = sum(1 for r in rows if r["diff"] == "only_b")

    summary = (
        f"Comparing: {name_a} vs {name_b}\n"
        f"  [bold red]{n_diff} different[/bold red] | "
        f"[green]{n_same} same[/green] | "
        f"{n_only_a} only in A | {n_only_b} only in B"
    )

    return CommandResult(
        success=True,
        message=summary,
        data={
            "type": "compare_table",
            "rows": rows,
            "name_a": name_a,
            "name_b": name_b,
        },
    )


def _resolve_params(name: str, state: SessionState) -> dict[str, object] | None:
    """Resolve a name to a parameter dict — check presets first, then active configs."""
    # Try as preset
    resolved = get_preset_name_from_path(name)
    if resolved:
        params = load_preset(resolved)
        if params:
            return params

    from eqsanscli.models.config_id import find_matching_config
    table = state.current_table
    match = find_matching_config(name, table.configurations)
    if match:
        return get_config(match, state.configurations)

    return None
