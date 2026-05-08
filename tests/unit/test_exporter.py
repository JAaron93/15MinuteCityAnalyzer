import pytest
import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, box
from src.pipeline.exporter import export_to_geoparquet, FileSizeLimitError

def test_export_to_geoparquet_empty(tmp_path, caplog):
    output_path = tmp_path / "empty.parquet"
    export_to_geoparquet(gpd.GeoDataFrame(), str(output_path))
    assert "Empty GeoDataFrame, skipping export" in caplog.text
    assert not os.path.exists(output_path)

def test_export_to_geoparquet_success(tmp_path):
    output_path = tmp_path / "test.parquet"
    df = pd.DataFrame({
        "geoid": ["1"],
        "geometry": [Point(0, 0)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    metadata = {"city": "Corona", "date": "2024-01-01"}
    
    export_to_geoparquet(gdf, str(output_path), metadata=metadata)
    
    assert os.path.exists(output_path)
    # Reload and check
    loaded_gdf = gpd.read_parquet(output_path)
    assert len(loaded_gdf) == 1
    # Check if metadata is present (requires pyarrow directly or checking geoparquet metadata)
    # For now, just check it saves without error.

def test_export_to_geoparquet_reprojection(tmp_path):
    output_path = tmp_path / "reproject.parquet"
    df = pd.DataFrame({
        "geoid": ["1"],
        "geometry": [Point(0, 0)]
    })
    # Use UTM
    gdf = gpd.GeoDataFrame(df, crs="EPSG:32611")
    export_to_geoparquet(gdf, str(output_path))
    
    loaded_gdf = gpd.read_parquet(output_path)
    assert loaded_gdf.crs.to_epsg() == 4326

def test_export_to_geoparquet_size_remediation(tmp_path, mocker):
    output_path = tmp_path / "large.parquet"
    # Create a complex gdf to trigger remediation (or just mock getsize)
    df = pd.DataFrame({
        "geoid": ["1"],
        "geometry": [box(0, 0, 1, 1)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    
    # Mock os.path.getsize to return > 50 MB first, then < 50 MB
    mocker.patch("os.path.getsize", side_effect=[60 * 1024 * 1024, 40 * 1024 * 1024])
    
    export_to_geoparquet(gdf, str(output_path))
    # It should pass after one simplification step (the mock changes size on 2nd call)
    assert os.path.exists(output_path)

def test_export_to_geoparquet_file_size_error(tmp_path, mocker):
    output_path = tmp_path / "too_large.parquet"
    df = pd.DataFrame({
        "geoid": ["1"],
        "geometry": [box(0, 0, 1, 1)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    
    # Always return > 50 MB
    mocker.patch("os.path.getsize", return_value=60 * 1024 * 1024)
    
    with pytest.raises(FileSizeLimitError):
        export_to_geoparquet(gdf, str(output_path))
