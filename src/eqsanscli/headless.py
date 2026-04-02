"""Headless mode — JSON protocol over stdin/stdout for agent integration.

Usage:
    python -m eqsanscli headless

Protocol:
    - Send one command per line to stdin (e.g., /load ipts 35884)
    - Receive one JSON object per line on stdout
    - Progress lines for long-running ops are prefixed with "progress:" on stderr

Output format:
    {"success": bool, "message": str, "data": dict|null}
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from typing import Any

from eqsanscli.commands.autopilot import handle_autopilot
from eqsanscli.commands.calibrate import handle_calibrate
from eqsanscli.commands.catalog import handle_show, handle_show_table, handle_list_ipts
from eqsanscli.commands.config import handle_list_configs, handle_set_config, handle_show_config
from eqsanscli.commands.data import handle_list_iq, handle_list_iqxqy, handle_plot
from eqsanscli.commands.export import handle_export_script
from eqsanscli.commands.matching import handle_assign, handle_matchruns, handle_remove, handle_set
from eqsanscli.commands.models import handle_models
from eqsanscli.commands.preset import (
    handle_apply_preset, handle_compare, handle_show_preset, handle_show_presets,
)
from eqsanscli.commands.reduction import handle_reduce
from eqsanscli.commands.router import CommandResult, CommandRouter
from eqsanscli.commands.session import (
    handle_save, handle_load, handle_list_tables, handle_continue, handle_session,
)
from eqsanscli.commands.settings import handle_settings
from eqsanscli.commands.share import handle_share
from eqsanscli.commands.shell import (
    handle_ls, handle_cd, handle_pwd, handle_mkdir,
    handle_cat, handle_head, handle_tail,
    handle_cp, handle_mv, handle_rm, handle_shell,
)
from eqsanscli.commands.stitch import handle_stitch
from eqsanscli.commands.tables import handle_move, handle_table
from eqsanscli.models.session_state import SessionState


def _emit(obj: dict[str, Any]) -> None:
    """Write a JSON line to stdout and flush."""
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def _progress(msg: str) -> None:
    """Write a progress line to stderr."""
    sys.stderr.write(f"progress: {msg}\n")
    sys.stderr.flush()


def _strip_markup(text: str) -> str:
    """Remove Rich markup tags like [bold], [green], [/dim] etc."""
    import re
    return re.sub(r"\[/?[a-zA-Z_ #0-9.]+\]", "", text)


def _register_commands(router: CommandRouter, state: SessionState) -> None:
    """Register all command handlers — mirrors app.py."""
    router.register("show", handle_show)
    router.register("show table", handle_show_table)
    router.register("matchruns", handle_matchruns)
    router.register("set", handle_set)
    router.register("set config", handle_set_config)
    router.register("show config", handle_show_config)
    router.register("list configs", handle_list_configs)
    router.register("show presets", handle_show_presets)
    router.register("show preset", handle_show_preset)
    router.register("apply preset", handle_apply_preset)
    router.register("compare", handle_compare)
    router.register("assign", handle_assign)
    router.register("reduce", handle_reduce)
    router.register("remove", handle_remove)
    router.register("export script", handle_export_script)
    router.register("plot", handle_plot)
    router.register("list iq", handle_list_iq)
    router.register("list iqxqy", handle_list_iqxqy)
    router.register("calibrate", handle_calibrate)
    router.register("stitch", handle_stitch)
    router.register("table", handle_table)
    router.register("move", handle_move)
    router.register("save", handle_save)
    router.register("load", handle_load)
    router.register("list tables", handle_list_tables)
    router.register("continue", handle_continue)
    router.register("session", handle_session)
    router.register("list ipts", handle_list_ipts)
    router.register("models", handle_models)
    router.register("autopilot", handle_autopilot)
    router.register("settings", handle_settings)
    router.register("share", handle_share)
    router.register("ls", handle_ls)
    router.register("cd", handle_cd)
    router.register("pwd", handle_pwd)
    router.register("mkdir", handle_mkdir)
    router.register("cat", handle_cat)
    router.register("head", handle_head)
    router.register("tail", handle_tail)
    router.register("cp", handle_cp)
    router.register("mv", handle_mv)
    router.register("rm", handle_rm)
    router.register("sh", handle_shell)
    router.alias("quit", "exit")
    router.alias("q", "exit")
    router.alias("dir", "ls")
    router.alias("shell", "sh")

    async def _handle_version(args, state):
        from eqsanscli import __version__
        return CommandResult(success=True, message=f"eqsanscli v{__version__}")

    async def _handle_exit(args, state):
        return CommandResult(success=True, message="exit")

    async def _handle_help(args, state):
        return CommandResult(success=True, message="Use /help in TUI mode. In headless mode, send /commands directly.")

    async def _handle_list(args, state):
        if not args:
            return CommandResult(success=False, message="Usage: /list iq | /list iqxqy | /list configs | /list tables | /list ipts")
        return CommandResult(success=False, message=f"Unknown /list subcommand: {args[0]}")

    router.register("exit", _handle_exit)
    router.register("help", _handle_help)
    router.register("version", _handle_version)
    router.register("list", _handle_list)


def _run_reduction_sync(
    state: SessionState,
    indices: list[int],
    loop: asyncio.AbstractEventLoop,
    router: CommandRouter,
) -> dict[str, Any]:
    """Run reduction batch synchronously, streaming progress to stderr."""
    from eqsanscli.services.reduction_service import reduce_row
    from eqsanscli.commands.reduction import _format_time, _summarize_error

    table = state.current_table
    output_dir = state.output_directory
    total = len(indices)
    n_success = 0
    n_fail = 0
    results_detail: list[dict] = []

    _progress(f"Reducing {total} run(s) -> {output_dir}")

    elapsed_times: list[float] = []
    for i, idx in enumerate(indices):
        row = table.get_row(idx)
        if row is None:
            continue

        remaining = total - i
        eta_str = ""
        if elapsed_times:
            avg = sum(elapsed_times) / len(elapsed_times)
            eta_str = f" ETA ~{_format_time(avg * remaining)}"

        bkg_info = f" bkg={row.background_scatt}" if row.background_scatt else " no_bkg"
        _progress(f"[{i+1}/{total}] reducing {row.sample_name} ({row.configuration}){bkg_info} {remaining} left{eta_str}")

        row.status = "reducing"
        result = reduce_row(
            row=row, ipts=state.ipts,
            user_configs=state.configurations, output_dir=output_dir,
            drtsans_version=state.drtsans_version,
        )

        elapsed_times.append(result.elapsed_seconds)

        if result.success:
            n_success += 1
            state.reduced_files.append(result.output_file)
            results_detail.append({
                "row": idx, "sample": row.sample_name, "config": row.configuration,
                "status": "done", "output_file": result.output_file,
                "elapsed": result.elapsed_seconds,
            })
            _progress(f"[{i+1}/{total}] done {row.sample_name} ({row.configuration}) {_format_time(result.elapsed_seconds)}")
        else:
            n_fail += 1
            err = _summarize_error(result.log_file, result.err_file)
            results_detail.append({
                "row": idx, "sample": row.sample_name, "config": row.configuration,
                "status": "error", "error": err,
                "elapsed": result.elapsed_seconds,
            })
            _progress(f"[{i+1}/{total}] FAILED {row.sample_name} ({row.configuration}) {err}")

    total_time = sum(elapsed_times)
    return {
        "type": "reduction_complete",
        "total": total, "success": n_success, "failed": n_fail,
        "elapsed_seconds": total_time,
        "results": results_detail,
    }


def _run_autopilot_sync(
    state: SessionState,
    ipts: int,
    samples: list[str] | None,
    excludes: list[str] | None,
    thickness: float | None,
    bkg_sample: str | None,
    config_filter: str | None,
    loop: asyncio.AbstractEventLoop,
    router: CommandRouter,
) -> dict[str, Any]:
    """Run autopilot synchronously, streaming progress to stderr."""
    from eqsanscli.services.autopilot import run_autopilot_sync

    messages: list[str] = []

    def write(msg: str) -> None:
        clean = _strip_markup(msg)
        messages.append(clean)
        _progress(clean)

    def dispatch_sync(cmd: str) -> CommandResult:
        return loop.run_until_complete(router.dispatch(cmd, state))

    def prompt_user(question: str) -> str:
        # In headless mode, auto-accept prompts (e.g., missing empty beam)
        _progress(f"AUTO-ACCEPT: {_strip_markup(question)}")
        return "yes"

    run_autopilot_sync(
        ipts=ipts,
        state=state,
        dispatch_sync=dispatch_sync,
        write=write,
        cancel_event=None,
        prompt_user=prompt_user,
        sample_filter=samples,
        exclude_filter=excludes,
        thickness=thickness,
        bkg_sample=bkg_sample,
        config_filter=config_filter,
    )

    return {
        "type": "autopilot_complete",
        "ipts": ipts,
        "log": messages,
    }


def run_headless() -> None:
    """Main headless loop — read commands from stdin, write JSON to stdout."""
    state = SessionState()
    state.output_directory = os.path.abspath(state.output_directory)
    router = CommandRouter()
    _register_commands(router, state)

    loop = asyncio.new_event_loop()

    # Try to resume from autosave
    autosave = SessionState.auto_save_path()
    if os.path.exists(autosave):
        try:
            loaded = SessionState.load(autosave)
            state.restore_from(loaded)
            _emit({
                "success": True,
                "message": f"Resumed session (IPTS-{state.ipts}, {len(state.current_table.rows)} rows)",
                "data": None,
            })
        except Exception:
            pass

    _emit({"success": True, "message": "eqsanscli headless mode ready", "data": None})

    try:
        for line in sys.stdin:
            cmd = line.strip()
            if not cmd:
                continue

            try:
                result = loop.run_until_complete(router.dispatch(cmd, state))
            except Exception as exc:
                _emit({"success": False, "message": f"Error: {exc}", "data": None})
                continue

            # Handle special data payloads that need synchronous execution
            if result.data:
                data_type = result.data.get("type")

                if data_type == "start_reduction":
                    reduction_result = _run_reduction_sync(
                        state, result.data["indices"], loop, router,
                    )
                    _emit({
                        "success": True,
                        "message": _strip_markup(result.message) if result.message else "",
                        "data": reduction_result,
                    })
                    _autosave(state)
                    continue

                if data_type == "start_autopilot":
                    autopilot_result = _run_autopilot_sync(
                        state,
                        ipts=result.data["ipts"],
                        samples=result.data.get("samples"),
                        excludes=result.data.get("excludes"),
                        thickness=result.data.get("thickness"),
                        bkg_sample=result.data.get("bkg_sample"),
                        config_filter=result.data.get("config_filter"),
                        loop=loop,
                        router=router,
                    )
                    _emit({
                        "success": True,
                        "message": "",
                        "data": autopilot_result,
                    })
                    _autosave(state)
                    continue

            # Check for exit
            if result.message == "exit":
                _autosave(state)
                _emit({"success": True, "message": "Session saved. Goodbye.", "data": None})
                break

            # Normal result
            clean_message = _strip_markup(result.message) if result.message else ""
            # Serialize data, stripping any non-JSON-serializable parts
            data_out = None
            if result.data:
                try:
                    json.dumps(result.data, default=str)
                    data_out = result.data
                except (TypeError, ValueError):
                    data_out = {"type": result.data.get("type", "unknown")}

            _emit({
                "success": result.success,
                "message": clean_message,
                "data": data_out,
            })
            _autosave(state)

    except (KeyboardInterrupt, EOFError):
        _autosave(state)
        _emit({"success": True, "message": "Session saved.", "data": None})
    finally:
        loop.close()


def _autosave(state: SessionState) -> None:
    """Silently auto-save session state."""
    try:
        state.save(SessionState.auto_save_path())
    except Exception:
        pass
