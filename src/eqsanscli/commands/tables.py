from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from eqsanscli.commands.catalog import build_working_table_display
from eqsanscli.commands.router import CommandResult
from eqsanscli.models.working_table import WorkingTable

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_table(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=True,
            message=f"Active table: [bold]{state.active_table}[/bold] "
            f"({len(state.current_table.rows)} rows)\n\n"
            "  /table list                — List all tables\n"
            "  /table new porsil          — Create new table\n"
            "  /table porsil              — Switch to table\n"
            "  /table clone src dst       — Clone a table\n"
            "  /table rename old new      — Rename\n"
            "  /table delete name         — Delete",
        )

    sub = args[0].lower()

    if sub == "list":
        return _table_list(state)
    if sub == "new":
        return _table_new(args[1:], state)
    if sub == "clone":
        return _table_clone(args[1:], state)
    if sub == "delete" or sub == "rm":
        return _table_delete(args[1:], state)
    if sub == "rename":
        return _table_rename(args[1:], state)

    # /table <name> — switch to existing table
    return _table_switch(sub, state)


async def handle_move(args: list[str], state: SessionState) -> CommandResult:
    """Move rows from active table to another: /move 1,3,5 porsil"""
    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /move <rows> <target_table>\n"
            "  Examples: /move 1,3,5 porsil  |  /move 1-4 samples",
        )

    row_spec = args[0]
    target_name = args[1]

    source = state.current_table
    if target_name not in state.tables:
        state.tables[target_name] = WorkingTable(name=target_name, ipts=state.ipts)
    target = state.tables[target_name]

    indices = _parse_indices(row_spec, source)
    if not indices:
        return CommandResult(success=False, message=f"No valid rows for: {row_spec}")

    moved = []
    for idx in sorted(indices, reverse=True):
        row = source.remove_row(idx)
        if row:
            moved.append(row)

    for row in reversed(moved):
        target.add_row(row)

    return CommandResult(
        success=True,
        message=f"Moved {len(moved)} rows from '{source.name}' to '{target_name}'.\n"
        f"  {source.name}: {len(source.rows)} rows remaining\n"
        f"  {target_name}: {len(target.rows)} rows",
    )


def _table_list(state: SessionState) -> CommandResult:
    lines = [f"Tables ({len(state.tables)}):"]
    for name, tbl in sorted(state.tables.items()):
        marker = " [bold cyan]●[/bold cyan]" if name == state.active_table else "  "
        configs = ", ".join(tbl.configurations) if tbl.rows else "empty"
        lines.append(f" {marker} {name:<20} {len(tbl.rows):>3} rows  [{configs}]")
    return CommandResult(success=True, message="\n".join(lines))


def _table_new(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /table new <name>")
    name = args[0]
    if name in state.tables:
        return CommandResult(success=False, message=f"Table '{name}' already exists.")
    state.tables[name] = WorkingTable(name=name, ipts=state.ipts)
    state.active_table = name
    return CommandResult(success=True, message=f"Created and switched to table '{name}'.")


def _table_switch(name: str, state: SessionState) -> CommandResult:
    if name not in state.tables:
        available = ", ".join(state.tables.keys())
        return CommandResult(success=False, message=f"Table '{name}' not found. Available: {available}")
    state.active_table = name
    tbl = state.tables[name]
    return CommandResult(
        success=True,
        message=f"Switched to table '{name}' ({len(tbl.rows)} rows).",
    )


def _table_clone(args: list[str], state: SessionState) -> CommandResult:
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /table clone <source> <destination>")
    src_name, dst_name = args[0], args[1]
    if src_name not in state.tables:
        return CommandResult(success=False, message=f"Source table '{src_name}' not found.")
    if dst_name in state.tables:
        return CommandResult(success=False, message=f"Table '{dst_name}' already exists.")

    src = state.tables[src_name]
    dst = WorkingTable.from_dict(src.to_dict())
    dst.name = dst_name
    state.tables[dst_name] = dst
    state.active_table = dst_name
    return CommandResult(
        success=True,
        message=f"Cloned '{src_name}' → '{dst_name}' ({len(dst.rows)} rows). Switched to '{dst_name}'.",
    )


def _table_delete(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /table delete <name>")
    name = args[0]
    if name not in state.tables:
        return CommandResult(success=False, message=f"Table '{name}' not found.")
    if len(state.tables) == 1:
        return CommandResult(success=False, message="Cannot delete the last table.")
    del state.tables[name]
    if state.active_table == name:
        state.active_table = next(iter(state.tables))
    return CommandResult(success=True, message=f"Deleted table '{name}'. Active: '{state.active_table}'.")


def _table_rename(args: list[str], state: SessionState) -> CommandResult:
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /table rename <old> <new>")
    old_name, new_name = args[0], args[1]
    if old_name not in state.tables:
        return CommandResult(success=False, message=f"Table '{old_name}' not found.")
    if new_name in state.tables:
        return CommandResult(success=False, message=f"Table '{new_name}' already exists.")
    tbl = state.tables.pop(old_name)
    tbl.name = new_name
    state.tables[new_name] = tbl
    if state.active_table == old_name:
        state.active_table = new_name
    return CommandResult(success=True, message=f"Renamed '{old_name}' → '{new_name}'.")


def _parse_indices(spec: str, table: WorkingTable) -> list[int]:
    valid = {r.index for r in table.rows}
    indices = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                indices.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                indices.append(int(part))
            except ValueError:
                continue
    return [i for i in indices if i in valid]
