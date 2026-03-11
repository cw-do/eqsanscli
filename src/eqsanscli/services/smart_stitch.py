"""Smart stitching — intelligent overlap analysis and curve selection.

This module provides:
1. Overlap quality analysis (number of points, position, error statistics)
2. Configuration redundancy detection
3. LLM-based decision making for complex stitching scenarios
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from eqsanscli.services.llm_handler import LLMHandler

from eqsanscli.services.plotting_service import load_iq_native


def centered_overlap(q_a: np.ndarray, q_b: np.ndarray, n_points: int = 4) -> tuple[float, float]:
    """Return (start_q, end_q) of a centered n-point overlap window between two Q arrays.

    Pools all Q values from both curves within their intersection, then picks
    n_points symmetrically around the center of that pool. This avoids using
    the full intersection (which is too wide) and produces a tight, stable
    scaling region consistent with /stitch set overlap auto.
    """
    intersect_start = max(float(q_a[0]), float(q_b[0]))
    intersect_end   = min(float(q_a[-1]), float(q_b[-1]))

    if intersect_start >= intersect_end:
        return intersect_start, intersect_end

    q_pool = np.union1d(
        q_a[(q_a >= intersect_start) & (q_a <= intersect_end)],
        q_b[(q_b >= intersect_start) & (q_b <= intersect_end)],
    )
    q_pool = np.sort(q_pool)
    n_avail = len(q_pool)

    if n_avail <= n_points:
        return float(q_pool[0]), float(q_pool[-1])

    center_idx = n_avail // 2
    half = n_points // 2
    lo = max(0, center_idx - half)
    hi = lo + n_points
    if hi > n_avail:
        hi = n_avail
        lo = hi - n_points
    return float(q_pool[lo]), float(q_pool[hi - 1])


@dataclass
class OverlapQuality:
    """Quality metrics for a single overlap region between two curves."""

    start_q: float
    end_q: float
    n_points_low: int  # points from low-q curve in overlap
    n_points_high: int  # points from high-q curve in overlap
    n_points_min: int  # minimum of the two (bottleneck)
    overlap_fraction_low: float  # fraction of low-q curve covered
    overlap_fraction_high: float  # fraction of high-q curve covered
    center_offset: float  # how close to center of overlap (0=center, 1=edge)
    intensity_ratio: float  # mean I_low / I_high in overlap
    intensity_ratio_std: float  # std of ratio (lower = more consistent)
    relative_error_low: float  # mean error/I in overlap
    relative_error_high: float  # mean error/I in overlap
    max_relative_error: float  # max of the two
    chi2_per_point: float  # chi2 of low vs high interpolated
    is_good: bool = False  # passes basic criteria
    quality_score: float = 0.0  # 0-100 composite score
    recommendation: str = ""  # human-readable assessment


@dataclass
class StitchConfig:
    """A configuration with its file and metadata."""

    config_id: str
    file_path: str
    distance: float
    q_range: tuple[float, float]
    n_points: int


@dataclass
class StitchPlan:
    """A plan for stitching a sample with selected configurations."""

    sample_name: str
    all_configs: list[StitchConfig]
    selected_configs: list[StitchConfig]  # subset after redundancy removal
    overlaps: list[tuple[float, float]]  # selected overlap regions
    target_config: StitchConfig  # normalization reference
    quality_metrics: list[OverlapQuality]
    removed_configs: list[tuple[StitchConfig, str]]  # (config, reason)
    llm_analysis: str = ""  # LLM's reasoning
    confidence: float = 0.0  # 0-1 confidence in the plan


class OverlapAnalyzer:
    """Analyze overlap quality between I(Q) curves."""

    MIN_POINTS_REQUIRED = 3
    CENTER_ZONE_FRACTION = 0.3  # consider "middle" as 30% of overlap region

    def __init__(self, min_points: int = 3, max_rel_error: float = 0.5):
        self.min_points = min_points
        self.max_rel_error = max_rel_error

    def analyze_overlap(
        self,
        iq_low: SimpleNamespace,
        iq_high: SimpleNamespace,
        suggested_start: float | None = None,
        suggested_end: float | None = None,
    ) -> OverlapQuality:
        """Analyze the overlap between two curves.

        Args:
            iq_low: Lower Q curve (SimpleNamespace with mod_q, intensity, error)
            iq_high: Higher Q curve (SimpleNamespace with mod_q, intensity, error)
            suggested_start: Optional suggested start of overlap
            suggested_end: Optional suggested end of overlap

        Returns:
            OverlapQuality with detailed metrics
        """
        q_low = iq_low.mod_q
        q_high = iq_high.mod_q
        i_low = iq_low.intensity
        i_high = iq_high.intensity
        e_low = iq_low.error if iq_low.error is not None else np.zeros_like(i_low)
        e_high = iq_high.error if iq_high.error is not None else np.zeros_like(i_high)

        # Determine overlap Q range
        if suggested_start is not None and suggested_end is not None:
            start_q = max(suggested_start, q_high[0], q_low[0])
            end_q = min(suggested_end, q_low[-1], q_high[-1])
        else:
            start_q = max(q_high[0], q_low[0])
            end_q = min(q_low[-1], q_high[-1])

        if start_q >= end_q:
            return OverlapQuality(
                start_q=start_q,
                end_q=end_q,
                n_points_low=0,
                n_points_high=0,
                n_points_min=0,
                overlap_fraction_low=0.0,
                overlap_fraction_high=0.0,
                center_offset=1.0,
                intensity_ratio=1.0,
                intensity_ratio_std=0.0,
                relative_error_low=1.0,
                relative_error_high=1.0,
                max_relative_error=1.0,
                chi2_per_point=0.0,
                is_good=False,
                quality_score=0.0,
                recommendation="No overlap region found",
            )

        # Find points in overlap region
        mask_low = (q_low >= start_q) & (q_low <= end_q)
        mask_high = (q_high >= start_q) & (q_high <= end_q)

        n_low = int(np.sum(mask_low))
        n_high = int(np.sum(mask_high))
        n_min = min(n_low, n_high)

        # Calculate overlap fractions
        q_range_low = q_low[-1] - q_low[0]
        q_range_high = q_high[-1] - q_high[0]
        frac_low = (end_q - start_q) / q_range_low if q_range_low > 0 else 0
        frac_high = (end_q - start_q) / q_range_high if q_range_high > 0 else 0

        # Calculate center offset (0 = centered, 1 = at edge)
        center_zone_low = self._center_zone(q_low)
        center_zone_high = self._center_zone(q_high)
        points_in_center_low = np.sum(mask_low & center_zone_low)
        points_in_center_high = np.sum(mask_high & center_zone_high)
        center_offset = 1.0 - (
            (points_in_center_low + points_in_center_high) / max(n_low + n_high, 1)
        )

        # Intensity ratio analysis
        if n_low > 0 and n_high > 0:
            # Interpolate high-Q curve to low-Q points in overlap
            good_high = np.isfinite(i_high)
            i_high_interp = np.interp(
                q_low[mask_low], q_high[good_high], i_high[good_high]
            )
            ratios = i_low[mask_low] / np.maximum(i_high_interp, 1e-10)
            ratios = ratios[np.isfinite(ratios) & (ratios > 0)]

            intensity_ratio = float(np.median(ratios)) if len(ratios) > 0 else 1.0
            intensity_std = float(np.std(ratios)) if len(ratios) > 1 else 0.0

            # Chi2 calculation
            expected = i_high_interp
            observed = i_low[mask_low]
            errors = e_low[mask_low]
            chi2 = np.sum(((observed - expected) / np.maximum(errors, 1e-10)) ** 2)
            chi2_per_point = chi2 / max(n_low, 1)
        else:
            intensity_ratio = 1.0
            intensity_std = 0.0
            chi2_per_point = 0.0

        # Relative errors
        rel_err_low = np.mean(e_low[mask_low] / np.maximum(i_low[mask_low], 1e-10)) if n_low > 0 else 1.0
        rel_err_high = np.mean(e_high[mask_high] / np.maximum(i_high[mask_high], 1e-10)) if n_high > 0 else 1.0

        # Quality scoring (0-100)
        score_components = {
            "points": min(n_min / self.min_points, 5.0) * 20,  # 0-100
            "centered": (1.0 - center_offset) * 100,  # 0-100
            "consistency": max(0, 100 - intensity_std * 100),  # 0-100
            "low_error": max(0, 100 - max(rel_err_low, rel_err_high) * 200),  # 0-100
        }
        quality_score = sum(score_components.values()) / len(score_components)

        # Determine if overlap is "good"
        is_good = (
            n_min >= self.min_points
            and center_offset < 0.5  # Not too close to edge
            and max(rel_err_low, rel_err_high) < self.max_rel_error
            and intensity_std < 0.5  # Consistent intensity ratio
        )

        # Generate recommendation
        issues = []
        if n_min < self.min_points:
            issues.append(f"only {n_min} points (need {self.min_points})")
        if center_offset >= 0.5:
            issues.append("overlap near edge of data")
        if max(rel_err_low, rel_err_high) >= self.max_rel_error:
            issues.append("high relative errors")
        if intensity_std >= 0.5:
            issues.append("inconsistent intensity ratio")

        if is_good:
            recommendation = f"Good overlap: {n_min} points, Q=[{start_q:.4f}, {end_q:.4f}], score={quality_score:.1f}"
        elif issues:
            recommendation = f"Poor overlap: {', '.join(issues)}"
        else:
            recommendation = "Marginal overlap"

        return OverlapQuality(
            start_q=start_q,
            end_q=end_q,
            n_points_low=n_low,
            n_points_high=n_high,
            n_points_min=n_min,
            overlap_fraction_low=frac_low,
            overlap_fraction_high=frac_high,
            center_offset=center_offset,
            intensity_ratio=intensity_ratio,
            intensity_ratio_std=intensity_std,
            relative_error_low=rel_err_low,
            relative_error_high=rel_err_high,
            max_relative_error=max(rel_err_low, rel_err_high),
            chi2_per_point=chi2_per_point,
            is_good=is_good,
            quality_score=quality_score,
            recommendation=recommendation,
        )

    def _center_zone(self, q: np.ndarray) -> np.ndarray:
        """Return mask for center zone of Q range."""
        q_min, q_max = q[0], q[-1]
        center = (q_min + q_max) / 2
        half_width = (q_max - q_min) * self.CENTER_ZONE_FRACTION / 2
        return (q >= center - half_width) & (q <= center + half_width)


class ConfigurationSelector:
    """Select optimal configurations to stitch, removing redundant ones."""

    def __init__(self, analyzer: OverlapAnalyzer | None = None):
        self.analyzer = analyzer or OverlapAnalyzer()

    def select_configurations(
        self,
        configs: list[StitchConfig],
        profiles: list[SimpleNamespace],
    ) -> tuple[list[StitchConfig], list[OverlapQuality], list[tuple[StitchConfig, str]]]:
        """Select configurations to use, removing redundant ones.

        Strategy:
        1. Sort by Q range (low to high)
        2. Check each consecutive pair for overlap quality
        3. If three configs (low, mid, high) and low:mid ≈ mid:high overlap,
           mid is redundant — skip it and stitch low:high directly

        Returns:
            (selected_configs, quality_metrics, removed_configs_with_reasons)
        """
        if len(configs) <= 2:
            # Need at least 3 configs to detect redundancy
            return configs, [], []

        # Sort by Q range (lowest Q first)
        sorted_order = sorted(range(len(configs)), key=lambda i: configs[i].q_range[0])
        sorted_configs = [configs[i] for i in sorted_order]
        sorted_profiles = [profiles[i] for i in sorted_order]

        selected = []
        removed = []
        qualities = []

        i = 0
        while i < len(sorted_configs):
            cfg = sorted_configs[i]
            prof = sorted_profiles[i]

            if i == 0:
                # Always include first (lowest Q)
                selected.append(cfg)
                i += 1
                continue

            # Check if we can skip this config (redundancy check)
            if i < len(sorted_configs) - 1 and len(selected) > 0:
                prev_idx = len(selected) - 1
                prev_cfg = selected[prev_idx]
                prev_prof = sorted_profiles[sorted_configs.index(prev_cfg)]

                next_cfg = sorted_configs[i + 1]
                next_prof = sorted_profiles[i + 1]

                # Analyze both overlaps
                current_overlap = self.analyzer.analyze_overlap(prev_prof, prof)
                next_overlap = self.analyzer.analyze_overlap(prev_prof, next_prof)

                # Check if current config is redundant
                if self._is_redundant(current_overlap, next_overlap):
                    removed.append((cfg, f"Redundant: {prev_cfg.config_id}→{cfg.config_id}→{next_cfg.config_id} has similar overlaps"))
                    qualities.append(current_overlap)
                    i += 1
                    continue

            # Include this config
            if len(selected) > 0:
                prev_cfg = selected[-1]
                prev_prof_idx = sorted_configs.index(prev_cfg)
                overlap = self.analyzer.analyze_overlap(
                    sorted_profiles[prev_prof_idx], prof
                )
                qualities.append(overlap)

            selected.append(cfg)
            i += 1

        return selected, qualities, removed

    def _is_redundant(
        self,
        overlap_with_current: OverlapQuality,
        overlap_without_current: OverlapQuality,
    ) -> bool:
        """Determine if the middle config is redundant.

        Conditions for redundancy:
        1. overlap_with_current is similar to overlap_without_current
        2. Both overlaps have sufficient quality
        3. Skipping doesn't lose too much Q coverage
        """
        # Check if overlaps are similar (within 20% in Q range)
        q_range_current = overlap_with_current.end_q - overlap_with_current.start_q
        q_range_skip = overlap_without_current.end_q - overlap_without_current.start_q

        if q_range_skip < q_range_current * 0.5:
            # Skipping would lose significant Q coverage
            return False

        # Check if both overlaps are decent
        min_quality = 30.0  # threshold
        if overlap_with_current.quality_score < min_quality:
            return False  # Current is poor, but that's no reason to skip it

        if overlap_without_current.quality_score < min_quality:
            return False  # Direct overlap is poor, need intermediate

        # Check overlap similarity
        q_similarity = abs(q_range_skip - q_range_current) / max(q_range_current, 1e-10)
        center_similarity = abs(
            overlap_with_current.center_offset - overlap_without_current.center_offset
        )

        # If overlaps are similar in range and position, middle config is redundant
        return q_similarity < 0.3 and center_similarity < 0.3


class LLMStitchAdvisor:
    """Use LLM to make intelligent stitching decisions."""

    SYSTEM_PROMPT = """You are an expert in small-angle neutron scattering (SANS) data analysis, specifically for the EQSANS instrument at SNS/ORNL.

