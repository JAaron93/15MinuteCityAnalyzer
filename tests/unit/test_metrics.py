import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from src.dashboard.metrics import calculate_equity_metrics

def test_calculate_equity_metrics_empty():
    gdf = gpd.GeoDataFrame()
    metrics = calculate_equity_metrics(gdf)
    assert metrics["total_block_groups"] == 0
    assert metrics["total_population"] == 0
    assert metrics["avg_score_by_quartile"] == {}

def test_calculate_equity_metrics_valid():
    df = pd.DataFrame({
        "geoid": ["1", "2", "3", "4"],
        "population": [100, 200, 300, 400],
        "median_income": [30000, 40000, 50000, 60000],
        "accessibility_score": [20, 30, 70, 80],
        "equity_category": ["Low Access", "Low Access", "High Access", "High Access"],
        "geometry": [Point(0,0)] * 4
    })
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

def test_calculate_equity_metrics_missing_cols():
    df = pd.DataFrame({"geoid": ["1"]})
    gdf = gpd.GeoDataFrame(df)
    with pytest.raises(ValueError, match="Missing required columns"):
        calculate_equity_metrics(gdf)

def test_calculate_equity_metrics_zero_income_quartile():
    # Test that we don't crash with fewer than 4 records for quartiles
    df = pd.DataFrame({
        "geoid": ["1", "2"],
        "population": [100, 200],
        "median_income": [30000, 40000],
        "accessibility_score": [20, 30],
        "equity_category": ["Low Access", "Low Access"],
        "geometry": [Point(0,0)] * 2
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    metrics = calculate_equity_metrics(gdf)
    assert metrics["avg_score_by_quartile"] == {}
