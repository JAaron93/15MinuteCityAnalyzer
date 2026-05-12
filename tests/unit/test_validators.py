import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from src.pipeline.data_validator import DataValidator

@pytest.fixture
def sample_census_df():
    df = pd.DataFrame({
        "geoid": ["1", "2"],
        "population": [100, -50],
        "median_income": [50000, 60000],
        "geometry": [Point(0, 0), Point(1, 1)]
    })
    return gpd.GeoDataFrame(df, crs="EPSG:4326")

def test_validate_census_data_basic(sample_census_df):
    validator = DataValidator()
    # Test valid case (with repair of negative pop)
    assert validator.validate_census_data(sample_census_df) is True
    assert sample_census_df.loc[1, "population"] == 0

def test_validate_census_data_empty():
    validator = DataValidator()
    assert validator.validate_census_data(gpd.GeoDataFrame()) is False

def test_validate_census_data_missing_cols():
    validator = DataValidator()
    df = pd.DataFrame({"geoid": ["1"]})
    assert validator.validate_census_data(gpd.GeoDataFrame(df)) is False

def test_validate_osm_data_basic():
    validator = DataValidator()
    df = pd.DataFrame({
        "osm_id": ["1"],
        "amenity_type": ["grocery"],
        "geometry": [Point(0, 0)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    result = validator.validate_osm_data(gdf)
    assert result is True
    assert len(gdf) == 1

def test_validate_crs_none():
    validator = DataValidator()
    df = pd.DataFrame({"geometry": [Point(0, 0)]})
    gdf = gpd.GeoDataFrame(df)
    assert gdf.crs is None
    assert validator.validate_crs(gdf, "EPSG:4326") is True
    assert gdf.crs.to_string() == "EPSG:4326"

def test_repair_geometries():
    validator = DataValidator()
    # Create invalid polygon (self-intersecting bowtie)
    p1 = Polygon([(0, 0), (2, 2), (0, 2), (2, 0)])
    assert not p1.is_valid
    gdf = gpd.GeoDataFrame({"geometry": [p1]}, crs="EPSG:4326")
    repaired_gdf = validator.repair_geometries(gdf)
    assert repaired_gdf.geometry[0].is_valid

def test_validate_demographics():
    validator = DataValidator()
    df = pd.DataFrame({
        "population": [100, None],
        "median_income": [50000, None]
    })
    gdf = gpd.GeoDataFrame(df)
    assert validator.validate_demographics(gdf) is True
    assert gdf.loc[1, "population"] == 0


def test_validate_osm_data_empty():
    """Empty OSM data is valid (no POIs in area is OK)."""
    validator = DataValidator()
    assert validator.validate_osm_data(gpd.GeoDataFrame()) is True


def test_validate_osm_data_missing_amenity_type():
    """OSM data without amenity_type column should fail."""
    validator = DataValidator()
    df = pd.DataFrame({"osm_id": ["1"], "geometry": [Point(0, 0)]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    assert validator.validate_osm_data(gdf) is False


def test_validate_osm_data_null_geometry():
    """OSM data with null geometries should be cleaned."""
    validator = DataValidator()
    df = pd.DataFrame({
        "amenity_type": ["grocery", "grocery"],
        "geometry": [Point(0, 0), None]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    assert validator.validate_osm_data(gdf) is True
    assert len(gdf) == 1  # null geometry row dropped


def test_validate_census_data_null_geometry():
    """Census data with null geometries should be dropped."""
    validator = DataValidator()
    df = pd.DataFrame({
        "geoid": ["1", "2"],
        "population": [100, 200],
        "median_income": [50000, 60000],
        "geometry": [Point(0, 0), None]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    assert validator.validate_census_data(gdf) is True
    assert len(gdf) == 1


def test_validate_crs_mismatch():
    """CRS mismatch should trigger re-projection."""
    validator = DataValidator()
    df = pd.DataFrame({"geometry": [Point(0, 0)]})
    gdf = gpd.GeoDataFrame(df, crs="EPSG:3857")
    assert validator.validate_crs(gdf, "EPSG:4326") is True
    assert gdf.crs.to_string() == "EPSG:4326"


def test_repair_geometries_all_valid():
    """Repairing already-valid geometries should be a no-op."""
    validator = DataValidator()
    p = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    assert p.is_valid
    gdf = gpd.GeoDataFrame({"geometry": [p]}, crs="EPSG:4326")
    repaired = validator.repair_geometries(gdf)
    assert repaired.geometry[0].is_valid

