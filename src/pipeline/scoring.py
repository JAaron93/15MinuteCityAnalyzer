"""Spatial join, accessibility scoring, and equity categorisation.

Implements the core analysis logic: joining block groups with isochrones using
an area-overlap threshold, counting amenities per type, computing the capped
weighted raw score, normalising to 0–100, and assigning equity categories with
mandatory validation checks.

References:
    - FR-1.2.2: Area-overlap spatial join
    - FR-1.2.3: Accessibility score (capped weighted formula)
    - FR-1.2.4: Equity category assignment and validation
    - FR-1.3.4: Output fields
    - DR-3.2.1: Output schema (incl. ``raw_score``)
    - DR-3.3.3: ``total_amenities`` consistency
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pyproj import CRS

from src.pipeline.crs_utils import transform_to_utm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ThresholdConfigError(Exception):
    """Raised when equity threshold configuration is invalid."""


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: str = "pipeline_config.yaml") -> Dict[str, Any]:
    """Load pipeline configuration from YAML."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError as e:
        msg = f"_load_config: Configuration file '{config_path}' not found."
        logger.error(msg)
        raise RuntimeError(msg) from e
    except yaml.YAMLError as e:
        msg = f"_load_config: Error parsing YAML in '{config_path}': {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e


def validate_threshold_config(config: Dict[str, Any]) -> None:
    """Validate equity threshold configuration at pipeline startup.

    Enforces FR-1.2.4 threshold bounds:
    - Both ``high_access_min`` and ``medium_access_min`` must be in [0, 100].
    - ``high_access_min`` must be strictly greater than ``medium_access_min``.

    Args:
        config: Pipeline configuration dictionary.

    Raises:
        ThresholdConfigError: If any constraint is violated.
    """
    thresholds = config.get("equity_thresholds", {})
    high_min = thresholds.get("high_access_min", 70)
    med_min = thresholds.get("medium_access_min", 40)

    if not (0 <= high_min <= 100):
        raise ThresholdConfigError(
            f"equity_thresholds.high_access_min={high_min} is outside [0, 100]."
        )
    if not (0 <= med_min <= 100):
        raise ThresholdConfigError(
            f"equity_thresholds.medium_access_min={med_min} is outside [0, 100]."
        )
    if high_min <= med_min:
        raise ThresholdConfigError(
            f"equity_thresholds.high_access_min ({high_min}) must be strictly "
            f"greater than equity_thresholds.medium_access_min ({med_min})."
        )

    logger.info(
        f"Threshold config validated: high_access_min={high_min}, "
        f"medium_access_min={med_min}"
    )


# ---------------------------------------------------------------------------
# Spatial join
# ---------------------------------------------------------------------------

