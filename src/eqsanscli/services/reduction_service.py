from __future__ import annotations

import os
import threading
from pathlib import Path

from eqsanscli.integrations.drtsans_runner import ReductionResult, run_reduction
from eqsanscli.integrations.json_builder import build_reduction_json, save_reduction_json
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.config_manager import get_config


def reduce_row(
    row: WorkingTableRow,
    ipts: int,
    user_configs: dict[str, dict],
    output_dir: str = "./output/",
    filename_suffix: str = "",
    cancel_event: threading.Event | None = None,
) -> ReductionResult:
    config_params = get_config(row.configuration, user_configs)

    output_name = f"{row.sample_name}_{row.configuration}"
    if filename_suffix:
        output_name += f"_{filename_suffix}"

    json_data = build_reduction_json(
        ipts=ipts,
        scattering_run=row.scattering_run,
        sample_name=row.sample_name,
        transmission_run=row.transmission_run,
        background_scatt=row.background_scatt,
        background_trans=row.background_trans,
        empty_beam=row.empty_beam,
        thickness=row.thickness,
        config_params=config_params,
        output_dir=output_dir,
        output_filename=output_name,
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    json_path = os.path.join(output_dir, f"{output_name}.json")
    save_reduction_json(json_data, json_path)

    result = run_reduction(json_path, cancel_event=cancel_event)

    standard_output = os.path.join(output_dir, f"{output_name}_Iq.dat")
    frame0_output = os.path.join(output_dir, f"{output_name}_frame_0_Iq.dat")

    if os.path.exists(frame0_output):
        result.output_file = frame0_output
    else:
        result.output_file = standard_output

    if result.cancelled:
        row.status = "cancelled"
    elif result.success:
        row.status = "done"
        row.output_file = result.output_file
    else:
        row.status = "error"

    return result


def parse_row_selection(selection: str, table: WorkingTable) -> list[int]:
    """Parse row selection: "1", "1-4", "1,3,5", "all" → list of 1-based indices."""
    if selection.lower() == "all":
        return [r.index for r in table.rows]

    indices = []
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            indices.extend(range(int(start), int(end) + 1))
        else:
            indices.append(int(part))

    valid = {r.index for r in table.rows}
    return [i for i in indices if i in valid]
