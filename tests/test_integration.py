"""Integration tests for the 15-Minute City pipeline and dashboard."""

import os
import tempfile
import time
import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon
import pandas as pd

from src.pipeline.crs_utils import WGS84, transform_to_utm, transform_to_wgs84
from src.pipeline.scoring import spatial_join_amenities, calculate_accessibility_score, assign_equity_category, count_amenities_by_type
from src.pipeline.exporter import export_to_geoparquet
from src.dashboard.data_loader import load_geoparquet
from src.dashboard.metrics import calculate_equity_metrics

def generate_mock_data():
    """Generate minimal mock data for the pipeline."""
    # A small block group
    lon, lat = -117.56, 33.87 # Corona, CA approx
    bg_geom = Polygon([
        (lon, lat), (lon + 0.01, lat), 
        (lon + 0.01, lat + 0.01), (lon, lat + 0.01), (lon, lat)
    ])
    
    block_groups = gpd.GeoDataFrame({
        "geoid": ["060650400001"],
        "population": [1500],
        "median_income": [65000.0]
    }, geometry=[bg_geom], crs=WGS84)
    
    # An isochrone overlapping the block group
    iso_geom = Polygon([
        (lon + 0.005, lat + 0.005), (lon + 0.015, lat + 0.005),
        (lon + 0.015, lat + 0.015), (lon + 0.005, lat + 0.015), (lon + 0.005, lat + 0.005)
    ])
    
    isochrones = gpd.GeoDataFrame({
        "amenity_type": ["grocery"]
    }, geometry=[iso_geom], crs=WGS84)
    
    return block_groups, isochrones

def test_pipeline_to_dashboard_integration():
    """
    Test end-to-end pipeline with small test city, export, and load into dashboard.
    Covers:
    6.6.2 Test end-to-end pipeline with small test city
    6.6.3 Test pipeline-to-dashboard integration
    6.6.4 Test GeoParquet export and import round-trip
    6.6.5 Test cross-CRS transformations throughout pipeline
    6.6.6 Measure and validate processing time for test city
    """
    start_time = time.time()
    
    # 1. Generate Mock Data (Simulates fetching)
    block_groups, isochrones = generate_mock_data()
    
    # 2. CRS Transformation & Spatial Join
    utm_crs = block_groups.iloc[[0]].estimate_utm_crs()
    joined = spatial_join_amenities(block_groups, isochrones, utm_crs)
    
    # 3. Amenity Counting
    bg_counts = count_amenities_by_type(joined, block_groups)
    
    # 4. Accessibility Scoring
    bg_scored = calculate_accessibility_score(bg_counts)
    
    # 5. Equity Category Assignment
    bg_final, metadata = assign_equity_category(bg_scored)
    
    # Validate metadata
    assert metadata is not None
    assert "equity_thresholds.high_access_min" in metadata
    assert "equity_thresholds.medium_access_min" in metadata
    assert "equity_thresholds.validated_at" in metadata
    
    # 6. Ensure CRS consistency
    assert bg_final.crs.to_string() == "EPSG:4326"
    
    # 7. GeoParquet export and import round-trip
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test_output.parquet")
        
        # Export
        export_to_geoparquet(bg_final, out_path, metadata)
        assert os.path.exists(out_path)
        
        # Load (Dashboard side)
        loaded_df = load_geoparquet(out_path)
        
        assert not loaded_df.empty
        assert "accessibility_score" in loaded_df.columns
        assert "equity_category" in loaded_df.columns
        assert loaded_df.crs.to_string() == "EPSG:4326"
        
        # Concrete value assertions for the mock data
        # With only 1 block group, score is normalized to 50.0 (city_min == city_max case)
        # and 50.0 >= 40.0 (default medium threshold) gives "Medium Access"
        assert loaded_df.iloc[0]["accessibility_score"] == 50.0
        assert loaded_df.iloc[0]["equity_category"] == "Medium Access"
        
        # 8. Dashboard metrics calculation
        metrics = calculate_equity_metrics(loaded_df, income_threshold=50000.0)
        assert metrics is not None
        assert metrics["total_block_groups"] == 1
        assert metrics["total_population"] == 1500
        assert metrics["city_avg_score"] == 50.0
        assert metrics["pct_pop_low_access"] == 0.0  # It's Medium Access
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Validate processing time
    assert processing_time < 30.0, f"Processing took {processing_time:.2f}s, expected < 30s"
