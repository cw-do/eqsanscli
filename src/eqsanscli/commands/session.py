from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.working_table import WorkingTable

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _tables_dir() -> Path:
    d = Path.cwd() / ".eqsanscli" / "tables"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sessions_dir() -> Path:
    d = Path.cwd() / ".eqsanscli" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_saved_files(directory: Path, ext: str = ".json") -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob(f"*{ext}"))


async def handle_save(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /save <target>\n"
            "  /save session myexp        — Save full session\n"
            "  /save table mytable        — Save working table\n"
            "  /save catalog data.csv     — Export catalog to CSV",
        )
    sub = args[0].lower()
    if sub == "table":
        return await handle_save_table(args[1:], state)
    if sub == "session":
        return await handle_save_session(args[1:], state)
    if sub == "catalog":
        return await handle_save_catalog(args[1:], state)
    return CommandResult(success=False, message=f"Unknown /save target: {sub}")


async def handle_load(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /load <target>\n"
            "  /load ipts 35884           — Fetch catalog from ONCat\n"
            "  /load session              — List saved sessions\n"
            "  /load session myexp        — Load a session\n"
            "  /load table                — List saved tables\n"
            "  /load table mytable        — Load a table\n"
            "  /load catalog data.csv     — Load catalog from CSV",
        )
    sub = args[0].lower()
    if sub == "ipts":
        from eqsanscli.commands.catalog import handle_load_ipts
        return await handle_load_ipts(args[1:], state)
    if sub == "table":
        return await handle_load_table(args[1:], state)
    if sub == "session":
        return await handle_load_session(args[1:], state)
    if sub == "catalog":
        return await handle_load_catalog(args[1:], state)
    return CommandResult(success=False, message=f"Unknown /load target: {sub}")


async def handle_save_table(args: list[str], state: SessionState) -> CommandResult:
    name = args[0] if args else state.active_table
    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message=f"Table '{table.name}' is empty, nothing to save.")

    path = _tables_dir() / f"{name}.json"
    with open(path, "w") as f:
        json.dump(table.to_dict(), f, indent=2, default=str)

    return CommandResult(
        success=True,
        message=f"Table '{table.name}' saved to {path} ({len(table.rows)} rows).",
    )


async def handle_load_table(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        saved = _list_saved_files(_tables_dir())
        if not saved:
            return CommandResult(success=True, message=f"No saved tables in {_tables_dir()}")
        lines = [f"Saved tables in {_tables_dir()}:"]
        for p in saved:
            try:
                with open(p) as f:
                    data = json.load(f)
                n_rows = len(data.get("rows", []))
                name = data.get("name", p.stem)
                lines.append(f"  [cyan]{name}[/cyan]  ({n_rows} rows)")
            except Exception:
                lines.append(f"  [dim]{p.stem}[/dim]  (corrupt)")
        lines.append(f"\n[dim]Usage: /load table <name>[/dim]")
        return CommandResult(success=True, message="\n".join(lines))

    name = args[0]
    path = Path(name)
    if not path.exists():
        path = _tables_dir() / f"{name}.json"
    if not path.exists():
        return CommandResult(success=False, message=f"Table not found: {name}")

    with open(path) as f:
        data = json.load(f)

    table = WorkingTable.from_dict(data)
    state.tables[table.name] = table
    state.active_table = table.name

    from eqsanscli.commands.catalog import build_working_table_display
    rows = build_working_table_display(state)

    return CommandResult(
        success=True,
        message=f"Loaded table '{table.name}' ({len(table.rows)} rows) from {path}.",
        data={"type": "working_table", "rows": rows},
    )


async def handle_list_tables(args: list[str], state: SessionState) -> CommandResult:
    saved = _list_saved_files(_tables_dir())

    lines = [f"Saved tables in {_tables_dir()} ({len(saved)}):"]
    for p in saved:
        try:
            with open(p) as f:
                data = json.load(f)
            n_rows = len(data.get("rows", []))
            name = data.get("name", p.stem)
            lines.append(f"  {name:<20} {n_rows} rows  ({p.name})")
        except Exception:
            lines.append(f"  {p.stem:<20} (corrupt)")

    lines.append(f"\nActive tables in session:")
    for name, tbl in state.tables.items():
        marker = " [bold cyan]●[/bold cyan]" if name == state.active_table else "  "
        lines.append(f" {marker} {name:<20} {len(tbl.rows)} rows")

    return CommandResult(success=True, message="\n".join(lines))


async def handle_save_session(args: list[str], state: SessionState) -> CommandResult:
    if args:
        state.name = args[0]
    path = state.save()
    return CommandResult(success=True, message=f"Session '{state.name}' saved to {path}.")


async def handle_load_session(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        saved = _list_saved_files(_sessions_dir())
        if not saved:
            return CommandResult(success=True, message=f"No saved sessions in {_sessions_dir()}")
        lines = [f"Saved sessions in {_sessions_dir()}:"]
        for p in saved:
            if p.stem.startswith("_"):
                continue
            try:
                with open(p) as f:
                    data = json.load(f)
                ipts = data.get("ipts", "?")
                n_tables = len(data.get("tables", {}))
                lines.append(f"  [cyan]{p.stem}[/cyan]  (IPTS-{ipts}, {n_tables} tables)")
            except Exception:
                lines.append(f"  [dim]{p.stem}[/dim]  (corrupt)")
        lines.append(f"\n[dim]Usage: /load session <name>[/dim]")
        return CommandResult(success=True, message="\n".join(lines))

    from eqsanscli.models.session_state import SessionState as SS
    try:
        loaded = SS.load(args[0])
    except FileNotFoundError as e:
        return CommandResult(success=False, message=str(e))

    state.name = loaded.name
    state.ipts = loaded.ipts
    state.catalog_data = loaded.catalog_data
    state.tables = loaded.tables
    state.active_table = loaded.active_table
    state.configurations = loaded.configurations
    state.calibration = loaded.calibration
    state.output_directory = loaded.output_directory
    state.reduced_files = loaded.reduced_files
    state.command_history = loaded.command_history

    return CommandResult(
        success=True,
        message=f"Session '{loaded.name}' loaded (IPTS-{loaded.ipts}, "
        f"{len(loaded.tables)} tables, {sum(len(t.rows) for t in loaded.tables.values())} total rows).",
    )


async def handle_save_catalog(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /save catalog <filename.csv>")
    catalog = state.catalog
    if catalog is None or catalog.empty:
        return CommandResult(success=False, message="No catalog loaded.")
    path = args[0]
    catalog.to_csv(path, index=False)
    return CommandResult(success=True, message=f"Catalog saved to {path} ({len(catalog)} rows).")


async def handle_load_catalog(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /load catalog <filename.csv>")
    import pandas as pd
    path = args[0]
    if not os.path.exists(path):
        return CommandResult(success=False, message=f"File not found: {path}")
    df = pd.read_csv(path)
    state.catalog = df
    return CommandResult(success=True, message=f"Catalog loaded from {path} ({len(df)} rows).")
