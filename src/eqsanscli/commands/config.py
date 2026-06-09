from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import find_matching_config, normalize_config_id
from eqsanscli.services.config_manager import get_config, list_config_params, set_config_param

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


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

    config_id = normalize_config_id("_".join(args))
    params = list_config_params(config_id, state.configurations)

    rows = []
    for param_name, value, source in params:
        source_marker = {"user": "[bold cyan]*[/bold cyan]", "preset": "", "default": "[dim]d[/dim]"}.get(source, "")
        rows.append({
            "Parameter": param_name,
            "Value": value,
            "Src": source_marker,
        })

    return CommandResult(
        success=True,
        message=f"Configuration: {config_id}\n"
        f"  [dim]Src: * = user override, d = default, (blank) = preset[/dim]",
        data={"type": "config_table", "rows": rows, "config_id": config_id},
    )


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
    config_id = normalize_config_id(raw_id)

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


async def handle_list_configs(args: list[str], state: SessionState) -> CommandResult:
    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY

    table = state.current_table
    lines: list[str] = []

    if table.rows:
        configs = table.configurations
        lines.append(f"Configurations in table '{table.name}' ({len(configs)}):")
        for cfg in configs:
            n_rows = len(table.rows_by_config(cfg))
            norm = normalize_config_id(cfg)
            has_overrides = any(
                normalize_config_id(k) == norm for k in state.configurations
                if k != ALL_CONFIGS_KEY
            )
            override_mark = " [cyan]*[/cyan]" if has_overrides else ""
            lines.append(f"  {cfg:<24} {n_rows} rows{override_mark}")
    else:
        lines.append("No configurations — working table is empty.")

    # Show pending "all" defaults (from /set config all <p> <v> before any matchruns)
    all_defaults = state.configurations.get(ALL_CONFIGS_KEY, {})
    if all_defaults:
        lines.append("")
        lines.append("[bold]Pending '/set config all' defaults (applied to every future config):[/bold]")
        for k, v in sorted(all_defaults.items()):
            lines.append(f"  {k} = {v}")

    if table.rows:
        lines.append("\n[dim]Use /show config <config_id> to see parameters.[/dim]")

    return CommandResult(success=True, message="\n".join(lines))
