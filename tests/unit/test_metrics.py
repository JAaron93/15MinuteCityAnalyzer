import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from src.dashboard.metrics import calculate_equity_metrics


def test_calculate_equity_metrics_empty():
    gdf = gpd.GeoDataFrame()
    metrics = calculate_equity_metrics(gdf)
    assert metrics["total_block_groups"] == 0
    assert metrics["total_population"] == 0
    assert metrics["avg_score_by_quartile"] == {}


def test_calculate_equity_metrics_valid():
    df = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 200, 300, 400],
            "median_income": [30000, 40000, 50000, 60000],
            "accessibility_score": [20, 30, 70, 80],
            "equity_category": [
                "Low Access",
                "Low Access",
                "High Access",
                "High Access",
            ],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    metrics = calculate_equity_metrics(gdf, income_threshold=45000)

    assert metrics["total_block_groups"] == 4
    assert metrics["total_population"] == 1000
    # Low access population: 100 + 200 = 300
    assert metrics["pct_pop_low_access"] == 30.0

    # Low income population: 30000, 40000 -> pop 100, 200 -> total 300
    # Low income AND low access: 100, 200 -> total 300
    # pct = 300 / 300 * 100 = 100
    assert metrics["pct_low_income_low_access"] == 100.0

    assert len(metrics["avg_score_by_quartile"]) == 4
    # Check that all expected quartile keys exist
    expected_quartiles = ["Q1 (Low)", "Q2", "Q3", "Q4 (High)"]
    for quartile in expected_quartiles:
        assert quartile in metrics["avg_score_by_quartile"]
        # Check that the value is numeric and within expected bounds (0-100 for accessibility scores)  # noqa: E501
        score = metrics["avg_score_by_quartile"][quartile]
        assert isinstance(
            score, (int, float)
        ), f"Score for {quartile} should be numeric"
        assert (
            0 <= score <= 100
        ), f"Score for {quartile} should be between 0 and 100, got {score}"


def test_calculate_equity_metrics_missing_cols():
    df = pd.DataFrame({"geoid": ["1"]})
    gdf = gpd.GeoDataFrame(df)
    with pytest.raises(ValueError, match="Missing required columns"):
        calculate_equity_metrics(gdf)


def test_calculate_equity_metrics_insufficient_quartile_data():
    # Test that we don't crash with fewer than 4 records for quartiles
    df = pd.DataFrame(
        {
            "geoid": ["1", "2"],
            "population": [100, 200],
            "median_income": [30000, 40000],
            "accessibility_score": [20, 30],
            "equity_category": ["Low Access", "Low Access"],
            "geometry": [Point(0, 0) for _ in range(2)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    metrics = calculate_equity_metrics(gdf)
    assert metrics["avg_score_by_quartile"] == {}


def test_negative_zero_values(caplog):
    """Test that negative population raises ValueError and zero values are handled."""
    # Case 1: Negative population should raise ValueError
    df_neg = pd.DataFrame(
        {
            "geoid": ["1"],
            "population": [-50],
            "median_income": [50000],
            "accessibility_score": [50],
            "equity_category": ["High Access"],
            "geometry": [Point(0, 0)],
        }
    )
    gdf_neg = gpd.GeoDataFrame(df_neg, crs="EPSG:4326")
    with pytest.raises(ValueError, match="Population values cannot be negative"):
        calculate_equity_metrics(gdf_neg)

    # Case 2: Zero values and negative income/scores should not raise (but should be handled)  # noqa: E501
    df_zero = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 0, 0, 300],
            "median_income": [
                30000,
                0,
                -10000,
                50000,
            ],  # zero and negative income (should warn)
            "accessibility_score": [
                20,
                -5,
                0,
                80,
            ],  # negative and zero score (should warn)
            "equity_category": [
                "Low Access",
                "Low Access",
                "High Access",
                "High Access",
            ],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf_zero = gpd.GeoDataFrame(df_zero, crs="EPSG:4326")

    # This should succeed despite negative income/scores (triggering warnings)
    import logging

    with caplog.at_level(logging.WARNING):
        metrics = calculate_equity_metrics(gdf_zero)

    assert "Found negative median income values" in caplog.text
    assert "Found negative accessibility scores" in caplog.text

    # Total population should sum non-negative values
    assert metrics["total_population"] == 400  # 100 + 0 + 0 + 300

    # Low access population (first two rows): 100 + 0 = 100
    assert metrics["pct_pop_low_access"] == (100 / 400 * 100)

    # Low income: income < 50000 (first three rows: 30000, 0, -10000)
    # Low income population: 100 + 0 + 0 = 100
    # Low income AND low access: first two rows qualify -> population 100 + 0 = 100
    # Expected pct = 100 / 100 * 100 = 100
    assert metrics["pct_low_income_low_access"] == 100.0


def test_null_handling_population_raises_error():
    """Test that missing population raises a ValueError."""
    df = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 200, None, 400],
            "median_income": [30000, 40000, 50000, 60000],
            "accessibility_score": [20, 30, 40, 80],
            "equity_category": [
                "Low Access",
                "Low Access",
                "High Access",
                "High Access",
            ],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    with pytest.raises(ValueError, match="Found 1 missing population values"):
        calculate_equity_metrics(gdf, income_threshold=45000)


def test_null_handling_warnings(caplog):
    """Test handling of None/null values in non-population columns."""
    df = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 200, 300, 400],
            "median_income": [30000, None, 50000, 60000],
            "accessibility_score": [20, 30, None, 80],
            "equity_category": ["Low Access", "Low Access", "High Access", None],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    import logging

    with caplog.at_level(logging.WARNING):
        metrics = calculate_equity_metrics(gdf, income_threshold=45000)

    assert "Found 1 missing median_income values" in caplog.text
    assert "Found 1 missing accessibility_score values" in caplog.text

    # Check that calculations worked despite nulls
    assert metrics["total_block_groups"] == 4
    assert metrics["total_population"] == 1000

    # For pct_pop_low_access: Low Access rows are 0,1 (row 2 is High Access, row 3 has None equity_category)  # noqa: E501
    # Population for low access: 100 + 200 = 300
    # Expected: 300/1000*100 = 30.0
    assert abs(metrics["pct_pop_low_access"] - 30.0) < 0.001

    # For pct_low_income_low_access:
    # Low income: income < 45000 -> row 0 (30000) (row 1 has None, which is False)
    # Low income population: 100
    # Low income AND low access: row 0 -> population 100
    # Pct = 100/100*100 = 100.0
    assert metrics["pct_low_income_low_access"] == 100.0


