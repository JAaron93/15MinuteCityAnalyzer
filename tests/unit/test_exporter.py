import os

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.pipeline.exporter import FileSizeLimitError, export_to_geoparquet


def test_export_to_geoparquet_empty(tmp_path, caplog):
    output_path = tmp_path / "empty.parquet"
    export_to_geoparquet(gpd.GeoDataFrame(), str(output_path))
    assert "Empty GeoDataFrame, skipping export" in caplog.text
    assert not os.path.exists(output_path)


def test_export_to_geoparquet_success(tmp_path):
    output_path = tmp_path / "test.parquet"
    df = pd.DataFrame({"geoid": ["1"], "geometry": [Point(0, 0)]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    metadata = {"city": "Corona", "date": "2024-01-01"}

    export_to_geoparquet(gdf, str(output_path), metadata=metadata)

    assert os.path.exists(output_path)
    # Reload and check
    loaded_gdf = gpd.read_parquet(output_path)
    assert len(loaded_gdf) == 1
    # Check if metadata is present (requires pyarrow directly or checking geoparquet metadata)  # noqa: E501
    # For now, just check it saves without error.


def test_export_to_geoparquet_reprojection(tmp_path):
    output_path = tmp_path / "reproject.parquet"
    df = pd.DataFrame({"geoid": ["1"], "geometry": [Point(0, 0)]})
    # Use UTM
    gdf = gpd.GeoDataFrame(df, crs="EPSG:32611")
    export_to_geoparquet(gdf, str(output_path))

    loaded_gdf = gpd.read_parquet(output_path)
    assert loaded_gdf.crs.to_epsg() == 4326


def test_export_to_geoparquet_size_remediation(tmp_path, mocker):
    output_path = tmp_path / "large.parquet"
    # Create a complex gdf to trigger remediation (or just mock getsize)
    df = pd.DataFrame({"geoid": ["1"], "geometry": [box(0, 0, 1, 1)]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    # Mock os.path.getsize to return > 50 MB first, then < 50 MB
    mocker.patch("os.path.getsize", side_effect=[60 * 1024 * 1024, 40 * 1024 * 1024])

    export_to_geoparquet(gdf, str(output_path))
    # It should pass after one simplification step (the mock changes size on 2nd call)
    assert os.path.exists(output_path)


def test_export_to_geoparquet_file_size_error(tmp_path, mocker):
    output_path = tmp_path / "too_large.parquet"
    df = pd.DataFrame({"geoid": ["1"], "geometry": [box(0, 0, 1, 1)]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    # Always return > 50 MB
    mocker.patch("os.path.getsize", return_value=60 * 1024 * 1024)

    with pytest.raises(FileSizeLimitError):
        export_to_geoparquet(gdf, str(output_path))


def test_export_to_geoparquet_missing_cols(tmp_path, caplog):
    output_path = tmp_path / "missing.parquet"
    # Create GeoDataFrame with only some required columns
    df = pd.DataFrame({"geoid": ["1"], "geometry": [Point(0, 0)], "extra_col": ["val"]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

    export_to_geoparquet(gdf, str(output_path))

    # Verify log contains missing columns warning
    assert "Missing required columns:" in caplog.text
    # Verify it mentions specific missing column like 'population'
    assert "population" in caplog.text
    # Verify it mentions existing columns to be pruned
    assert "geoid" in caplog.text
    assert "geometry" in caplog.text
    # Verify 'extra_col' is pruned from the exported file
    loaded_gdf = gpd.read_parquet(output_path)
    assert "extra_col" not in loaded_gdf.columns
    assert "geoid" in loaded_gdf.columns


def test_export_to_geoparquet_skipped_pruning(tmp_path, caplog):
    output_path = tmp_path / "no_cols.parquet"
    # Create GeoDataFrame with no required columns, but with an active geometry named 'geom'
    df = pd.DataFrame({"some_other_col": ["val"], "geom": [Point(0, 0)]})
    gdf = gpd.GeoDataFrame(df, geometry="geom", crs="EPSG:4326")

    export_to_geoparquet(gdf, str(output_path))

    # Verify log contains pruning skipped warning
    assert "No required columns found in GeoDataFrame. Pruning is skipped." in caplog.text
    # Verify the exported file still has 'some_other_col' because pruning was skipped
    loaded_gdf = gpd.read_parquet(output_path)
    assert "some_other_col" in loaded_gdf.columns


