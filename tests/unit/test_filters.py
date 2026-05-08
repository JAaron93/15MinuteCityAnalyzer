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
        "geometry": [Point(0,0)] * 3
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

def test_apply_all_filters_clamping(sample_gdf):
    # Test income clamping
    filtered = apply_all_filters(sample_gdf, income_threshold=MAX_INCOME_THRESHOLD + 1000, score_range=(0, 100))
    assert len(filtered) == 3 # All should pass if we clamp to MAX which is 200k

def test_apply_all_filters_normalization(sample_gdf):
    # Test score range normalization (swapping min/max)
    filtered = apply_all_filters(sample_gdf, income_threshold=MAX_INCOME_THRESHOLD, score_range=(90, 40))
    assert len(filtered) == 2
    assert set(filtered["geoid"]) == {"2", "3"}

def test_apply_all_filters_missing_cols():
    df = pd.DataFrame({"geoid": ["1"]})
    gdf = gpd.GeoDataFrame(df)
    with pytest.raises(ValueError, match="Missing 'median_income' column"):
        apply_all_filters(gdf, income_threshold=50000, score_range=(0, 100))

def test_apply_all_filters_invalid_types(sample_gdf):
    with pytest.raises(TypeError, match="income_threshold must be numeric"):
        apply_all_filters(sample_gdf, income_threshold="invalid", score_range=(0, 100))
    
    with pytest.raises(ValueError, match="score_range must be a tuple or list of length 2"):
        apply_all_filters(sample_gdf, income_threshold=50000, score_range=(0,))