def test_exactly_four_quartiles():
    """Test with exactly four records to verify quartile computations return four entries."""  # noqa: E501
    df = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 200, 300, 400],
            "median_income": [
                20000,
                40000,
                60000,
                80000,
            ],  # Clearly distributable into 4 quartiles
            "accessibility_score": [10, 30, 70, 90],
            "equity_category": [
                "Low Access",
                "Low Access",
                "High Access",
                "High Access",
            ],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    metrics = calculate_equity_metrics(gdf)

    # With exactly 4 records and all incomes > 0, we should get 4 quartiles
    assert len(metrics["avg_score_by_quartile"]) == 4

    # Each quartile should have exactly one record
    for quartile, avg_score in metrics["avg_score_by_quartile"].items():
        assert quartile in ["Q1 (Low)", "Q2", "Q3", "Q4 (High)"]
        # Since each quartile has exactly one record, average equals that record's score
        assert avg_score in [10, 30, 70, 90]


def test_income_threshold_variants():
    """Test different income_threshold values and the default behavior."""
    df = pd.DataFrame(
        {
            "geoid": ["1", "2", "3", "4"],
            "population": [100, 200, 300, 400],
            "median_income": [30000, 40000, 50000, 60000],
            "accessibility_score": [20, 30, 70, 80],
            "equity_category": [
                "Low Access",
                "Low Access",
                "High Access",
                "High Access",
            ],
            "geometry": [Point(0, 0) for _ in range(4)],
        }
    )
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    # Test with income_threshold=45000 (as in original test)
    metrics_45k = calculate_equity_metrics(gdf, income_threshold=45000)
    # Low income: < 45000 -> rows 1,2 (30k, 40k) -> population 100+200=300
    # Low income AND low access: rows 1,2 are both Low Access -> population 300
    # Low income population: 300
    # pct = 300/300 * 100 = 100
    assert metrics_45k["pct_low_income_low_access"] == 100.0

    # Test with income_threshold=25000
    metrics_25k = calculate_equity_metrics(gdf, income_threshold=25000)
    # Low income: < 25000 -> none -> population 0
    # When low income population is 0, pct should be 0 (avoiding division by zero)
    assert metrics_25k["pct_low_income_low_access"] == 0.0

    # Test with income_threshold=65000 (above all incomes)
    metrics_65k = calculate_equity_metrics(gdf, income_threshold=65000)
    # Low income: < 65000 -> all rows -> population 1000
    # Low income AND low access: first two rows -> population 300
    # pct = 300/1000 * 100 = 30
    assert metrics_65k["pct_low_income_low_access"] == 30.0

    # Test with default income_threshold (should be 50000.0 per function definition)
    metrics_default = calculate_equity_metrics(gdf)
    # Low income: < 50000 -> rows 1,2 (30k, 40k) -> population 300
    # Low income AND low access: rows 1,2 are both Low Access -> population 300
    # Low income population: 300
    # pct = 300/300 * 100 = 100
    assert metrics_default["pct_low_income_low_access"] == 100.0
