from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from eqsanscli.models.config_id import normalize_config_id
from eqsanscli.models.working_table import WorkingTable
from eqsanscli.services.config_manager import get_config

_PATH_PARAMS = frozenset({
    "maskfilename", "sensitivityfilename", "darkfilename",
    "beamfluxfilename",
})


def _extract_path_vars(
    paths: list[str],
    reserved: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Find common directory prefixes and assign short variable names.

    Returns (var_defs, path_replacements):
        var_defs: {"data_dir": "/SNS/EQSANS/...", ...}
        path_replacements: {"/SNS/EQSANS/.../file.nxs": "data_dir + 'file.nxs'", ...}
    """
    reserved = reserved or set()

    dir_counts: Counter[str] = Counter()
    path_to_dir: dict[str, str] = {}
    for p in paths:
        if not p or not os.path.isabs(p):
            continue
        d = os.path.dirname(p)
        if d and d != "/":
            trailing = d if d.endswith("/") else d + "/"
            dir_counts[trailing] += 1
            path_to_dir[p] = trailing

    used_names: set[str] = set(reserved)
    var_defs: dict[str, str] = {}
    dir_to_var: dict[str, str] = {}

    for d, count in dir_counts.most_common():
        if count < 2:
            break
        if d in dir_to_var:
            continue
        var_name = _dir_to_varname(d, used_names)
        used_names.add(var_name)
        var_defs[var_name] = d
        dir_to_var[d] = var_name

    path_replacements: dict[str, str] = {}
    for p, d in path_to_dir.items():
        if d in dir_to_var:
            var_name = dir_to_var[d]
            fname = os.path.basename(p)
            path_replacements[p] = f"{var_name} + '{fname}'"

    return var_defs, path_replacements


def _dir_to_varname(dirpath: str, used: set[str]) -> str:
    parts = [p for p in dirpath.rstrip("/").split("/") if p]

    candidates: list[str] = []
    if parts:
        last = parts[-1].lower().replace("-", "_").replace(".", "_")
        if last.endswith("_mp"):
            candidates.append("calib_dir")
        elif "nexus" in last.lower() or "nxs" in last.lower():
            candidates.append("nexus_dir")
        elif "output" in last.lower():
            candidates.append("output_dir")
        elif "shared" in last.lower():
            candidates.append("shared_dir")
        elif "script" in last.lower():
            candidates.append("script_dir")
        candidates.append(last + "_dir")
    candidates.append("path_dir")

    for name in candidates:
        clean = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if clean and not clean[0].isdigit() and clean not in used:
            return clean

    base = candidates[0] if candidates else "path_dir"
    base = "".join(c if c.isalnum() or c == "_" else "_" for c in base)
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def export_reduction_script(
    table: WorkingTable,
    user_configs: dict[str, dict],
    output_dir: str,
    output_path: str,
    ipts: int = 0,
) -> str:
    lines: list[str] = []
    _emit_header(lines, table, ipts, output_dir)

    # Group by (parameter config, physics config): the first picks the reduction
    # parameters (so a per-row override / cloned config is honoured), the second
    # names the output files. Filenames follow the physics config for the same
    # reason WorkingTableRow.output_stem does — a clone label like "4m10a_v2"
    # must never reach a filename. (The emitted script keeps the legacy
    # eqsanstools "." → "o" spelling, e.g. 2.5m2.5a → 2o5m2o5a.)
    groups: dict[tuple[str, str], list] = {}
    for row in table.rows:
        groups.setdefault((row.configuration, row.physical_configuration), []).append(row)

    all_paths: list[str] = []
    all_configs: list[tuple[str, str, list, dict]] = []
    for (config_label, file_label), rows in sorted(groups.items()):
        config_params = get_config(config_label, user_configs)
        all_configs.append((config_label, file_label, rows, config_params))
        for key in _PATH_PARAMS:
            val = config_params.get(key)
            if val and isinstance(val, str) and os.path.isabs(val):
                all_paths.append(val)

    var_defs, path_replacements = _extract_path_vars(
        all_paths, reserved={"ipts_number", "output_directory"},
    )
    if var_defs:
        for var_name, dirpath in var_defs.items():
            lines.append(f"{var_name} = '{dirpath}'")
        lines.append("")

    for config_label, file_label, rows, config_params in all_configs:
        _emit_config_block(lines, config_label, rows, config_params, ipts,
                           path_replacements, file_label=file_label)

    lines.append(f"\nreduction_confirm({ipts})")
    lines.append("")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    return output_path


def _emit_header(lines: list[str], table: WorkingTable, ipts: int, output_dir: str) -> None:
    lines.append("#!/usr/bin/env python3")
    lines.append(f"# Generated by eqsanscli on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"# IPTS: {ipts} | Table: {table.name} | Configs: {', '.join(table.configurations)}")
    lines.append("#")
    lines.append(f"# Usage: drtsans {Path(output_dir).name}/reduce_{ipts}.py")
    lines.append("")
    lines.append("from mantid.simpleapi import *")
    lines.append("import os, sys, time")
    lines.append("sys.path.append('/SNS/EQSANS/shared/script/eqsanstools')")
    lines.append("from eqsans_drtsans_script import *")
    lines.append("")
    lines.append(f"ipts_number = {ipts}")
    lines.append(f'output_directory = "{output_dir}"')
    lines.append("")


def _emit_config_block(
    lines: list[str],
    config_label: str,
    rows: list,
    config_params: dict,
    ipts: int,
    path_replacements: dict[str, str] | None = None,
    file_label: str = "",
) -> None:
    """Emit one reduction loop for a config group.

    `config_label` identifies the reduction parameters (may be a cloned config
    like "4m10a_v2"); `file_label` is the physics config used in output
    filenames. Defaults to `config_label` when not given.
    """
    file_label = file_label or config_label
    lines.append(f"# {'='*60}")
    lines.append(f"# Configuration: {config_label}")
    if file_label != config_label:
        lines.append(f"# Output files named for physical config: {file_label}")
    lines.append(f"# {'='*60}")

    samscatt = [r.scattering_run for r in rows]
    samtrans = [r.transmission_run for r in rows]
    bkgscatt = [r.background_scatt for r in rows]
    bkgtrans = [r.background_trans for r in rows]
    emptybeam = [r.empty_beam for r in rows]
    thickness = [str(r.thickness) for r in rows]
    names = [r.sample_name for r in rows]

    lines.append(f"samscatt = {samscatt}")
    lines.append(f"samtrans = {samtrans}")
    lines.append(f"bkgscatt = {bkgscatt}")
    lines.append(f"bkgtrans = {bkgtrans}")
    lines.append(f"emptybeam = {emptybeam}")
    lines.append(f"sample_thick = {thickness}")
    lines.append(f"sample_names = {names}")
    lines.append("")
    lines.append("for i in range(len(samscatt)):")
    lines.append("    eq = EQVar()")
    lines.append(f"    eq._outputdir = output_directory")
    lines.append(f"    eq._ipts = ipts_number")

    # Emit config params as EQVar attributes
    eqvar_map = {
        "standardabsolutescale": "_standardabsolutescale",
        "sampleaperturesize": "_sampleaperturesize",
        "maskfilename": "_maskfilename",
        "sensitivityfilename": "_sensitivityfilename",
        "darkfilename": "_darkfilename",
        "beamfluxfilename": "_beamfluxfilename",
        "numqbins": "_numqbins",
        "numqxqybins": "_numqxqybins",
        "qbintype": "_qbintype",
        "qmin": "_qmin",
        "qmax": "_qmax",
        "cuttofmin": "_cuttofmin",
        "cuttofmax": "_cuttofmax",
        "wavelengthstep": "_wavelengthstep",
        "sampleoffset": "_sampleoffset",
        "detectoroffset": "_detectoroffset",
        "fitinelasticincoh": "_fitinelasticincoh",
        "selectminincoh": "_selectminincoh",
        "useerrorweighting": "_useerrorweighting",
        "incohfit_qmin": "_incohfit_qmin",
        "incohfit_qmax": "_incohfit_qmax",
        "outputwavelengthdependentprofile": "_outputwavelengthdependentprofile",
        "usemaskbacktubes": "_usemaskbacktubes",
        "usetimeslice": "_usetimeslice",
        "timesliceinterval": "_timesliceinterval",
    }

    for param_key, eqvar_attr in eqvar_map.items():
        val = config_params.get(param_key)
        if val is not None and val != "":
            if (path_replacements
                    and isinstance(val, str)
                    and val in path_replacements):
                lines.append(f"    eq.{eqvar_attr} = {path_replacements[val]}")
            else:
                lines.append(f"    eq.{eqvar_attr} = {repr(val)}")

    # Scale components (special handling — list value)
    scale = config_params.get("scalecomponents.detector1")
    if scale and isinstance(scale, list):
        lines.append(f"    eq._scalecomponents = {scale}")

    lines.append("    eq._showjson = False")
    lines.append("    eq._empty = emptybeam[i]")
    lines.append("    eq._thickness = float(sample_thick[i])")
    lines.append("    eq._bkgscatt = str(bkgscatt[i])")
    lines.append("    eq._bkgtrans = str(bkgtrans[i])")
    lines.append("    eq._samscatt = str(samscatt[i])")
    lines.append("    eq._samtrans = str(samtrans[i])")

    safe_label = file_label.replace(".", "o")
    lines.append(f"    eq._filename = str(sample_names[i]) + '_{safe_label}'")
    lines.append("    reduceNow(eq)")
    lines.append("")