def spatial_join_amenities(
    block_groups: gpd.GeoDataFrame,
    isochrones: gpd.GeoDataFrame,
    utm_crs: CRS,
    config_path: str = "pipeline_config.yaml",
) -> gpd.GeoDataFrame:
    """Spatial join between block groups and isochrones using area-overlap.

    A block group is considered to have access to an amenity only when::

        area(intersection(block_group, isochrone))
            ≥ MIN_OVERLAP_FRACTION × area(block_group)

    All area calculations are performed in the local UTM projection to avoid
    geographic-coordinate distortion (FR-1.2.2).

    Args:
        block_groups: Census block groups (WGS84).
        isochrones: Isochrone polygons with ``amenity_type`` column (WGS84).
        utm_crs: Local UTM CRS for area calculations.
        config_path: Path to the pipeline configuration file.

    Returns:
        GeoDataFrame of block-group–isochrone pairs that meet the overlap
        threshold, with columns ``[geoid, amenity_type, overlap_fraction]``.
    """
    config = _load_config(config_path)
    min_overlap = config.get("spatial_join", {}).get("min_overlap_fraction", 0.10)

    logger.info(
        f"Performing spatial join with min_overlap_fraction={min_overlap} "
        f"({len(block_groups)} block groups × {len(isochrones)} isochrones)"
    )

    if block_groups.empty or isochrones.empty:
        logger.warning("Empty input to spatial join; returning empty result.")
        return gpd.GeoDataFrame(
            columns=["geoid", "amenity_type", "overlap_fraction"]
        )

    # Project to UTM for accurate area calculations
    bg_utm = transform_to_utm(block_groups.copy(), utm_crs)
    iso_utm = transform_to_utm(isochrones.copy(), utm_crs)

    # Ensure spatial index exists (GeoPandas uses it internally for sjoin)
    # by accessing .sindex
    _ = bg_utm.sindex
    _ = iso_utm.sindex

    # Spatial join — inner join on 'intersects' predicate
    joined = gpd.sjoin(
        bg_utm,
        iso_utm[["geometry", "amenity_type"]],
        how="inner",
        predicate="intersects",
    )

    if joined.empty:
        logger.warning(
            "Spatial join produced zero intersections. Check CRS alignment "
            "and that isochrones overlap with block groups."
        )
        return gpd.GeoDataFrame(
            columns=["geoid", "amenity_type", "overlap_fraction"]
        )

    # Compute overlap fraction per pair in a vectorized manner
    # We align the isochrone geometries with the joined block groups
    iso_geoms = iso_utm.geometry.loc[joined["index_right"]]
    iso_geoms.index = joined.index  # Align indices for vectorized operation
    
    # Calculate intersection areas (vectorized)
    intersection_areas = joined.geometry.intersection(iso_geoms).area
    block_areas = joined.geometry.area
    
    # Guard against degenerate geometries with zero area
    if (block_areas == 0).any():
        logger.warning("Some block groups have zero area; excluding from overlap calculation.")
        valid_mask = block_areas > 0
        joined = joined[valid_mask]
        intersection_areas = intersection_areas[valid_mask]
        block_areas = block_areas[valid_mask]

    # Calculate overlap fractions
    overlap_fractions = intersection_areas / block_areas
    
    # Filter by threshold
    mask = overlap_fractions >= min_overlap
    
    result_df = gpd.GeoDataFrame({
        "geoid": joined["geoid"].values[mask],
        "amenity_type": joined["amenity_type"].values[mask],
        "overlap_fraction": overlap_fractions.values[mask] if hasattr(overlap_fractions, "values") else overlap_fractions[mask],
    }, geometry=joined.geometry.values[mask], crs=joined.crs)

    logger.info(
        f"Spatial join complete: {len(result_df)} block-group–amenity pairs "
        f"met the {min_overlap} overlap threshold."
    )

    return result_df


# ---------------------------------------------------------------------------
# Amenity counting
# ---------------------------------------------------------------------------

