"""Single source of truth for command registration.

Both entry points — `app.py` (Textual TUI) and `headless.py` (JSON protocol) —
call `register_all(router)` so a new command only needs registering ONCE.

Each entry point then registers its own handlers for the few commands that are
inherently front-end specific (`/help`, `/exit`, `/version`, `/list` usage, and
`/guide` in the TUI); those are listed in `ENTRY_POINT_COMMANDS` and are
deliberately NOT registered here.

When adding a command:
  1. add it here (once), and
  2. document it in `services/llm_handler.py` so natural-language routing knows
     it exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.autopilot import handle_autopilot
from eqsanscli.commands.calibrate import handle_calibrate
from eqsanscli.commands.catalog import (
    handle_list_ipts, handle_reclass, handle_refresh_catalog, handle_show, handle_show_table,
)
from eqsanscli.commands.config import (
    handle_config, handle_list_configs, handle_set_config, handle_show_config,
)
from eqsanscli.commands.data import handle_list_iq, handle_list_iqxqy, handle_plot
from eqsanscli.commands.export import handle_confirm, handle_export_script, handle_zipnsend
from eqsanscli.commands.matching import handle_assign, handle_matchruns, handle_remove, handle_set
from eqsanscli.commands.models import handle_models
from eqsanscli.commands.note import handle_note
from eqsanscli.commands.preset import (
    handle_apply_preset, handle_compare, handle_show_preset, handle_show_presets,
)
from eqsanscli.commands.reduction import handle_reduce
from eqsanscli.commands.session import (
    handle_continue, handle_list_tables, handle_load, handle_save, handle_session,
)
from eqsanscli.commands.settings import handle_settings
from eqsanscli.commands.share import handle_share
from eqsanscli.commands.shell import (
    handle_cat, handle_cd, handle_cp, handle_head, handle_ls, handle_mkdir,
    handle_mv, handle_pwd, handle_rm, handle_shell, handle_tail,
)
from eqsanscli.commands.stitch import handle_stitch
from eqsanscli.commands.tables import handle_move, handle_table

if TYPE_CHECKING:
    from eqsanscli.commands.router import CommandRouter

# Commands each entry point must register itself (front-end specific behaviour:
# rendering help, quitting the app, printing a usage stub). Kept here as
# documentation — `register_all` does not touch them.
ENTRY_POINT_COMMANDS = ("help", "exit", "version", "list", "guide")


def register_all(router: CommandRouter) -> None:
    """Register every shared command handler on `router`.

    Compound names ("show table", "set config") are matched before the bare
    command by `CommandRouter._dispatch_command`, so both forms can coexist.
    """
    # --- Catalog -----------------------------------------------------------
    router.register("show", handle_show)
    router.register("show table", handle_show_table)
    router.register("list ipts", handle_list_ipts)
    router.register("reclass", handle_reclass)
    router.register("refresh catalog", handle_refresh_catalog)
    router.register("refresh", handle_refresh_catalog)  # bare /refresh = catalog

    # --- Working table -----------------------------------------------------
    router.register("matchruns", handle_matchruns)
    router.register("set", handle_set)
    router.register("assign", handle_assign)
    router.register("remove", handle_remove)
    router.register("table", handle_table)
    router.register("move", handle_move)

    # --- Configuration & presets -------------------------------------------
    router.register("set config", handle_set_config)
    router.register("show config", handle_show_config)
    router.register("list configs", handle_list_configs)
    router.register("config", handle_config)
    router.register("show presets", handle_show_presets)
    router.register("show preset", handle_show_preset)
    router.register("apply preset", handle_apply_preset)
    router.register("compare", handle_compare)

    # --- Reduction & analysis ----------------------------------------------
    router.register("reduce", handle_reduce)
    router.register("calibrate", handle_calibrate)
    router.register("stitch", handle_stitch)
    router.register("plot", handle_plot)
    router.register("list iq", handle_list_iq)
    router.register("list iqxqy", handle_list_iqxqy)
    router.register("autopilot", handle_autopilot)

    # --- Session persistence ------------------------------------------------
    router.register("save", handle_save)
    router.register("load", handle_load)
    router.register("list tables", handle_list_tables)
    router.register("continue", handle_continue)
    router.register("session", handle_session)

    # --- Export & sharing ---------------------------------------------------
    router.register("export script", handle_export_script)
    router.register("zipnsend", handle_zipnsend)
    router.register("confirm", handle_confirm)
    router.register("share", handle_share)
    router.register("note", handle_note)

    # --- Settings -----------------------------------------------------------
    router.register("models", handle_models)
    router.register("settings", handle_settings)

    # --- Shell passthrough --------------------------------------------------
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

    # --- Aliases ------------------------------------------------------------
    router.alias("quit", "exit")
    router.alias("q", "exit")
    router.alias("dir", "ls")
    router.alias("shell", "sh")
