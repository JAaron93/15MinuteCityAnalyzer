import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from src.dashboard.filters import apply_all_filters, MAX_INCOME_THRESHOLD

@pytest.fixture
def sample_gdf():
    df = pd.DataFrame({
        "geoid": ["1", "2", "3"],
        "median_income": [30000, 60000, 150000],
        "accessibility_score": [20, 50, 80],
        "geometry": [Point(0, 0) for _ in range(3)]
    })
    return gpd.GeoDataFrame(df, crs="EPSG:4326")

def test_apply_all_filters_income(sample_gdf):
    # Test filtering by income
    filtered = apply_all_filters(sample_gdf, income_threshold=50000, score_range=(0, 100))
    assert len(filtered) == 1
    assert filtered.iloc[0]["geoid"] == "1"

def test_apply_all_filters_score(sample_gdf):
    # Test filtering by score
    filtered = apply_all_filters(sample_gdf, income_threshold=MAX_INCOME_THRESHOLD, score_range=(40, 90))
    assert len(filtered) == 2
    assert set(filtered["geoid"]) == {"2", "3"}

def test_apply_all_filters_income_out_of_range(sample_gdf):
    # Test income out of range
    with pytest.raises(ValueError, match="income_threshold must be between 0.0 and"):
        apply_all_filters(sample_gdf, income_threshold=-1, score_range=(0, 100))
    with pytest.raises(ValueError, match="income_threshold must be between 0.0 and"):
        apply_all_filters(sample_gdf, income_threshold=MAX_INCOME_THRESHOLD + 1, score_range=(0, 100))

def test_apply_all_filters_score_range_invalid_order(sample_gdf):
    # Test score range invalid order (min > max)
    with pytest.raises(ValueError, match="score_range min_score .* must be <= max_score"):
        apply_all_filters(sample_gdf, income_threshold=50000, score_range=(90, 40))

def test_apply_all_filters_missing_cols():
    df = pd.DataFrame({"geoid": ["1"]})
    gdf = gpd.GeoDataFrame(df)
    with pytest.raises(ValueError, match="Missing 'median_income' column in data."):
        apply_all_filters(gdf, income_threshold=50000, score_range=(0, 100))

def test_apply_all_filters_invalid_types(sample_gdf):
    # Invalid income_threshold type
    with pytest.raises(TypeError, match="income_threshold must be numeric."):
        apply_all_filters(sample_gdf, income_threshold="invalid", score_range=(0, 100))
    
    # Invalid score_range type/length
    with pytest.raises(ValueError, match="score_range must be a tuple or list of length 2."):
        apply_all_filters(sample_gdf, income_threshold=50000, score_range=(0,))
    
    # Non-numeric score_range values
    with pytest.raises(TypeError, match="score_range values must be numeric."):
        apply_all_filters(sample_gdf, income_threshold=50000, score_range=("a", "b"))

def test_apply_all_filters_empty_gdf():
    df = pd.DataFrame(columns=["geoid", "median_income", "accessibility_score", "geometry"])
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    filtered = apply_all_filters(gdf, income_threshold=50000, score_range=(0, 100))
    assert filtered.empty

def test_apply_all_filters_boundaries(sample_gdf):
    # Test boundary inclusivity for both income and score filters
    # geoid "1" has median_income=30000, accessibility_score=20
    filtered = apply_all_filters(sample_gdf, income_threshold=30000, score_range=(20, 20))
    assert len(filtered) == 1
    assert filtered.iloc[0]["geoid"] == "1"

def test_apply_all_filters_none_values():
    df = pd.DataFrame({
        "geoid": ["1", "2", "3"],
        "median_income": [30000, None, 150000],
        "accessibility_score": [20, 50, None],
        "geometry": [Point(0, 0) for _ in range(3)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    # Filters should exclude rows with None in relevant columns
    filtered = apply_all_filters(gdf, income_threshold=MAX_INCOME_THRESHOLD, score_range=(0, 100))
    assert len(filtered) == 1
    assert filtered.iloc[0]["geoid"] == "1"