def count_amenities_by_type(
    joined: pd.DataFrame,
    block_groups: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Count accessible amenities per block group across all four types.

    Aggregates the spatial-join results to produce per-block-group counts for
    ``grocery``, ``healthcare``, ``transit``, and ``other``.

    Args:
        joined: Output of :func:`spatial_join_amenities`.
        block_groups: Original Census block groups with ``geoid`` column.

    Returns:
        The block-groups GeoDataFrame augmented with ``grocery_count``,
        ``healthcare_count``, ``transit_count``, ``other_count``, and
        ``total_amenities`` columns.
    """
    bg = block_groups.copy()

    # Initialise count columns to zero
    for col in ["grocery_count", "healthcare_count", "transit_count", "other_count"]:
        bg[col] = 0

    if joined.empty:
        bg["total_amenities"] = 0
        return bg

    # Pivot: count unique amenities per geoid × type
    counts = (
        joined.groupby(["geoid", "amenity_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    type_to_col = {
        "grocery": "grocery_count",
        "healthcare": "healthcare_count",
        "transit": "transit_count",
        "other": "other_count",
    }

    for amenity_type, col_name in type_to_col.items():
        if amenity_type in counts.columns:
            mapping = counts.set_index("geoid")[amenity_type]
            bg[col_name] = bg["geoid"].map(mapping).fillna(0).astype(int)

    bg["total_amenities"] = (
        bg["grocery_count"]
        + bg["healthcare_count"]
        + bg["transit_count"]
        + bg["other_count"]
    )

    logger.info(
        f"Amenity counts: grocery={bg['grocery_count'].sum()}, "
        f"healthcare={bg['healthcare_count'].sum()}, "
        f"transit={bg['transit_count'].sum()}, "
        f"other={bg['other_count'].sum()}, "
        f"total={bg['total_amenities'].sum()}"
    )

    return bg


# ---------------------------------------------------------------------------
# Accessibility scoring
# ---------------------------------------------------------------------------

def calculate_accessibility_score(
    block_groups: gpd.GeoDataFrame,
    config_path: str = "pipeline_config.yaml",
) -> gpd.GeoDataFrame:
    """Compute raw_score and accessibility_score for each block group.

    Implements the canonical capped weighted formula (FR-1.2.3)::

        raw_score = (
            w_g × min(grocery_count,    c_g) +
            w_h × min(healthcare_count, c_h) +
            w_t × min(transit_count,    c_t) +
            w_o × min(other_count,      c_o)
        )

        accessibility_score = normalize(raw_score)

    Where ``normalize(x) = 100 × (x − city_min) / (city_max − city_min)``.

    Edge case: when ``city_max == city_min``, all scores are set to 50 and a
    WARNING is logged.

    Args:
        block_groups: GeoDataFrame with amenity count columns.
        config_path: Path to the pipeline configuration file.

    Returns:
        The GeoDataFrame with ``raw_score`` and ``accessibility_score`` added.
    """
    config = _load_config(config_path)

    weights = config.get("scoring_weights", {})
    caps = config.get("scoring_caps", {})

    w_g = weights.get("grocery", 0.35)
    w_h = weights.get("healthcare", 0.30)
    w_t = weights.get("transit", 0.25)
    w_o = weights.get("other", 0.10)

    c_g = caps.get("grocery", 5)
    c_h = caps.get("healthcare", 3)
    c_t = caps.get("transit", 10)
    c_o = caps.get("other", 5)

    bg = block_groups.copy()

    # Compute raw_score (capped weighted sum)
    bg["raw_score"] = (
        w_g * np.minimum(bg["grocery_count"], c_g)
        + w_h * np.minimum(bg["healthcare_count"], c_h)
        + w_t * np.minimum(bg["transit_count"], c_t)
        + w_o * np.minimum(bg["other_count"], c_o)
    ).astype(float)

    # Normalise to 0–100
    city_min = bg["raw_score"].min()
    city_max = bg["raw_score"].max()

    if city_max == city_min:
        logger.warning(
            "All block groups have identical raw_score "
            f"({city_min:.4f}). Setting accessibility_score=50 for all "
            "(min-max normalization skipped due to degenerate distribution)."
        )
        bg["accessibility_score"] = 50.0
    else:
        bg["accessibility_score"] = (
            100.0 * (bg["raw_score"] - city_min) / (city_max - city_min)
        )

    logger.info(
        f"Accessibility scores computed: "
        f"raw_score range=[{city_min:.2f}, {city_max:.2f}], "
        f"accessibility_score range="
        f"[{bg['accessibility_score'].min():.1f}, "
        f"{bg['accessibility_score'].max():.1f}]"
    )

    return bg


# ---------------------------------------------------------------------------
# Equity category assignment
# ---------------------------------------------------------------------------

def assign_equity_category(
    block_groups: gpd.GeoDataFrame,
    config_path: str = "pipeline_config.yaml",
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """Assign equity categories with mandatory validation (FR-1.2.4).

    Steps:
    1. Validate threshold bounds (raises ``ThresholdConfigError`` on failure).
    2. Assign categories: High Access / Medium Access / Low Access.
    3. Run mandatory percentile check (≥5 % per category).
    4. Run mandatory ±5-point sensitivity test (≥90 % stability).
    5. Collect all seven ``equity_thresholds.*`` metadata fields.

    Args:
        block_groups: GeoDataFrame with ``accessibility_score`` column.
        config_path: Path to the pipeline configuration file.

    Returns:
        Tuple of:
        - GeoDataFrame with ``equity_category`` column added.
        - Dictionary of equity threshold metadata for GeoParquet output.

    Raises:
        ThresholdConfigError: If threshold bounds are invalid.
    """
    config = _load_config(config_path)

    # 1. Validate threshold config
    validate_threshold_config(config)

    thresholds = config.get("equity_thresholds", {})
    high_min: float = thresholds.get("high_access_min", 70)
    med_min: float = thresholds.get("medium_access_min", 40)
    min_cat_fraction: float = thresholds.get("min_category_fraction", 0.05)
    sensitivity_threshold: float = thresholds.get(
        "sensitivity_stability_threshold", 0.90
    )

    bg = block_groups.copy()

    # 2. Assign categories
    bg["equity_category"] = _categorise(bg["accessibility_score"], high_min, med_min)

    # 3. Percentile check
    category_fractions = _compute_category_fractions(bg)
    percentile_check = "PASS"
    for category, fraction in category_fractions.items():
        if fraction < min_cat_fraction:
            logger.warning(
                f"Percentile check: category '{category}' contains only "
                f"{fraction:.1%} of block groups (minimum {min_cat_fraction:.0%})."
            )
            percentile_check = "WARN"

    if percentile_check == "PASS":
        logger.info("Percentile check: PASS — all categories ≥ minimum fraction.")

    # 4. Sensitivity test (±5 points)
    sensitivity_stability = _run_sensitivity_test(
        bg["accessibility_score"], high_min, med_min
    )
    sensitivity_check = "PASS"
    for shift_label, stability in sensitivity_stability.items():
        if stability < sensitivity_threshold:
            logger.warning(
                f"Sensitivity check ({shift_label}): stability={stability:.1%} "
                f"< threshold={sensitivity_threshold:.0%}."
            )
            sensitivity_check = "WARN"

    if sensitivity_check == "PASS":
        logger.info("Sensitivity check: PASS — both ±5 shifts above threshold.")

    # 5. Assemble metadata
    validated_at = datetime.now(timezone.utc).isoformat()

    metadata: Dict[str, Any] = {
        "equity_thresholds.high_access_min": high_min,
        "equity_thresholds.medium_access_min": med_min,
        "equity_thresholds.percentile_check": percentile_check,
        "equity_thresholds.category_fractions": category_fractions,
        "equity_thresholds.sensitivity_check": sensitivity_check,
        "equity_thresholds.sensitivity_stability": sensitivity_stability,
        "equity_thresholds.validated_at": validated_at,
    }

    logger.info(f"Equity thresholds validated at {validated_at}: {metadata}")

    return bg, metadata


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _categorise(
    scores: pd.Series,
    high_min: float,
    med_min: float,
) -> pd.Series:
    """Map accessibility scores to equity categories."""
    return pd.cut(
        scores,
        bins=[-np.inf, med_min, high_min, np.inf],
        labels=["Low Access", "Medium Access", "High Access"],
        right=False,
    ).astype(str)


def _compute_category_fractions(bg: gpd.GeoDataFrame) -> Dict[str, float]:
    """Compute the fraction of block groups in each equity category."""
    total = len(bg)
    if total == 0:
        return {"High Access": 0.0, "Medium Access": 0.0, "Low Access": 0.0}

    counts = bg["equity_category"].value_counts()
    return {
        "High Access": counts.get("High Access", 0) / total,
        "Medium Access": counts.get("Medium Access", 0) / total,
        "Low Access": counts.get("Low Access", 0) / total,
    }


def _run_sensitivity_test(
    scores: pd.Series,
    high_min: float,
    med_min: float,
) -> Dict[str, float]:
    """Run ±5-point sensitivity test and return stability fractions.

    Stability is the fraction of block groups whose category is unchanged
    when thresholds are shifted by ±5 points (clamped to [0, 100]).
    """
    baseline = _categorise(scores, high_min, med_min)

    # +5 shift
    high_plus = min(high_min + 5, 100)
    med_plus = min(med_min + 5, 100)
    
    # Ensure high > med after clamping (DR-3.3.4)
    if high_plus <= med_plus:
        med_plus = max(med_min, high_plus - 1)
        
    shifted_plus = _categorise(scores, high_plus, med_plus)
    stability_plus = (baseline == shifted_plus).mean()

    # -5 shift
    high_minus = max(high_min - 5, 0)
    med_minus = max(med_min - 5, 0)
    
    # Ensure high > med after clamping (DR-3.3.4)
    if high_minus <= med_minus:
        high_minus = min(high_plus, med_minus + 1)
        
    shifted_minus = _categorise(scores, high_minus, med_minus)
    stability_minus = (baseline == shifted_minus).mean()

    return {
        "shift_plus5": float(stability_plus),
        "shift_minus5": float(stability_minus),
    }


def validate_total_amenities(bg: gpd.GeoDataFrame) -> bool:
    """Validate that total_amenities equals the sum of individual counts.

    Args:
        bg: GeoDataFrame with amenity count and total_amenities columns.

    Returns:
        ``True`` if all records pass the check.

    Raises:
        ValueError: If any record fails the consistency check (DR-3.3.3).
    """
    expected = (
        bg["grocery_count"]
        + bg["healthcare_count"]
        + bg["transit_count"]
        + bg["other_count"]
    )
    mismatches = bg[bg["total_amenities"] != expected]

    if not mismatches.empty:
        sample = mismatches.head(5)
        msg = (
            f"total_amenities inconsistency in {len(mismatches)} records. "
            f"Sample geoids: {sample['geoid'].tolist()}"
        )
        logger.error(msg)
        raise ValueError(msg)

    logger.info("total_amenities validation passed for all records.")
    return True
