import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from src.dashboard.data_loader import ValidationError, load_geoparquet


def test_load_geoparquet_file_not_found(mocker):
    mocker.patch("src.dashboard.data_loader.os.path.exists", return_value=False)
    with pytest.raises(FileNotFoundError, match="Processed data not found"):
        load_geoparquet("nonexistent.parquet")


def test_load_geoparquet_missing_columns(tmp_path):
    # Create a dummy geoparquet file with missing columns
    file_path = tmp_path / "missing_cols.parquet"
    df = pd.DataFrame(
        {
            "geoid": ["1"],
            "geometry": [Point(0, 0)],
            "population": [100],
            # Missing median_income, accessibility_score, etc.
        }
    )
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(file_path)

    with pytest.raises(ValidationError, match="Missing required columns"):
        load_geoparquet(str(file_path))


def test_load_geoparquet_success(tmp_path):
    file_path = tmp_path / "valid.parquet"
    df = pd.DataFrame(
        {
            "geoid": ["1"],
            "geometry": [Point(0, 0)],
            "population": [100],
            "median_income": [50000.0],
            "raw_score": [50.0],
            "accessibility_score": [50.0],
            "equity_category": ["High Access"],
        }
    )
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(file_path)

    loaded_gdf = load_geoparquet(str(file_path))

    assert len(loaded_gdf) == 1
    assert "accessibility_score" in loaded_gdf.columns
    assert loaded_gdf.crs.to_epsg() == 4326
    assert loaded_gdf.loc[0, "population"] == 100
    assert loaded_gdf.loc[0, "median_income"] == 50000.0
    assert loaded_gdf.loc[0, "accessibility_score"] == 50.0


def test_load_geoparquet_reprojection(tmp_path):
    file_path = tmp_path / "reproject.parquet"
    df = pd.DataFrame(
        {
            "geoid": ["1"],
            "geometry": [Point(1000000, 1000000)],
            "population": [100],
            "median_income": [50000.0],
            "raw_score": [50.0],
            "accessibility_score": [50.0],
            "equity_category": ["High Access"],
        }
    )
    # Create with different CRS
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:3857")
    gdf.to_parquet(file_path)

    loaded_gdf = load_geoparquet(str(file_path))

    assert loaded_gdf.crs.to_epsg() == 4326
    # Verify coordinates were actually transformed
    geom = loaded_gdf.loc[0, "geometry"]
    assert geom.x != 1000000
    assert geom.y != 1000000


def test_load_geoparquet_invalid_crs(tmp_path):
    file_path = tmp_path / "invalid_crs.parquet"
    df = pd.DataFrame(
        {
            "geoid": ["1"],
            "geometry": [Point(0, 0)],
            "population": [100],
            "median_income": [50000.0],
            "raw_score": [50.0],
            "accessibility_score": [50.0],
            "equity_category": ["High Access"],
        }
    )
    # Create with a custom CRS that doesn't have an EPSG code
    gdf = gpd.GeoDataFrame(
        df,
        geometry="geometry",
        crs="+proj=laea +lat_0=45 +lon_0=-100 +x_0=0 +y_0=0 +a=6370997 +b=6370997 +units=m +no_defs",  # noqa: E501
    )
    gdf.to_parquet(file_path)

    with pytest.raises(ValidationError, match="non-standard or unsupported CRS"):
        load_geoparquet(str(file_path))
