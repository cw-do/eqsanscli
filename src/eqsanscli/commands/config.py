from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import (
    base_config_id, find_matching_config, is_derived_config_id, normalize_config_id,
)
from eqsanscli.services.config_manager import (
    ALL_CONFIGS_KEY, get_config, list_config_params, set_config_param,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _resolve_config_key(raw: str, state: SessionState) -> str:
    """Resolve a user-typed config id to an EXISTING config key.

    Cloned configs keep their raw name (e.g. `4m2.5a30hz_TR`), but
    `normalize_config_id` strips underscores and lowercases, giving
    `4m2.5a30hztr` — a different key. Writing/reading the normalized form then
    misses the clone entirely (the override lands on a phantom key and the row's
    reduction never sees it). Match the user's input to a stored/table config key
    (exact first, then normalized-equal, preserving the stored casing); fall back
    to the normalized form only when nothing matches (a genuinely new config).
    """
    keys = list(state.configurations.keys()) + list(state.current_table.configurations)
    if raw in keys:
        return raw
    norm = normalize_config_id(raw)
    for k in keys:
        if k != ALL_CONFIGS_KEY and normalize_config_id(k) == norm:
            return k
    return norm


# Params whose values are file paths — resolve bare filenames to absolute paths
_FILE_PATH_PARAMS = {
    "maskfilename",
    "defaultmask",
    "sensitivityfilename",
    "darkfilename",
    "fluxmonitorratiofile",
    "beamfluxfilename",
}


def _resolve_file_path(value: str, ipts: int | str | None) -> tuple[str, str | None]:
    """Resolve a bare filename to an absolute path by searching common locations.

    Search order: cwd → /SNS/EQSANS/IPTS-{ipts}/shared/ → /SNS/EQSANS/shared/script/eqsanstools/

    Returns (resolved_value, note). `note` is a human-readable message if a resolution
    happened or failed; None otherwise. Sentinels ("none"/"null"/"") and already-absolute
    paths pass through unchanged.
    """
    v = value.strip()
    if not v or v.lower() in ("none", "null"):
        return value, None
    if os.path.isabs(v):
        return v, None
    # Treat any value containing a path separator as a user-supplied relative path
    if os.sep in v or "/" in v:
        abs_path = os.path.abspath(v)
        return abs_path, f"Resolved to {abs_path}"

    search_paths: list[str] = [os.path.abspath(v)]
    if ipts:
        search_paths.append(f"/SNS/EQSANS/IPTS-{ipts}/shared/{v}")
    search_paths.append(f"/SNS/EQSANS/shared/script/eqsanstools/{v}")

    for path in search_paths:
        if os.path.exists(path):
            return path, f"Resolved {v} → {path}"

    return value, (
        f"⚠ Could not locate '{v}' in cwd"
        + (f", /SNS/EQSANS/IPTS-{ipts}/shared/" if ipts else "")
        + ", or /SNS/EQSANS/shared/script/eqsanstools/. Stored as-is."
    )


async def handle_show_config(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return await handle_list_configs([], state)

    config_id = _resolve_config_key("_".join(args), state)
    params = list_config_params(config_id, state.configurations)

    # Values the instrument-file resolver put here get their own marker, with the
    # cycle they came from — otherwise a machine-physics path looks user-set.
    resolved = _resolved_marker(state, config_id)

    rows = []
    for param_name, value, source in params:
        source_marker = {"user": "[bold cyan]*[/bold cyan]", "preset": "", "default": "[dim]d[/dim]"}.get(source, "")
        if param_name in resolved:
            source_marker = f"[green]{resolved[param_name]}[/green]"
        rows.append({
            "Parameter": param_name,
            "Value": value,
            "Src": source_marker,
        })

    legend = "  [dim]Src: * = user override, d = default, (blank) = preset"
    if resolved:
        legend += ", mp:<cycle> = machine-physics calibration (/instrument show)"
    legend += "[/dim]"

    return CommandResult(
        success=True,
        message=f"Configuration: {config_id}\n{legend}",
        data={"type": "config_table", "rows": rows, "config_id": config_id},
    )


def _resolved_marker(state: SessionState, config_id: str) -> dict[str, str]:
    """Map param -> "mp:<cycle>" for values currently owned by the resolver."""
    provenance = getattr(state, "instrument_provenance", None) or {}
    record = None
    for key, value in provenance.items():
        if normalize_config_id(key) == normalize_config_id(config_id):
            record = value
            break
    if not record:
        return {}

    from eqsanscli.services.instrument_files import _same

    stored = {}
    for key, value in state.configurations.items():
        if normalize_config_id(key) == normalize_config_id(config_id):
            stored = value
            break

    cycle = _resolved_cycle(state, config_id)
    tag = f"mp:{cycle}" if cycle else "mp"
    return {
        param: tag for param, written in record.items()
        if param in stored and _same(stored[param], written)
    }


def _resolved_cycle(state: SessionState, config_id: str) -> str:
    """Which machine-physics cycle this config's calibration came from."""
    from eqsanscli.services.instrument_files import config_targets, resolve_for_run

    if state.instrument_cycle_pin:
        return state.instrument_cycle_pin
    for target in config_targets(state):
        if normalize_config_id(target.config_id) == normalize_config_id(config_id):
            return resolve_for_run(target.run, target.distance).cycle_id or ""
    return ""


async def handle_set_config(args: list[str], state: SessionState) -> CommandResult:
    """Config ID is now a single underscore-delimited token: /set config 4.0m_2.5a_60hz qbintype linear"""
    if len(args) < 3:
        return CommandResult(
            success=False,
            message="Usage: /set config <config_id> <param> <value>\n"
            "       /set config all <param> <value>   — apply to every config in the table,\n"
            "                                          and store as a sticky default for any\n"
            "                                          future configs that get created.\n"
            "  Example: /set config 4.0m_2.5a_60hz qbintype linear\n"
            "  Example: /set config all numqbins 33",
        )

    raw_id = args[0]
    param = args[1]
    value = " ".join(args[2:])

    # --- /set config all <param> <val> ---
    # The token "all" means "apply to every current config in the working table,
    # and stick as a default for future configs". This is the right choice when
    # the user (or LLM) doesn't know which config IDs exist yet — e.g. before
    # /load ipts or /matchruns.
    if raw_id.lower() == "all":
        from eqsanscli.services.config_manager import ALL_CONFIGS_KEY

        resolve_note: str | None = None
        if param.lower() in _FILE_PATH_PARAMS:
            value, resolve_note = _resolve_file_path(value, state.ipts)

        # 1) Apply to each existing config in the working table
        table_configs = state.current_table.configurations
        results: list[str] = []
        n_reset_total = 0
        for cfg in table_configs:
            ok, msg = set_config_param(cfg, param, value, state.configurations)
            if ok:
                results.append(f"  [green]✓[/green] {cfg}")
                # Mark done rows modified
                for row in state.current_table.rows:
                    if row.status == "done" and normalize_config_id(row.configuration) == cfg:
                        row.status = "modified"
                        n_reset_total += 1
            else:
                results.append(f"  [red]✗[/red] {cfg}: {msg}")

        # 2) Also store under the global "__all__" key so future configs inherit
        ok_all, _ = set_config_param(ALL_CONFIGS_KEY, param, value, state.configurations)

        if not table_configs:
            msg = (
                f"No configs in the working table yet — saved {param}={value} "
                f"as a global default.\n"
                "  It will be applied to every config created by future /matchruns\n"
                "  or /autopilot runs (won't overwrite per-config user settings)."
            )
        else:
            msg = f"Set {param}={value} on {len(table_configs)} config(s):\n" + "\n".join(results)
            msg += f"\n  Also saved as a sticky default for future configs."
            if n_reset_total:
                msg += f"\n  ⚠ {n_reset_total} row(s) marked as modified — will be re-reduced."

        if resolve_note:
            msg = f"{msg}\n  {resolve_note}"

        return CommandResult(success=True, message=msg)

    # --- /set config <id> <param> <val> ---
    config_id = _resolve_config_key(raw_id, state)

    resolve_note: str | None = None
    if param.lower() in _FILE_PATH_PARAMS:
        value, resolve_note = _resolve_file_path(value, state.ipts)

    ok, message = set_config_param(config_id, param, value, state.configurations)
    if resolve_note:
        message = f"{message}\n  {resolve_note}"

    # Mark "done" rows as "modified" when their config parameters change
    if ok:
        table = state.current_table
        n_reset = 0
        for row in table.rows:
            if row.status == "done" and normalize_config_id(row.configuration) == config_id:
                row.status = "modified"
                n_reset += 1
        if n_reset:
            message += f"\n  ⚠ {n_reset} row(s) marked as modified — will be re-reduced."

    return CommandResult(success=ok, message=message)


def _config_label(cfg: str) -> str:
    """Display label: the stored name, plus its normalized id in parentheses when
    they differ, so a clone like `4m2.5a30hz_TR` shows the `4m2.5a30hztr` id that
    everything resolves to. Names already equal to their normalized form (e.g.
    `4m10a`) are shown as-is."""
    norm = normalize_config_id(cfg)
    return f"{cfg} ({norm})" if norm != cfg else cfg


async def handle_list_configs(args: list[str], state: SessionState) -> CommandResult:
    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY

    table = state.current_table
    lines: list[str] = []

    # Configs actually in use by working-table rows (may include cloned/override IDs
    # whose row.configuration_override is set).
    in_use_configs: list[str] = table.configurations if table.rows else []
    in_use_norms = {normalize_config_id(c) for c in in_use_configs}

    if in_use_configs:
        lines.append(f"Configurations in table '{table.name}' ({len(in_use_configs)}):")
        for cfg in in_use_configs:
            n_rows = len(table.rows_by_config(cfg))
            norm = normalize_config_id(cfg)
            has_overrides = any(
                normalize_config_id(k) == norm for k in state.configurations
                if k != ALL_CONFIGS_KEY
            )
            override_mark = " [cyan]*[/cyan]" if has_overrides else ""
            clone_mark = (
                f" [dim](clone of {base_config_id(cfg)})[/dim]"
                if is_derived_config_id(cfg) and base_config_id(cfg) else ""
            )
            lines.append(f"  {_config_label(cfg):<30} {n_rows} rows{override_mark}{clone_mark}")
    else:
        lines.append("No configurations — working table is empty.")

    # Stored configs not currently used by any row (e.g. clones awaiting /set <row> cfg).
    stored_extras = sorted(
        k for k in state.configurations
        if k != ALL_CONFIGS_KEY and normalize_config_id(k) not in in_use_norms
    )
    if stored_extras:
        lines.append("")
        lines.append(f"[bold]Stored configs not assigned to any row ({len(stored_extras)}):[/bold]")
        for cfg in stored_extras:
            clone_mark = (
                f" [dim](clone of {base_config_id(cfg)})[/dim]"
                if is_derived_config_id(cfg) and base_config_id(cfg) else ""
            )
            lines.append(f"  {_config_label(cfg):<30} 0 rows [cyan]*[/cyan]{clone_mark}")
        lines.append("  [dim]Assign with: /set <row> cfg <name>[/dim]")

    # Leftover/duplicate configs: a stored key that isn't itself shown above but
    # normalizes to the same id as one that is — e.g. a phantom `4m2.5a30hztr` from
    # a punctuation/case variant of the clone `4m2.5a30hz_TR`. These are dedup'd out
    # of both lists above, so surface them explicitly with a delete hint.
    shown = set(in_use_configs) | set(stored_extras)
    leftovers = sorted(
        k for k in state.configurations
        if k != ALL_CONFIGS_KEY and k not in shown
    )
    if leftovers:
        lines.append("")
        lines.append(f"[bold]Leftover configs — same id as another, safe to delete ({len(leftovers)}):[/bold]")
        for k in leftovers:
            norm = normalize_config_id(k)
            canon = next((c for c in list(in_use_configs) + stored_extras
                          if normalize_config_id(c) == norm), norm)
            lines.append(f"  {k:<24} [yellow]⚠ duplicate of {canon}[/yellow] "
                         f"[dim](/config delete {k})[/dim]")

    # Show pending "all" defaults (from /set config all <p> <v> before any matchruns)
    all_defaults = state.configurations.get(ALL_CONFIGS_KEY, {})
    if all_defaults:
        lines.append("")
        lines.append("[bold]Pending '/set config all' defaults (applied to every future config):[/bold]")
        for k, v in sorted(all_defaults.items()):
            lines.append(f"  {k} = {v}")

    if in_use_configs or stored_extras:
        lines.append("\n[dim]Use /show config <config_id> to see parameters.[/dim]")

    return CommandResult(success=True, message="\n".join(lines))


_CONFIG_USAGE = (
    "Usage: /config <subcommand> [args]\n"
    "  /config list                       — list configs in the working table and stored extras\n"
    "  /config clone <src> <dst>          — copy params from <src> to a new config <dst>\n"
    "                                       <dst> must contain <src>'s config ID (4m10a → 4m10a_v2)\n"
    "                                       (use /set <row> cfg <dst> to assign rows)\n"
    "  /config rows <id>                  — show rows assigned to <id>\n"
    "  /config delete <id> [--force]      — delete a clone/leftover config; --force also\n"
    "                                       reverts any rows using it to their physical config\n"
)


def _dedup_config_names(state, table) -> list[str]:
    """All known config names (stored + in-table), dedup'd by normalized form."""
    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY
    seen: set[str] = set()
    out: list[str] = []
    for k in list(state.configurations) + list(table.configurations):
        if k == ALL_CONFIGS_KEY:
            continue
        n = normalize_config_id(k)
        if n in seen:
            continue
        seen.add(n)
        out.append(k)
    out.sort()
    return out


async def handle_config(args: list[str], state: SessionState) -> CommandResult:
    """Dispatch /config <subcommand>. Currently: list, clone, rows."""
    if not args:
        return await handle_list_configs([], state)
    sub = args[0].lower()
    rest = args[1:]
    if sub == "list":
        return await handle_list_configs(rest, state)
    if sub == "clone":
        return await handle_config_clone(rest, state)
    if sub == "rows":
        return await handle_config_rows(rest, state)
    if sub in ("delete", "remove", "rm", "del"):
        return await handle_config_delete(rest, state)
    return CommandResult(success=False, message=f"Unknown /config subcommand: {sub}\n\n{_CONFIG_USAGE}")


async def handle_config_delete(args: list[str], state: SessionState) -> CommandResult:
    """/config delete <id> [--force] — remove a stored config.

    A config that is the *physical* configuration of rows cannot be deleted — it
    is how those runs were measured. A clone (or an orphan/leftover) can: with no
    rows using it, it is removed; with rows assigned via /set <row> cfg, --force
    reverts them to their physical config (marking done rows modified) and deletes.
    """
    force = any(a.lower() == "--force" for a in args)
    positional = [a for a in args if a.lower() != "--force"]
    if not positional:
        return CommandResult(
            success=False,
            message="Usage: /config delete <config_id> [--force]\n"
            "  Deletes a clone or leftover config. See /config list for names.",
        )

    key = _resolve_config_key(positional[0], state)
    if key == ALL_CONFIGS_KEY:
        return CommandResult(success=False, message="Cannot delete the '__all__' defaults key.")

    norm = normalize_config_id(key)
    table = state.current_table

    # Rows whose PHYSICAL config this is (not an override) — cannot delete.
    physical = [r for r in table.rows
                if not r.configuration_override
                and normalize_config_id(r.physical_configuration) == norm]
    if physical:
        return CommandResult(
            success=False,
            message=f"'{key}' is the physical configuration of {len(physical)} row(s) — it is how "
            f"those runs were measured, so it can't be deleted. Only clones and leftover configs can.",
        )

    # Rows that reference THIS exact key as an override (a clone assignment).
    # Exact, not normalized: a phantom `4m2.5a30hztr` and the real clone
    # `4m2.5a30hz_TR` share a normalized id, but a row references one key string —
    # deleting the phantom must not count rows that use the clone.
    using = [r for r in table.rows if r.configuration_override == key]

    if key not in state.configurations and not using:
        return CommandResult(
            success=False,
            message=f"No stored config '{positional[0]}' to delete. See /config list.",
        )

    if using and not force:
        samples = ", ".join(sorted({r.sample_name for r in using}))
        return CommandResult(
            success=False,
            message=f"'{key}' is assigned to {len(using)} row(s): {samples}.\n"
            f"  Re-assign them first (/set <row> cfg none), or pass --force to delete and\n"
            f"  revert those rows to their physical config.",
        )

    # Perform the delete.
    reverted = 0
    for r in using:
        r.set_field("configuration_override", "")  # revert to physics; done → modified
        reverted += 1
    existed = state.configurations.pop(key, None) is not None

    msg = f"Deleted config '{key}'." if existed else f"Cleared references to '{key}'."
    if reverted:
        msg += f"\n  {reverted} row(s) reverted to their physical config" + \
               (" (done rows marked modified)." if any(r.status == "modified" for r in using) else ".")
    return CommandResult(success=True, message=msg)


async def handle_config_clone(args: list[str], state: SessionState) -> CommandResult:
    """/config clone <src> <dst> — copy stored params from one config to a new name.

    The clone gets its own entry in state.configurations and can be edited
    independently (e.g. different maskfilename). To use it, assign rows with
    /set <row> cfg <dst>. Existing rows continue to reference <src>.

    <src> may be any config the user can see in /config list (a config in the
    table, a stored-only clone, or a normalized variant — e.g. "4m10a" matches
    a stored "4.0m_2.5a_60hz" if normalized forms agree).

    NAMING RULE: <dst> must contain <src>'s physics ID (e.g. 4m10a → 4m10a_v2,
    4m10a-mask2, porsil_4m10a). Everything downstream that reasons about
    physics — preset matching, cycle-file discovery, low-Q-first stitch
    ordering — recovers the physics from the name via
    config_id.base_config_id(), so a name like "mask2" would silently lose it.
    """
    from eqsanscli.services.config_manager import (
        ALL_CONFIGS_KEY, _load_json_defaults, get_config,
    )

    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /config clone <src> <dst>\n"
            "  <dst> must contain <src>'s config ID, e.g. 4m10a_v2 / 4m10a-mask2\n"
            "  Example: /config clone 4m10a 4m10a_mask2\n"
            "  Then assign rows: /set <row> cfg 4m10a_mask2",
        )

    src_raw = args[0]
    dst_raw = args[1]
    dst_norm = normalize_config_id(dst_raw)

    if dst_norm == normalize_config_id(ALL_CONFIGS_KEY) or dst_raw.lower() == "all":
        return CommandResult(success=False, message=f"Cannot clone to reserved name '{dst_raw}'.")
    if not dst_norm:
        return CommandResult(success=False, message="Destination name cannot be empty.")

    # The clone name must keep the source's physics ID recoverable.
    src_base = base_config_id(src_raw)
    dst_base = base_config_id(dst_raw)
    if not src_base:
        return CommandResult(
            success=False,
            message=f"Cannot determine the physical configuration of '{src_raw}'. "
            f"Clone from a real config ID (e.g. 4m10a) or an existing clone of one.",
        )
    if dst_base != src_base:
        hint = f"'{src_base}_v2'" if not dst_base else f"'{src_base}_{dst_raw}'"
        return CommandResult(
            success=False,
            message=(
                f"Clone name '{dst_raw}' must contain the source's config ID '{src_base}' "
                f"(found: {dst_base or 'none'}).\n"
                f"  Try {hint} — e.g. /config clone {src_raw} {src_base}_v2\n"
                f"  Why: preset matching, cycle-file discovery and stitch ordering read the\n"
                f"  physics back out of the config name."
            ),
        )

    # Reject if dst already exists (any normalized match — clone is create-only).
    for existing_key in state.configurations:
        if existing_key == ALL_CONFIGS_KEY:
            continue
        if normalize_config_id(existing_key) == dst_norm:
            return CommandResult(
                success=False,
                message=f"Config '{dst_raw}' already exists (as '{existing_key}'). Pick a different name "
                f"or /set config {existing_key} <param> <value> to edit it.",
            )
    # Also reject if dst matches a physical config currently in the table
    # (would cause confusing aliasing — there's no point cloning to the same ID).
    table = state.current_table
    for row_cfg in table.configurations:
        if normalize_config_id(row_cfg) == dst_norm and row_cfg not in state.configurations:
            return CommandResult(
                success=False,
                message=f"'{dst_raw}' matches a physical config already in the working table "
                f"('{row_cfg}'). Clones must use a distinct name (e.g. add a suffix).",
            )

    # Resolve <src>: prefer an exact stored key, fall back to any stored key
    # whose normalized form matches, then to a row's physical config.
    src_norm = normalize_config_id(src_raw)
    src_key: str | None = None
    for k in state.configurations:
        if k == ALL_CONFIGS_KEY:
            continue
        if normalize_config_id(k) == src_norm:
            src_key = k
            break

    # If src isn't a stored override but matches a physical config in the table,
    # snapshot the effective params via get_config (defaults + any __all__).
    src_params: dict[str, object]
    if src_key is not None:
        src_params = dict(state.configurations[src_key])
        display_src = src_key
    else:
        in_table = any(normalize_config_id(c) == src_norm for c in table.configurations)
        if not in_table:
            available = _dedup_config_names(state, table)
            return CommandResult(
                success=False,
                message=f"Source config '{src_raw}' not found. Available: {', '.join(available) or '(none)'}",
            )
        # Snapshot the full effective config so the clone is self-contained
        # rather than implicitly tracking <src>'s preset. Keep every key whose
        # effective value DIFFERS from the drtsans-template default: that is the
        # minimal set which guarantees get_config(dst) == get_config(src) right
        # after the clone, whatever the value's provenance (preset, __all__, or
        # an earlier /set config). Keys equal to the default need no entry —
        # they resolve to the same default through the template layer.
        full = get_config(src_raw, state.configurations)
        template_defaults = _load_json_defaults()
        src_params = {
            k: v for k, v in full.items()
            if k not in template_defaults or template_defaults[k] != v
        }
        display_src = src_raw

    state.configurations[dst_raw] = dict(src_params)

    return CommandResult(
        success=True,
        message=(
            f"Cloned config '{display_src}' → '{dst_raw}' ({len(src_params)} param(s) copied).\n"
            f"  Physics: {src_base} [dim](used for presets/stitching; output files stay "
            f"named for {src_base})[/dim]\n"
            f"  Assign rows with: /set <row> cfg {dst_raw}\n"
            f"  Edit independently with: /set config {dst_raw} <param> <value>"
        ),
    )


async def handle_config_rows(args: list[str], state: SessionState) -> CommandResult:
    """/config rows <id> — show which working-table rows reference <id>."""
    if not args:
        return CommandResult(success=False, message="Usage: /config rows <config_id>")
    target = normalize_config_id(args[0])
    table = state.current_table
    matches = [r for r in table.rows if normalize_config_id(r.configuration) == target]
    if not matches:
        return CommandResult(success=True, message=f"No rows reference config '{args[0]}'.")
    lines = [f"Rows referencing '{args[0]}' ({len(matches)}):"]
    for r in matches:
        override = " [cyan](override)[/cyan]" if r.configuration_override else ""
        lines.append(f"  Row {r.index}: {r.sample_name} (run {r.scattering_run}){override}")
    return CommandResult(success=True, message="\n".join(lines))
