from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import find_matching_config, normalize_config_id
from eqsanscli.services.config_manager import get_config, list_config_params, set_config_param

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


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
            "  Example: /set config 4.0m_2.5a_60hz qbintype linear",
        )

    config_id = normalize_config_id(args[0])
    param = args[1]
    value = " ".join(args[2:])

    ok, message = set_config_param(config_id, param, value, state.configurations)
    return CommandResult(success=ok, message=message)


async def handle_list_configs(args: list[str], state: SessionState) -> CommandResult:
    table = state.current_table
    if not table.rows:
        return CommandResult(success=True, message="No configurations — working table is empty.")

    configs = table.configurations
    lines = [f"Configurations in table '{table.name}' ({len(configs)}):"]
    for cfg in configs:
        n_rows = len(table.rows_by_config(cfg))
        norm = normalize_config_id(cfg)
        has_overrides = any(normalize_config_id(k) == norm for k in state.configurations)
        override_mark = " [cyan]*[/cyan]" if has_overrides else ""
        lines.append(f"  {cfg:<24} {n_rows} rows{override_mark}")

    lines.append("\n[dim]Use /show config <config_id> to see parameters.[/dim]")

    return CommandResult(success=True, message="\n".join(lines))
