from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.merge_service import (
    StitchGroup,
    build_stitch_table,
    generate_stitch_script,
    load_stitch_table,
    run_stitch,
    save_stitch_table,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

def _stitch_dir() -> Path:
    d = Path.cwd() / ".eqsanscli" / "stitch"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def handle_stitch(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /stitch build | smart | show | set | run | save | load | removerow | removeconfig | reorder\n"
            "  /stitch build                 — Auto-build stitch table from reduced files\n"
            "  /stitch smart                 — Smart stitch with overlap analysis\n"
            "  /stitch show                  — Display stitch table\n"
            "  /stitch set <sample> overlap <values> — Set overlap Q range\n"
            "  /stitch set <sample> target <idx>     — Set normalization target\n"
            "  /stitch run [sample]          — Execute stitching\n"
            "  /stitch removerow <idx|all>   — Remove row(s) from stitch table\n"
            "  /stitch removeconfig <idx|all> <config> — Remove config from row(s)\n"
            "  /stitch reorder <idx|all> <c1,c2,...>  — Reorder configs in stitch group(s)\n"
            "  /stitch save <name>           — Save stitch table\n"
            "  /stitch load <name>           — Load stitch table",
        )

    sub = args[0].lower()
    if sub == "build":
        return await _handle_build(args[1:], state)
    if sub == "smart":
        return await _handle_smart(args[1:], state)
    if sub == "show":
        return await _handle_show(args[1:], state)
    if sub == "set":
        return await _handle_set(args[1:], state)
    if sub == "run":
        return await _handle_run(args[1:], state)
    if sub == "save":
        return await _handle_save(args[1:], state)
    if sub == "load":
        return await _handle_load(args[1:], state)
    if sub == "script":
        return await _handle_script(args[1:], state)
    if sub in ("removerow", "rmrow"):
        return await _handle_removerow(args[1:], state)
    if sub in ("removeconfig", "rmconfig"):
        return await _handle_removeconfig(args[1:], state)
    if sub == "reorder":
        return await _handle_reorder(args[1:], state)

    return CommandResult(success=False, message=f"Unknown stitch subcommand: {sub}")


async def _handle_build(args: list[str], state: SessionState) -> CommandResult:
    table = state.current_table
    groups = build_stitch_table(table, state.output_directory)

    if not groups:
        return CommandResult(
            success=False,
            message=f"No I(Q) files found in {state.output_directory}\n"
            "  Check /set outputdir or /list iq to verify files exist.",
        )

    state.stitch_groups = groups
    stitchable = [g for g in groups if g.status != "1 config"]
    single = [g for g in groups if g.status == "1 config"]

    msg = (
        f"Built stitch table from {state.output_directory}\n"
        f"  {len(stitchable)} groups ready for stitching, {len(single)} with only 1 config."
    )
    return CommandResult(
        success=True,
        message=msg,
        data={"type": "stitch_table", "groups": [g.to_dict() for g in groups]},
    )


async def _handle_smart(args: list[str], state: SessionState) -> CommandResult:
    """Smart stitching with overlap quality analysis and redundancy detection."""
    from eqsanscli.services.smart_stitch import (
        SmartStitchService,
        build_smart_stitch_table,
    )
    from eqsanscli.services.merge_service import StitchGroup, _scan_output_dir

    table = state.current_table
    output_dir = state.output_directory

    # Strategy 1: Build sample_files dict from working table
    sample_files: dict[str, list[tuple[str, str, float, float]]] = {}
    for row in table.rows:
        if not row.output_file or not os.path.exists(row.output_file):
            row.output_file = os.path.join(output_dir, f"{row.sample_name}_{row.configuration}_Iq.dat")
        if os.path.exists(row.output_file):
            sample_files.setdefault(row.sample_name, []).append(
                (row.output_file, row.configuration, row.detector_distance, row.wavelength)
            )

    # Strategy 2: If no table matches, scan output directory directly
    if not sample_files:
        sample_files = _scan_output_dir(output_dir)

    if not sample_files:
        return CommandResult(
            success=False,
            message=f"No I(Q) files found in {output_dir}\n"
            "  Check /set outputdir or run /stitch build first.",
        )

    # Get LLM handler if available
    llm_handler = getattr(state, "llm_handler", None)
    use_llm = "--llm" in args or "-l" in args

    # Build smart stitch table
    try:
        smart_groups = build_smart_stitch_table(
            sample_files, output_dir, llm_handler=llm_handler, use_llm=use_llm
        )
    except Exception as e:
        file_list = "\n".join(
            f"    {sample}: {len(files)} files"
            for sample, files in sorted(sample_files.items())
        )
        return CommandResult(
            success=False,
            message=f"Failed to build smart stitch table: {e}\n\n"
            f"Found samples:\n{file_list}\n\n"
            f"Output directory: {output_dir}",
        )

    # Convert to StitchGroup objects
    state.stitch_groups = []
    messages = []

    for sg in smart_groups:
        if sg["status"] == "1 config":
            messages.append(f"  {sg['sample_name']}: single config, skipping")
            continue

        if sg["status"] != "ready":
            messages.append(f"  [red]✗[/red] {sg['sample_name']}: {sg.get('llm_advice', 'error')}")
            continue

        output_file = sg.get("output_file", "")
        if not output_file:
            configs_str = "_".join(sg["configs"])
            output_file = os.path.join(output_dir, f"merged_{sg['sample_name']}_{configs_str}_Iq.txt")

        # Create StitchGroup with selected configs
        from eqsanscli.services.merge_service import _default_target_index
        group = StitchGroup(
            sample_name=sg["sample_name"],
            files=sg["files"],
            configs=sg["configs"],
            overlaps=[round(v, 6) for pair in sg["overlaps"] for v in pair],
            target_profile_index=_default_target_index(sg["configs"]),
            output_file=output_file,
            status="ready",
        )

        state.stitch_groups.append(group)

        # Build status message
        all_cfgs = sg.get("all_configs", sg["configs"])
        removed = sg.get("removed_configs", [])

        if len(all_cfgs) > len(sg["configs"]):
            removed_str = ", ".join(f"[yellow]{r['config']}[/yellow]" for r in removed)
            messages.append(
                f"  [green]✓[/green] {sg['sample_name']}:"
                f"\n    Original: {', '.join(all_cfgs)}"
                f"\n    Selected: {', '.join(sg['configs'])}"
                f"\n    [dim]Removed: {removed_str}[/dim]"
            )
        else:
            messages.append(
                f"  [green]✓[/green] {sg['sample_name']}: {', '.join(sg['configs'])}"
                f" [dim](all {len(sg['configs'])} configs kept)[/dim]"
            )

        # Show quality metrics
        quality = sg.get("quality_metrics", [])
        for q in quality:
            icon = "[green]✓[/green]" if q.get("is_good") else "[yellow]~[/yellow]"
            messages.append(
                f"      {icon} Q=[{q['start_q']:.4f}, {q['end_q']:.4f}]: "
                f"{q['n_points']} pts, score={q['score']:.1f}"
            )

    msg = (
        f"Smart stitch analysis complete:\n"
        + "\n".join(messages)
        + f"\n\nUse '/stitch run' to execute stitching with selected configurations."
    )

    return CommandResult(
        success=True,
        message=msg,
        data={"type": "stitch_table", "groups": [g.to_dict() for g in state.stitch_groups]},
    )


async def _handle_show(args: list[str], state: SessionState) -> CommandResult:
    groups = getattr(state, "stitch_groups", None)
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")

    return CommandResult(
        success=True,
        message=f"Stitch table ({len(groups)} groups):",
        data={"type": "stitch_table", "groups": [g.to_dict() for g in groups]},
    )


def _resolve_target_index(value: str, configs: list[str]) -> int | None:
    """Resolve target to index: accepts integer or config_id (e.g., '4m10a')."""
    try:
        return int(value)
    except ValueError:
        pass
    
    from eqsanscli.models.config_id import normalize_config_id
    
    norm_value = normalize_config_id(value)
    for idx, config in enumerate(configs):
        if normalize_config_id(config) == norm_value:
            return idx
    
    return None


def _auto_overlap_centered(files: list[str], n_points: int = 6) -> tuple[list[float], str]:
    """For each adjacent pair in files compute a centered n-point overlap window."""
    import numpy as np
    from eqsanscli.services.plotting_service import load_iq_native
    from eqsanscli.services.smart_stitch import centered_overlap

    flat: list[float] = []
    details: list[str] = []

    for i in range(len(files) - 1):
        try:
            iq_a = load_iq_native(files[i])
            iq_b = load_iq_native(files[i + 1])
            q_a = iq_a.mod_q[np.isfinite(iq_a.intensity)]
            q_b = iq_b.mod_q[np.isfinite(iq_b.intensity)]
            start_q, end_q = centered_overlap(q_a, q_b, n_points)
            flat.extend([round(start_q, 6), round(end_q, 6)])
            details.append(f"pair {i}↔{i+1}: [{start_q:.4f}, {end_q:.4f}]")
        except Exception as e:
            flat.extend([0.0, 0.0])
            details.append(f"pair {i}↔{i+1}: error — {e}")

    return flat, "; ".join(details)


async def _handle_set(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")

    if len(args) < 3:
        return CommandResult(
            success=False,
            message="Usage: /stitch set <idx|sample|all> overlap <q1 q2 ...>\n"
            "       /stitch set <idx|sample|all> overlap auto [n=6]\n"
            "       /stitch set <idx|sample|all> target <index|config_id>\n"
            "       /stitch set --sample <name> target <index|config_id>",
        )

    # Support --sample flag to force sample-name matching
    force_sample = False
    if args[0] == "--sample":
        force_sample = True
        args = args[1:]
        if len(args) < 3:
            return CommandResult(success=False, message="Usage: /stitch set --sample <name> <field> <value>")

    selector = args[0]
    field = args[1].lower()

    if selector.lower() == "all":
        target_groups = groups
    elif force_sample:
        target_groups = [g for g in groups if g.sample_name.lower() == selector.lower()]
    else:
        # Try as index first, then as sample name
        target_groups = []
        try:
            idx = int(selector)
            if 0 <= idx < len(groups):
                target_groups = [groups[idx]]
        except ValueError:
            pass
        if not target_groups:
            target_groups = [g for g in groups if g.sample_name.lower() == selector.lower()]
    if not target_groups:
            return CommandResult(
                success=False,
                message=f"'{selector}' not found as index or sample name in stitch table.",
            )

    if field == "overlap":
        if args[2].lower() == "auto":
            n_points = 4
            if len(args) > 3:
                try:
                    n_points = int(args[3].lstrip("n="))
                except ValueError:
                    pass
            results = []
            for group in target_groups:
                overlaps, detail = _auto_overlap_centered(group.files, n_points)
                group.overlaps = overlaps
                results.append(f"  {group.sample_name}: {detail}")
            return CommandResult(
                success=True,
                message=f"Auto overlaps ({n_points} pts):\n" + "\n".join(results),
            )

        try:
            overlap_values = [float(v) for v in args[2:]]
        except ValueError:
            return CommandResult(success=False, message="Overlap values must be numbers.")
        for group in target_groups:
            group.overlaps = overlap_values
        if selector.lower() == "all":
            return CommandResult(success=True, message=f"Set overlaps for all {len(target_groups)} samples: {overlap_values}")
        return CommandResult(success=True, message=f"Set overlaps for {selector}: {overlap_values}")

    if field == "target":
        results = []
        for group in target_groups:
            idx = _resolve_target_index(args[2], group.configs)
            if idx is None:
                results.append(f"  [red]✗[/red] {group.sample_name}: '{args[2]}' not found in configs {group.configs}")
                continue
            if idx < 0 or idx >= len(group.configs):
                results.append(f"  [red]✗[/red] {group.sample_name}: index {idx} out of range (0-{len(group.configs)-1})")
                continue
            group.target_profile_index = idx
            config_name = group.configs[idx] if group.configs else str(idx)
            results.append(f"  [green]✓[/green] {group.sample_name}: target={idx} ({config_name})")
        
        if selector.lower() == "all":
            return CommandResult(success=True, message=f"Set target for {len(target_groups)} samples:\n" + "\n".join(results))
        return CommandResult(success=True, message="\n".join(results))

    if field == "output":
        for group in target_groups:
            group.output_file = args[2]
        if selector.lower() == "all":
            return CommandResult(success=True, message=f"Set output file for all {len(target_groups)} samples: {args[2]}")
        return CommandResult(success=True, message=f"Set output file for {selector}: {args[2]}")

    return CommandResult(success=False, message=f"Unknown stitch field: {field}. Use 'overlap', 'target', or 'output'.")


async def _handle_run(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")

    if args:
        target_sample = args[0].lower()
        to_run = [g for g in groups if g.sample_name.lower() == target_sample and g.status != "1 config"]
    else:
        to_run = [g for g in groups if g.status != "1 config"]

    if not to_run:
        return CommandResult(success=False, message="No stitchable groups found.")

    results = []
    n_ok = 0
    n_fail = 0
    for group in to_run:
        try:
            out = run_stitch(group)
            n_ok += 1
            results.append(f"  [green]✓[/green] {group.sample_name} → {os.path.basename(out)}")
        except Exception as e:
            n_fail += 1
            group.status = "error"
            results.append(f"  [red]✗[/red] {group.sample_name} — {e}")

    msg = f"Stitch complete: {n_ok} succeeded, {n_fail} failed.\n" + "\n".join(results)
    return CommandResult(success=n_fail == 0, message=msg)


async def _handle_save(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table to save.")
    name = args[0] if args else "default"
    path = str(_stitch_dir() / f"{name}.json")
    save_stitch_table(groups, path)
    return CommandResult(success=True, message=f"Stitch table saved: {path}")


async def _handle_load(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /stitch load <name>")
    name = args[0]
    path = Path(name)
    if not path.exists():
        path = _stitch_dir() / f"{name}.json"
    if not path.exists():
        return CommandResult(success=False, message=f"Stitch table not found: {name}")
    state.stitch_groups = load_stitch_table(str(path))
    return CommandResult(success=True, message=f"Loaded stitch table: {path} ({len(state.stitch_groups)} groups)")


async def _handle_script(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")
    output_path = args[0] if args else os.path.join(state.output_directory, "stitch_script.py")
    path = generate_stitch_script(groups, output_path)
    return CommandResult(success=True, message=f"Stitch script exported: {path}")


async def _handle_removerow(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")

    if not args:
        return CommandResult(
            success=False,
            message="Usage: /stitch removerow <idx|all|--sample name>\n"
            "  /stitch removerow 2              — Remove row 2\n"
            "  /stitch removerow all            — Remove all rows\n"
            "  /stitch removerow --sample SDS   — Remove rows matching sample name (substring)",
        )

    target = args[0].lower()

    if target == "--sample":
        if len(args) < 2:
            return CommandResult(success=False, message="Usage: /stitch removerow --sample <name>")
        pattern = args[1]
        matching = [g for g in groups if sample_matches(pattern, g.sample_name)]
        if not matching:
            return CommandResult(success=False, message=f"No stitch groups matching sample '{pattern}'")
        remaining = [g for g in groups if not sample_matches(pattern, g.sample_name)]
        state.stitch_groups = remaining
        names = ", ".join(g.sample_name for g in matching)
        return CommandResult(
            success=True,
            message=f"Removed {len(matching)} stitch group(s): {names}",
        )

    if target == "all":
        count = len(groups)
        state.stitch_groups = []
        return CommandResult(success=True, message=f"Removed all {count} stitch groups")

    try:
        idx = int(target)
    except ValueError:
        return CommandResult(success=False, message=f"Invalid index: {target}. Use a number, 'all', or '--sample <name>'.")

    if idx < 0 or idx >= len(groups):
        return CommandResult(
            success=False,
            message=f"Index {idx} out of range (0-{len(groups)-1})",
        )

    removed = groups.pop(idx)
    state.stitch_groups = groups
    return CommandResult(
        success=True,
        message=f"Removed stitch group {idx}: {removed.sample_name} ({', '.join(removed.configs)})",
    )


async def _handle_removeconfig(args: list[str], state: SessionState) -> CommandResult:
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(success=False, message="No stitch table. Use /stitch build first.")

    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /stitch removeconfig <idx|all> <config_id>\n"
            "  /stitch removeconfig 0 4m10a    — Remove 4m10a from row 0\n"
            "  /stitch removeconfig all 4m10a  — Remove 4m10a from all rows",
        )

    target = args[0].lower()
    config_to_remove = args[1]

    from eqsanscli.models.config_id import normalize_config_id

    norm_config = normalize_config_id(config_to_remove)

    if target == "all":
        results = []
        for i, group in enumerate(groups):
            result = _remove_config_from_group(group, norm_config)
            if result:
                results.append(f"  Row {i} ({group.sample_name}): {result}")

        if not results:
            return CommandResult(
                success=False,
                message=f"Config '{config_to_remove}' not found in any stitch group",
            )

        return CommandResult(
            success=True,
            message=f"Removed '{config_to_remove}' from stitch groups:\n" + "\n".join(results),
        )

    try:
        idx = int(target)
    except ValueError:
        return CommandResult(success=False, message=f"Invalid index: {target}")

    if idx < 0 or idx >= len(groups):
        return CommandResult(
            success=False,
            message=f"Index {idx} out of range (0-{len(groups)-1})",
        )

    group = groups[idx]
    result = _remove_config_from_group(group, norm_config)

    if not result:
        return CommandResult(
            success=False,
            message=f"Config '{config_to_remove}' not found in row {idx} ({group.sample_name})",
        )

    if len(group.configs) < 2:
        group.status = "1 config"

    return CommandResult(
        success=True,
        message=f"Row {idx} ({group.sample_name}): {result}",
    )


def _remove_config_from_group(group: StitchGroup, norm_config: str) -> str:
    """Remove a config from a stitch group. Returns description of changes or empty string if not found."""
    from eqsanscli.models.config_id import normalize_config_id

    # Find the config to remove
    remove_idx = None
    for i, cfg in enumerate(group.configs):
        if normalize_config_id(cfg) == norm_config:
            remove_idx = i
            break

    if remove_idx is None:
        return ""

    removed_config = group.configs[remove_idx]

    # Remove the file
    if remove_idx < len(group.files):
        removed_file = group.files.pop(remove_idx)
    else:
        removed_file = ""

    # Remove the config
    group.configs.pop(remove_idx)

    # Update overlaps: remove the overlap pair associated with this config
    # Overlaps are pairs: [start1, end1, start2, end2, ...] for N configs -> N-1 pairs
    # Config i is involved in overlaps: (i-1, i) if i>0, and (i, i+1) if i < N-1
    if group.overlaps:
        overlap_pairs = [(group.overlaps[j], group.overlaps[j + 1]) for j in range(0, len(group.overlaps), 2)]

        # Determine which overlap pairs to keep
        new_pairs = []
        for pair_idx, pair in enumerate(overlap_pairs):
            # Pair pair_idx connects config pair_idx and pair_idx+1
            # Keep if neither config is the removed one
            if pair_idx != remove_idx - 1 and pair_idx != remove_idx:
                new_pairs.append(pair)

        # Flatten back
        group.overlaps = [v for pair in new_pairs for v in pair]

    # Update target index if needed
    if group.target_profile_index >= len(group.configs):
        group.target_profile_index = 0
    elif group.target_profile_index > remove_idx:
        group.target_profile_index -= 1

    # Update output filename
    if group.configs:
        configs_str = "_".join(group.configs)
        group.output_file = os.path.join(
            os.path.dirname(group.output_file) or ".",
            f"merged_{group.sample_name}_{configs_str}_Iq.txt",
        )

    # Update status
    if len(group.configs) < 2:
        group.status = "1 config"

    return f"removed {removed_config} (file: {os.path.basename(removed_file)}), overlaps updated"


async def _handle_reorder(args: list[str], state: SessionState) -> CommandResult:
    """Reorder configs within stitch group(s).

    Usage:
        /stitch reorder all conf0,conf1,conf2
        /stitch reorder <idx> conf0,conf1,conf2
    """
    groups: list[StitchGroup] = getattr(state, "stitch_groups", [])
    if not groups:
        return CommandResult(
            success=False,
            message="No stitch table. Use /stitch build first.",
        )

    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /stitch reorder <idx|all> <config1,config2,...>\n"
            "  /stitch reorder all conf0,conf1    — Reorder configs in all groups\n"
            "  /stitch reorder 0 conf0,conf1      — Reorder configs in row 0\n"
            "\n"
            "  Configs are comma-separated, no spaces. The new order determines\n"
            "  which config is lower-Q (first) to higher-Q (last).\n"
            "  Overlaps are recomputed automatically after reordering.",
        )

    target = args[0].lower()
    new_order = [c.strip() for c in args[1].split(",") if c.strip()]

    if not new_order:
        return CommandResult(success=False, message="No config names provided.")

    from eqsanscli.models.config_id import normalize_config_id

    if target == "all":
        target_groups = list(enumerate(groups))
    else:
        try:
            idx = int(target)
        except ValueError:
            return CommandResult(success=False, message=f"Invalid index: {target}")
        if idx < 0 or idx >= len(groups):
            return CommandResult(
                success=False,
                message=f"Index {idx} out of range (0-{len(groups) - 1})",
            )
        target_groups = [(idx, groups[idx])]

    results: list[str] = []
    for row_idx, group in target_groups:
        result = _reorder_group(group, new_order)
        results.append(f"  Row {row_idx} ({group.sample_name}): {result}")

    return CommandResult(
        success=True,
        message="Reorder results:\n" + "\n".join(results),
    )


def _reorder_group(group: StitchGroup, new_order: list[str]) -> str:
    """Reorder configs/files in a group to match new_order. Returns status string."""
    from eqsanscli.models.config_id import normalize_config_id

    if len(group.configs) < 2:
        return "skipped (single config)"

    norm_to_idx: dict[str, int] = {}
    for i, cfg in enumerate(group.configs):
        norm_to_idx[normalize_config_id(cfg)] = i

    new_indices: list[int] = []
    not_found: list[str] = []
    for cfg_name in new_order:
        norm = normalize_config_id(cfg_name)
        if norm in norm_to_idx:
            idx = norm_to_idx[norm]
            if idx not in new_indices:
                new_indices.append(idx)
        else:
            not_found.append(cfg_name)

    if not_found:
        return (
            f"config(s) not found: {', '.join(not_found)}. "
            f"Available: {', '.join(group.configs)}"
        )

    # Configs not mentioned in new_order keep their relative position at the end
    for i in range(len(group.configs)):
        if i not in new_indices:
            new_indices.append(i)

    if new_indices == list(range(len(group.configs))):
        return "no change (already in requested order)"

    old_configs = list(group.configs)

    group.configs = [group.configs[i] for i in new_indices]
    group.files = [group.files[i] for i in new_indices]

    # Target index tracks a position, so remap it after the shuffle
    old_target = group.target_profile_index
    try:
        group.target_profile_index = new_indices.index(old_target)
    except ValueError:
        group.target_profile_index = 0

    if len(group.files) >= 2:
        overlaps, detail = _auto_overlap_centered(group.files)
        group.overlaps = overlaps
        overlap_msg = ", overlaps recomputed"
    else:
        group.overlaps = []
        overlap_msg = ""

    return (
        f"reordered: {', '.join(old_configs)} → {', '.join(group.configs)}"
        f"{overlap_msg}"
    )


