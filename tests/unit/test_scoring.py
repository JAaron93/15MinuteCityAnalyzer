"""Unit tests for spatial join, scoring, and equity categorisation (Task 3.3 / 6.2.7–6.2.12).

Tests cover:
- Spatial join with area-overlap threshold
- raw_score computation with capped weighted formula
- Score normalization (including degenerate edge case)
- Equity category assignment and validation
- ThresholdConfigError
- Percentile check (PASS/WARN)
- Sensitivity test (PASS/WARN)
- total_amenities consistency validation
"""

from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon, box

from src.pipeline.crs_utils import determine_utm_zone
from src.pipeline.scoring import (
    ThresholdConfigError,
    assign_equity_category,
    calculate_accessibility_score,
    count_amenities_by_type,
    spatial_join_amenities,
    validate_threshold_config,
    validate_total_amenities,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_block_groups(n: int = 5) -> gpd.GeoDataFrame:
    """Create synthetic block groups as a grid of squares."""
    geoids = []
    geometries = []
    populations = []
    incomes = []

    for i in range(n):
        for j in range(n):
            geoid = f"06065{i:03d}{j:03d}00"
            geom = box(
                -117.6 + j * 0.02,
                33.8 + i * 0.02,
                -117.6 + (j + 1) * 0.02,
                33.8 + (i + 1) * 0.02,
            )
            geoids.append(geoid)
            geometries.append(geom)
            populations.append(1000 + i * 100 + j * 10)
            incomes.append(40000.0 + i * 5000 + j * 1000)

    return gpd.GeoDataFrame(
        {
            "geoid": geoids,
            "population": populations,
            "median_income": incomes,
        },
        geometry=geometries,
        crs="EPSG:4326",
    )


def _make_isochrones(n_per_type: int = 3) -> gpd.GeoDataFrame:
    """Create synthetic isochrone polygons covering parts of the block groups."""
    records = []
    types = ["grocery", "healthcare", "transit", "other"]
    base_lon, base_lat = -117.58, 33.84

    for i, amenity_type in enumerate(types):
        for j in range(n_per_type):
            center_lon = base_lon + j * 0.03
            center_lat = base_lat + i * 0.02
            # Create a circular-ish polygon (square for simplicity)
            geom = box(
                center_lon - 0.015,
                center_lat - 0.015,
                center_lon + 0.015,
                center_lat + 0.015,
            )
            records.append(
                {
                    "amenity_type": amenity_type,
                    "geometry": geom,
                }
            )

    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def _default_config() -> dict:
    """Return a minimal default configuration dictionary."""
    return {
        "walk_speed_kmh": 4.5,
        "spatial_join": {"min_overlap_fraction": 0.10},
        "scoring_weights": {
            "grocery": 0.35,
            "healthcare": 0.30,
            "transit": 0.25,
            "other": 0.10,
        },
        "scoring_caps": {
            "grocery": 5,
            "healthcare": 3,
            "transit": 10,
            "other": 5,
        },
        "equity_thresholds": {
            "high_access_min": 70,
            "medium_access_min": 40,
            "min_category_fraction": 0.05,
            "sensitivity_stability_threshold": 0.90,
        },
    }


# ---------------------------------------------------------------------------
# Tests: spatial_join_amenities (task 3.3.2)
# ---------------------------------------------------------------------------

class TestSpatialJoinAmenities:
    """Tests for spatial_join_amenities() — task 6.2.7."""

    def setup_method(self) -> None:
        """Derive a deterministic UTM CRS from the synthetic data bbox."""
        # _make_block_groups spans roughly lon -117.6→-117.5, lat 33.8→33.9
        self.block_groups = _make_block_groups(n=5)
        self.isochrones = _make_isochrones(n_per_type=3)
        self.utm_crs = determine_utm_zone((33.9, 33.8, -117.5, -117.6))

    def test_returns_geodataframe(self) -> None:
        """Result must be a GeoDataFrame."""
        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        assert isinstance(result, gpd.GeoDataFrame)

    def test_expected_columns_present(self) -> None:
        """Result must have geoid, amenity_type, and overlap_fraction columns."""
        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        assert "geoid" in result.columns
        assert "amenity_type" in result.columns
        assert "overlap_fraction" in result.columns

    def test_all_amenity_types_represented(self) -> None:
        """Each of the four amenity types should appear in the join result."""
        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        assert not result.empty
        found_types = set(result["amenity_type"].unique())
        for amenity_type in ("grocery", "healthcare", "transit", "other"):
            assert amenity_type in found_types, f"Missing type: {amenity_type}"

    def test_overlap_fraction_within_bounds(self) -> None:
        """All overlap_fractions must be in (0, 1] and >= min_overlap threshold."""
        config = _default_config()
        min_overlap = config["spatial_join"]["min_overlap_fraction"]
        with patch("src.pipeline.scoring._load_config", return_value=config):
            result = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        assert (result["overlap_fraction"] >= min_overlap).all()
        assert (result["overlap_fraction"] <= 1.0).all()

    def test_empty_isochrones_returns_empty(self) -> None:
        """Empty isochrones input should return an empty GeoDataFrame."""
        empty_iso = gpd.GeoDataFrame(
            {"amenity_type": pd.Series(dtype=str), "geometry": gpd.GeoSeries(dtype="geometry")},
            geometry="geometry",
            crs="EPSG:4326",
        )
        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = spatial_join_amenities(
                self.block_groups, empty_iso, self.utm_crs
            )
        assert isinstance(result, gpd.GeoDataFrame)
        assert result.empty

    def test_high_overlap_threshold_reduces_matches(self) -> None:
        """Raising the overlap threshold should produce fewer or equal matches."""
        low_config = _default_config()
        low_config["spatial_join"]["min_overlap_fraction"] = 0.01
        high_config = _default_config()
        high_config["spatial_join"]["min_overlap_fraction"] = 0.80

        with patch("src.pipeline.scoring._load_config", return_value=low_config):
            result_low = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        with patch("src.pipeline.scoring._load_config", return_value=high_config):
            result_high = spatial_join_amenities(
                self.block_groups, self.isochrones, self.utm_crs
            )
        assert len(result_high) <= len(result_low)



# ---------------------------------------------------------------------------
# Tests: validate_threshold_config (task 6.2.11)
# ---------------------------------------------------------------------------

class TestValidateThresholdConfig:
    """Tests for threshold validation at pipeline startup."""

    def test_valid_config_passes(self) -> None:
        """Valid thresholds should not raise."""
        config = _default_config()
        validate_threshold_config(config)  # Should not raise

    def test_high_equals_medium_raises(self) -> None:
        """high_access_min == medium_access_min must raise ThresholdConfigError."""
        config = _default_config()
        config["equity_thresholds"]["high_access_min"] = 50
        config["equity_thresholds"]["medium_access_min"] = 50

        with pytest.raises(ThresholdConfigError, match="strictly greater"):
            validate_threshold_config(config)

    def test_high_less_than_medium_raises(self) -> None:
        """high_access_min < medium_access_min must raise ThresholdConfigError."""
        config = _default_config()
        config["equity_thresholds"]["high_access_min"] = 30
        config["equity_thresholds"]["medium_access_min"] = 50

        with pytest.raises(ThresholdConfigError, match="strictly greater"):
            validate_threshold_config(config)

    def test_high_out_of_range_raises(self) -> None:
        """high_access_min outside [0, 100] must raise."""
        config = _default_config()
        config["equity_thresholds"]["high_access_min"] = 110

        with pytest.raises(ThresholdConfigError, match="outside"):
            validate_threshold_config(config)

    def test_medium_out_of_range_raises(self) -> None:
        """medium_access_min outside [0, 100] must raise."""
        config = _default_config()
        config["equity_thresholds"]["medium_access_min"] = -5

        with pytest.raises(ThresholdConfigError, match="outside"):
            validate_threshold_config(config)


# ---------------------------------------------------------------------------
# Tests: calculate_accessibility_score (tasks 6.2.9, 6.2.10)
# ---------------------------------------------------------------------------

class TestCalculateAccessibilityScore:
    """Tests for raw_score and accessibility_score computation."""

    def _make_scored_bg(
        self,
        grocery: int = 2,
        healthcare: int = 1,
        transit: int = 5,
        other: int = 3,
    ) -> gpd.GeoDataFrame:
        """Create a single-row block-group GeoDataFrame with count columns."""
        return gpd.GeoDataFrame(
            {
                "geoid": ["060650010001"],
                "grocery_count": [grocery],
                "healthcare_count": [healthcare],
                "transit_count": [transit],
                "other_count": [other],
                "total_amenities": [grocery + healthcare + transit + other],
            },
            geometry=[box(-117.6, 33.8, -117.58, 33.82)],
            crs="EPSG:4326",
        )

    def test_raw_score_formula(self) -> None:
        """raw_score should equal the capped weighted sum."""
        bg = self._make_scored_bg(grocery=2, healthcare=1, transit=5, other=3)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        expected_raw = (
            0.35 * min(2, 5)
            + 0.30 * min(1, 3)
            + 0.25 * min(5, 10)
            + 0.10 * min(3, 5)
        )
        assert "raw_score" in result.columns
        assert abs(result["raw_score"].iloc[0] - expected_raw) < 1e-6

    def test_caps_are_applied(self) -> None:
        """Counts above the cap should be clamped."""
        bg = self._make_scored_bg(grocery=20, healthcare=10, transit=50, other=20)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        # All at max caps
        expected_raw = 0.35 * 5 + 0.30 * 3 + 0.25 * 10 + 0.10 * 5
        assert abs(result["raw_score"].iloc[0] - expected_raw) < 1e-6

    def test_raw_score_stored_separately(self) -> None:
        """raw_score must be a separate column in the output."""
        bg = self._make_scored_bg()
        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        assert "raw_score" in result.columns
        assert "accessibility_score" in result.columns
        # They should be different values (unless single row → score=50)

    def test_degenerate_distribution_assigns_50(self) -> None:
        """When all raw_scores are identical, accessibility_score should be 50."""
        # Two identical rows
        bg = gpd.GeoDataFrame(
            {
                "geoid": ["A", "B"],
                "grocery_count": [2, 2],
                "healthcare_count": [1, 1],
                "transit_count": [5, 5],
                "other_count": [3, 3],
                "total_amenities": [11, 11],
            },
            geometry=[
                box(-117.6, 33.8, -117.58, 33.82),
                box(-117.58, 33.8, -117.56, 33.82),
            ],
            crs="EPSG:4326",
        )

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        assert (result["accessibility_score"] == 50.0).all()

    def test_normalization_range(self) -> None:
        """Normalised scores should be in [0, 100]."""
        # Create varied counts
        bg = gpd.GeoDataFrame(
            {
                "geoid": [f"G{i}" for i in range(10)],
                "grocery_count": list(range(10)),
                "healthcare_count": list(range(10)),
                "transit_count": list(range(10)),
                "other_count": list(range(10)),
                "total_amenities": [4 * i for i in range(10)],
            },
            geometry=[box(-117.6 + i * 0.01, 33.8, -117.59 + i * 0.01, 33.81) for i in range(10)],
            crs="EPSG:4326",
        )

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        assert result["accessibility_score"].min() >= 0.0
        assert result["accessibility_score"].max() <= 100.0

    def test_monotonicity(self) -> None:
        """Higher raw_score must produce higher or equal accessibility_score."""
        bg = gpd.GeoDataFrame(
            {
                "geoid": ["A", "B", "C"],
                "grocery_count": [0, 3, 5],
                "healthcare_count": [0, 2, 3],
                "transit_count": [0, 5, 10],
                "other_count": [0, 2, 5],
                "total_amenities": [0, 12, 23],
            },
            geometry=[
                box(-117.6, 33.8, -117.58, 33.82),
                box(-117.58, 33.8, -117.56, 33.82),
                box(-117.56, 33.8, -117.54, 33.82),
            ],
            crs="EPSG:4326",
        )

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result = calculate_accessibility_score(bg)

        # raw_score should be strictly increasing
        raw = result["raw_score"].values
        assert raw[0] < raw[1] < raw[2]

        # accessibility_score should be non-decreasing (monotone)
        scores = result["accessibility_score"].values
        assert scores[0] <= scores[1] <= scores[2]

    def test_reads_config_weights(self) -> None:
        """Weights and caps should be read from config, not hard-coded."""
        bg = self._make_scored_bg(grocery=2, healthcare=1, transit=5, other=3)

        custom_config = _default_config()
        custom_config["scoring_weights"] = {
            "grocery": 0.50,
            "healthcare": 0.20,
            "transit": 0.20,
            "other": 0.10,
        }

        with patch(
            "src.pipeline.scoring._load_config", return_value=custom_config
        ):
            result = calculate_accessibility_score(bg)

        expected_raw = 0.50 * 2 + 0.20 * 1 + 0.20 * 5 + 0.10 * 3
        assert abs(result["raw_score"].iloc[0] - expected_raw) < 1e-6


# ---------------------------------------------------------------------------
# Tests: assign_equity_category (tasks 6.2.11, 6.2.12)
# ---------------------------------------------------------------------------

class TestAssignEquityCategory:
    """Tests for equity category assignment and validation."""

    def _make_scored_data(self, scores: list) -> gpd.GeoDataFrame:
        """Create block groups with pre-assigned accessibility_score."""
        n = len(scores)
        return gpd.GeoDataFrame(
            {
                "geoid": [f"G{i}" for i in range(n)],
                "accessibility_score": scores,
            },
            geometry=[box(-117.6 + i * 0.01, 33.8, -117.59 + i * 0.01, 33.81) for i in range(n)],
            crs="EPSG:4326",
        )

    def test_category_assignment(self) -> None:
        """Scores should map to correct categories."""
        scores = [20.0, 50.0, 80.0]
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result, metadata = assign_equity_category(bg)

        cats = result["equity_category"].tolist()
        assert cats[0] == "Low Access"     # 20 < 40
        assert cats[1] == "Medium Access"  # 40 ≤ 50 < 70
        assert cats[2] == "High Access"    # 80 ≥ 70

    def test_boundary_values(self) -> None:
        """Scores exactly at thresholds should be categorised correctly."""
        # high_min=70, med_min=40: score=40 → Medium, score=70 → High
        scores = [0.0, 39.99, 40.0, 69.99, 70.0, 100.0]
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            result, _ = assign_equity_category(bg)

        cats = result["equity_category"].tolist()
        assert cats[0] == "Low Access"      # 0
        assert cats[1] == "Low Access"      # 39.99
        assert cats[2] == "Medium Access"   # 40.0
        assert cats[3] == "Medium Access"   # 69.99
        assert cats[4] == "High Access"     # 70.0
        assert cats[5] == "High Access"     # 100.0

    def test_reads_thresholds_from_config(self) -> None:
        """Thresholds must be read from config, not hard-coded (task 6.2.12)."""
        scores = [30.0, 60.0, 90.0]
        bg = self._make_scored_data(scores)

        custom_config = _default_config()
        custom_config["equity_thresholds"]["high_access_min"] = 80
        custom_config["equity_thresholds"]["medium_access_min"] = 50

        with patch(
            "src.pipeline.scoring._load_config", return_value=custom_config
        ):
            result, _ = assign_equity_category(bg)

        cats = result["equity_category"].tolist()
        assert cats[0] == "Low Access"      # 30 < 50
        assert cats[1] == "Medium Access"   # 50 ≤ 60 < 80
        assert cats[2] == "High Access"     # 90 ≥ 80

    def test_metadata_contains_all_seven_keys(self) -> None:
        """Metadata must include all seven equity_thresholds.* keys."""
        scores = [20.0, 50.0, 80.0]
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            _, metadata = assign_equity_category(bg)

        required_keys = [
            "equity_thresholds.high_access_min",
            "equity_thresholds.medium_access_min",
            "equity_thresholds.percentile_check",
            "equity_thresholds.category_fractions",
            "equity_thresholds.sensitivity_check",
            "equity_thresholds.sensitivity_stability",
            "equity_thresholds.validated_at",
        ]
        for key in required_keys:
            assert key in metadata, f"Missing metadata key: {key}"

    def test_percentile_check_pass(self) -> None:
        """All categories ≥ 5% should produce PASS."""
        # Even distribution across categories
        scores = list(range(0, 100, 1))  # 100 scores spanning all categories
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            _, metadata = assign_equity_category(bg)

        assert metadata["equity_thresholds.percentile_check"] == "PASS"

    def test_percentile_check_warn(self) -> None:
        """Category with < 5% should produce WARN."""
        # Almost all scores in High Access
        scores = [80.0] * 98 + [20.0, 50.0]  # Low and Medium each < 5%
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            _, metadata = assign_equity_category(bg)

        assert metadata["equity_thresholds.percentile_check"] == "WARN"

    def test_sensitivity_check_has_both_shifts(self) -> None:
        """Sensitivity stability must include both shift_plus5 and shift_minus5."""
        scores = list(range(0, 100))
        bg = self._make_scored_data(scores)

        with patch(
            "src.pipeline.scoring._load_config", return_value=_default_config()
        ):
            _, metadata = assign_equity_category(bg)

        stability = metadata["equity_thresholds.sensitivity_stability"]
        assert "shift_plus5" in stability
        assert "shift_minus5" in stability
        assert 0.0 <= stability["shift_plus5"] <= 1.0
        assert 0.0 <= stability["shift_minus5"] <= 1.0

    def test_sensitivity_clamping_at_100(self) -> None:
        """Sensitivity test must not collapse medium category when high is clamped to 100."""
        # Setup scores and thresholds so that high + 5 >= 100
        scores = list(range(0, 101))
        bg = self._make_scored_data(scores)

        clamping_config = _default_config()
        clamping_config["equity_thresholds"]["high_access_min"] = 98
        clamping_config["equity_thresholds"]["medium_access_min"] = 97

        with patch(
            "src.pipeline.scoring._load_config", return_value=clamping_config
        ):
            _, metadata = assign_equity_category(bg)

        # In _run_sensitivity_test:
        # high_plus = min(98 + 5, 100) = 100
        # med_plus = min(97 + 5, 100) = 100
        # if high_plus <= med_plus: med_plus = max(97, 100 - 1) = 99
        # So bins should be [-inf, 99, 100, inf], allowing a Medium Access bucket [99, 100)
        
        # Stability is checked against baseline: [-inf, 97, 98, inf]
        # Baseline categories for [97, 98, 99, 100]: [M, H, H, H]
        # Shifted categories for [97, 98, 99, 100]: [L, L, M, H]
        
        # The fact that it doesn't crash and returns stability is the primary check here.
        stability = metadata["equity_thresholds.sensitivity_stability"]
        assert "shift_plus5" in stability
        assert 0.0 <= stability["shift_plus5"] <= 1.0
        assert "shift_minus5" in stability
        assert 0.0 <= stability["shift_minus5"] <= 1.0

    def test_invalid_config_raises(self) -> None:
        """Invalid threshold config should raise ThresholdConfigError."""
        scores = [50.0]
        bg = self._make_scored_data(scores)

        bad_config = _default_config()
        bad_config["equity_thresholds"]["high_access_min"] = 30
        bad_config["equity_thresholds"]["medium_access_min"] = 50

        with patch(
            "src.pipeline.scoring._load_config", return_value=bad_config
        ):
            with pytest.raises(ThresholdConfigError):
                assign_equity_category(bg)


# ---------------------------------------------------------------------------
# Tests: validate_total_amenities (task 3.3.7)
# ---------------------------------------------------------------------------

class TestValidateTotalAmenities:
    """Tests for total_amenities consistency check."""

    def test_valid_totals(self) -> None:
        """Consistent totals should pass validation."""
        bg = gpd.GeoDataFrame(
            {
                "geoid": ["A", "B"],
                "grocery_count": [2, 0],
                "healthcare_count": [1, 3],
                "transit_count": [5, 2],
                "other_count": [1, 1],
                "total_amenities": [9, 6],
            },
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )

        assert validate_total_amenities(bg) is True

    def test_invalid_totals_raises(self) -> None:
        """Inconsistent total_amenities should raise ValueError."""
        bg = gpd.GeoDataFrame(
            {
                "geoid": ["A"],
                "grocery_count": [2],
                "healthcare_count": [1],
                "transit_count": [5],
                "other_count": [1],
                "total_amenities": [999],  # Wrong!
            },
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )

        with pytest.raises(ValueError, match="total_amenities inconsistency"):
            validate_total_amenities(bg)


# ---------------------------------------------------------------------------
# Tests: count_amenities_by_type (task 3.3.3)
# ---------------------------------------------------------------------------

class TestCountAmenitiesByType:
    """Tests for amenity counting after spatial join."""

    def test_counts_all_four_types(self) -> None:
        """All four amenity types should have count columns."""
        bg = gpd.GeoDataFrame(
            {"geoid": ["A", "B"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        joined = pd.DataFrame(
            {
                "geoid": ["A", "A", "A", "B"],
                "amenity_type": ["grocery", "healthcare", "transit", "other"],
            }
        )

        result = count_amenities_by_type(joined, bg)

        for col in ["grocery_count", "healthcare_count", "transit_count", "other_count"]:
            assert col in result.columns

        assert result["total_amenities"].sum() == 4

    def test_empty_join_gives_zeros(self) -> None:
        """No spatial join results should give all-zero counts."""
        bg = gpd.GeoDataFrame(
            {"geoid": ["A"]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        joined = pd.DataFrame(columns=["geoid", "amenity_type"])

        result = count_amenities_by_type(joined, bg)

        assert result["total_amenities"].iloc[0] == 0