Your task is to evaluate stitching plans for I(Q) curves from multiple detector configurations. Each configuration provides data in a different Q range based on detector distance and wavelength.

Key principles:
1. Overlap regions should have 3-4 data points minimum
2. Overlap should be in the "middle" of the data (not at edges where errors are high)
3. If three configurations (low-Q, mid-Q, high-Q) have similar overlaps (low:mid ≈ mid:high), the mid-Q configuration adds little value and can be skipped
4. The goal is the smoothest combined curve with minimal stitching artifacts

Evaluate the provided stitching plan and provide:
1. Your assessment of the quality
2. Whether any configurations should be added or removed
3. Recommended overlap Q ranges
4. Confidence in your recommendation (0-1)

Respond in JSON format:
{
  "assessment": "Brief description of current plan",
  "recommendations": ["specific changes to make"],
  "add_configs": ["config_ids to add"],
  "remove_configs": ["config_ids to remove"],
  "suggested_overlaps": [[start_q1, end_q1], [start_q2, end_q2], ...],
  "confidence": 0.85,
  "reasoning": "explanation of your decision"
}"""

    def __init__(self, llm_handler: LLMHandler | None = None):
        self.llm_handler = llm_handler

    def advise(
        self,
        plan: StitchPlan,
    ) -> StitchPlan:
        """Get LLM advice on a stitching plan.

        Returns an updated plan with LLM recommendations.
        """
        if self.llm_handler is None:
            return plan

        # Build context for LLM
        context = self._build_context(plan)

        try:
            response = self.llm_handler.get_completion(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=context,
                temperature=0.3,
            )

            # Parse LLM response
            parsed = self._parse_response(response)

            # Update plan with LLM suggestions
            updated_plan = self._apply_suggestions(plan, parsed)
            updated_plan.llm_analysis = parsed.get("reasoning", "")
            updated_plan.confidence = parsed.get("confidence", 0.5)

            return updated_plan

        except Exception as e:
            # If LLM fails, return original plan
            plan.llm_analysis = f"LLM advisory failed: {e}"
            plan.confidence = 0.0
            return plan

    def _build_context(self, plan: StitchPlan) -> str:
        """Build detailed context for LLM."""
        lines = [
            f"Sample: {plan.sample_name}",
            f"Total configurations available: {len(plan.all_configs)}",
            f"Proposed for stitching: {len(plan.selected_configs)}",
            "",
            "Available configurations:",
        ]

        for cfg in plan.all_configs:
            lines.append(
                f"  - {cfg.config_id}: Q=[{cfg.q_range[0]:.4f}, {cfg.q_range[1]:.4f}], "
                f"{cfg.n_points} points, distance={cfg.distance}m"
            )

        lines.extend(["", "Selected configurations:"])
        for cfg in plan.selected_configs:
            lines.append(f"  - {cfg.config_id}")

        if plan.removed_configs:
            lines.extend(["", "Removed as redundant:"])
            for cfg, reason in plan.removed_configs:
                lines.append(f"  - {cfg.config_id}: {reason}")

        lines.extend(["", "Overlap quality metrics:"])
        for i, q in enumerate(plan.quality_metrics):
            lines.append(
                f"  Overlap {i+1}: Q=[{q.start_q:.4f}, {q.end_q:.4f}], "
                f"{q.n_points_min} points, score={q.quality_score:.1f}, "
                f"{q.recommendation}"
            )

        lines.extend(["", "Proposed overlaps:", str(plan.overlaps)])

        return "\n".join(lines)

    def _parse_response(self, response: str) -> dict:
        """Parse LLM JSON response."""
        try:
            # Try to find JSON in response
            start = response.find("{")
            end = response.rfind("}")
            if start >= 0 and end > start:
                json_str = response[start : end + 1]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Fallback: return empty structure
        return {
            "assessment": "Could not parse LLM response",
            "recommendations": [],
            "add_configs": [],
            "remove_configs": [],
            "suggested_overlaps": [],
            "confidence": 0.0,
            "reasoning": response[:500],
        }

    def _apply_suggestions(self, plan: StitchPlan, parsed: dict) -> StitchPlan:
        """Apply LLM suggestions to update the plan."""
        # This is a placeholder - in practice, you'd implement
        # full plan modification based on LLM suggestions
        # For now, just update the analysis
        return plan


class SmartStitchService:
    """High-level service for intelligent stitching."""

    def __init__(self, llm_handler: LLMHandler | None = None):
        self.analyzer = OverlapAnalyzer()
        self.selector = ConfigurationSelector(self.analyzer)
        self.advisor = LLMStitchAdvisor(llm_handler)

    def create_stitch_plan(
        self,
        sample_name: str,
        config_files: list[tuple[str, str, float, float]],  # (file_path, config_id, distance, wavelength)
        use_llm: bool = True,
    ) -> StitchPlan | None:
        """Create an intelligent stitching plan.

        Args:
            sample_name: Name of the sample
            config_files: List of (file_path, config_id, distance)
            use_llm: Whether to consult LLM for final decision

        Returns:
            StitchPlan or None if insufficient data
        """
        if len(config_files) < 2:
            return None

        # Load profiles and build StitchConfigs
        configs = []
        profiles = []
        errors = []

        for fpath, cfg_id, dist, _wl in config_files:
            # Debug: check file exists
            if not os.path.exists(fpath):
                errors.append(f"{os.path.basename(fpath)}: File does not exist: {fpath}")
                continue

            try:
                profile = load_iq_native(fpath)
                q_min = float(profile.mod_q[0])
                q_max = float(profile.mod_q[-1])
                n_pts = len(profile.mod_q)

                configs.append(
                    StitchConfig(
                        config_id=cfg_id,
                        file_path=fpath,
                        distance=dist,
                        q_range=(q_min, q_max),
                        n_points=n_pts,
                    )
                )
                profiles.append(profile)
            except Exception as e:
                import traceback
                errors.append(f"{os.path.basename(fpath)}: {type(e).__name__}: {e}")
                continue

        if len(configs) < 2:
            error_msg = "\n".join(errors) if errors else "Could not load enough files"
            raise ValueError(
                f"Failed to create stitch plan: need >=2 configs, got {len(configs)}.\n"
                f"Errors:\n{error_msg}"
            )

        # Select configurations (remove redundant ones)
        selected, qualities, removed = self.selector.select_configurations(
            configs, profiles
        )

        # Build overlaps for selected configs using centered n-point windows
        n_overlap_points = 6
        overlaps = []
        selected_profiles = []
        for cfg in selected:
            idx = next(j for j, c in enumerate(configs) if c.config_id == cfg.config_id)
            selected_profiles.append(profiles[idx])

        for i in range(len(selected) - 1):
            q_a = selected_profiles[i].mod_q[np.isfinite(selected_profiles[i].intensity)]
            q_b = selected_profiles[i + 1].mod_q[np.isfinite(selected_profiles[i + 1].intensity)]
            start_q, end_q = centered_overlap(q_a, q_b, n_overlap_points)
            overlaps.append((round(start_q, 6), round(end_q, 6)))

        # Determine target (use first selected as default)
        target = selected[0] if selected else configs[0]

        plan = StitchPlan(
            sample_name=sample_name,
            all_configs=configs,
            selected_configs=selected,
            overlaps=overlaps,
            target_config=target,
            quality_metrics=qualities,
            removed_configs=removed,
        )

        # Consult LLM if requested
        if use_llm and self.advisor.llm_handler is not None:
            plan = self.advisor.advise(plan)

        return plan

    def execute_plan(self, plan: StitchPlan) -> str:
        """Execute a stitch plan and return output file path."""
        from eqsanscli.services.merge_service import stitch_profiles, save_iq

        profiles = [load_iq_native(cfg.file_path) for cfg in plan.selected_configs]

        if len(profiles) < 2:
            raise ValueError("Need at least 2 profiles to stitch")

        # Flatten overlaps
        flat_overlaps = []
        for start, end in plan.overlaps:
            flat_overlaps.extend([start, end])

        # Find target index
        target_idx = 0
        for i, cfg in enumerate(plan.selected_configs):
            if cfg.config_id == plan.target_config.config_id:
                target_idx = i
                break

        stitched = stitch_profiles(profiles, flat_overlaps, target_idx)

        # Generate output filename
        configs_str = "_".join(cfg.config_id for cfg in plan.selected_configs)
        output_file = Path(plan.selected_configs[0].file_path).parent / f"merged_{plan.sample_name}_{configs_str}_Iq.txt"

        save_iq(stitched, str(output_file))

        return str(output_file)


def build_smart_stitch_table(
    sample_files: dict[str, list[tuple[str, str, float, float]]],
    output_dir: str,
    llm_handler: LLMHandler | None = None,
    use_llm: bool = True,
) -> list[dict]:
    """Build stitch groups with intelligent configuration selection.

    Args:
        sample_files: Dict of {sample_name: [(file, config_id, distance, wavelength), ...]}
        output_dir: Output directory for stitched files
        llm_handler: Optional LLM handler for smart decisions
        use_llm: Whether to use LLM advisory

    Returns:
        List of stitch group dicts with smart selection info
    """
    service = SmartStitchService(llm_handler)
    groups = []

    for sample_name, entries in sorted(sample_files.items()):
        if len(entries) < 2:
            groups.append({
                "sample_name": sample_name,
                "files": [f for f, _, _, _ in entries],
                "configs": [c for _, c, _, _ in entries],
                "selected_configs": [c for _, c, _, _ in entries],
                "removed_configs": [],
                "overlaps": [],
                "target_config": entries[0][1] if entries else None,
                "status": "1 config",
                "llm_advice": "",
            })
            continue

        try:
            plan = service.create_stitch_plan(sample_name, entries, use_llm=use_llm)
        except Exception as e:
            groups.append({
                "sample_name": sample_name,
                "files": [f for f, _, _, _ in entries],
                "configs": [c for _, c, _, _ in entries],
                "selected_configs": [c for _, c, _, _ in entries],
                "removed_configs": [],
                "overlaps": [],
                "target_config": entries[0][1] if entries else None,
                "status": "error",
                "llm_advice": f"Failed to create stitch plan: {e}",
            })
            continue

        if plan is None:
            groups.append({
                "sample_name": sample_name,
                "files": [f for f, _, _, _ in entries],
                "configs": [c for _, c, _, _ in entries],
                "selected_configs": [c for _, c, _, _ in entries],
                "removed_configs": [],
                "overlaps": [],
                "target_config": entries[0][1] if entries else None,
                "status": "error",
                "llm_advice": "Failed to create stitch plan",
            })
            continue

        groups.append({
            "sample_name": sample_name,
            "files": [cfg.file_path for cfg in plan.selected_configs],
            "all_files": [f for f, _, _, _ in entries],
            "configs": [cfg.config_id for cfg in plan.selected_configs],
            "all_configs": [c for _, c, _, _ in entries],
            "removed_configs": [
                {"config": cfg.config_id, "reason": reason}
                for cfg, reason in plan.removed_configs
            ],
            "overlaps": plan.overlaps,
            "target_config": plan.target_config.config_id,
            "status": "ready",
            "quality_metrics": [
                {
                    "start_q": q.start_q,
                    "end_q": q.end_q,
                    "n_points": q.n_points_min,
                    "score": q.quality_score,
                    "is_good": q.is_good,
                    "recommendation": q.recommendation,
                }
                for q in plan.quality_metrics
            ],
            "llm_advice": plan.llm_analysis,
            "confidence": plan.confidence,
        })

    return groups
