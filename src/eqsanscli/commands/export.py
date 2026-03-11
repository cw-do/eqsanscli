from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.script_exporter import export_reduction_script

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_export_script(args: list[str], state: SessionState) -> CommandResult:
    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message="Working table is empty. Use /matchruns first.")

    if args:
        output_path = args[0]
    else:
        output_path = os.path.join(
            state.output_directory,
            f"reduce_{state.ipts}_{table.name}.py",
        )

    path = export_reduction_script(
        table=table,
        user_configs=state.configurations,
        output_dir=state.output_directory,
        output_path=output_path,
        ipts=state.ipts,
    )

    n_configs = len(table.configurations)
    n_rows = len(table.rows)
    return CommandResult(
        success=True,
        message=f"Exported reduction script: {path}\n"
        f"  {n_rows} samples across {n_configs} configurations.\n"
        f"  Run with: drtsans {path}",
    )
