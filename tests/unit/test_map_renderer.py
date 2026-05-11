import pytest
import pandas as pd
import geopandas as gpd
import folium
from shapely.geometry import box
from src.dashboard.map_renderer import create_choropleth_map


@pytest.fixture
def sample_gdf():
    df = pd.DataFrame({
        "geoid": ["1"],
        "population": [100],
        "median_income": [50000.0],
        "accessibility_score": [75.0],
        "equity_category": ["High Access"],
        "geometry": [box(0, 0, 1, 1)]
    })
    return gpd.GeoDataFrame(df, crs="EPSG:4326")


def test_create_choropleth_map_empty():
    msg = "Cannot create map from empty dataset"
    with pytest.raises(ValueError, match=msg):
        create_choropleth_map(gpd.GeoDataFrame())


def test_create_choropleth_map_score(sample_gdf, mocker):
    # Capture the GeoJson object when it's created to avoid searching map children
    spy = mocker.spy(folium, "GeoJson")

    m = create_choropleth_map(sample_gdf, metric="accessibility_score")
    assert isinstance(m, folium.Map)

    # Get the actual GeoJson instance that was created
    geojson_layer = spy.spy_return

    # Verify the GeoJson layer was added to the map
    assert any(
        child is geojson_layer for child in m._children.values()
    ), "No GeoJson layer found in map children"

    # Check that the GeoJson data contains the expected feature properties
    assert hasattr(geojson_layer, "data"), "GeoJson layer has no 'data' attribute"
    geojson_data = geojson_layer.data
    assert isinstance(geojson_data, dict), "GeoJson data is not a dictionary"
    assert (
        geojson_data.get("type") == "FeatureCollection"
    ), "GeoJson data type is not 'FeatureCollection'"
    assert "features" in geojson_data, "GeoJson data missing 'features' key"
    assert isinstance(geojson_data["features"], list), "'features' is not a list"
    assert len(geojson_data["features"]) >= 1, "No features found in GeoJson data"

    feature = geojson_data["features"][0]
    assert isinstance(feature, dict), "First feature is not a dictionary"
    assert "properties" in feature, "First feature missing 'properties' key"

    expected_properties = {
        "geoid": "1",
        "population": 100,
        "median_income": 50000.0,
        "accessibility_score": 75.0,
        "equity_category": "High Access",
    }
    properties = feature["properties"]
    for key, value in expected_properties.items():
        assert key in properties, f"Property {key} missing from feature properties"
        assert properties[key] == value, f"Property {key} mismatch"


def test_create_choropleth_map_income(sample_gdf):
    m = create_choropleth_map(sample_gdf, metric="median_income")
    assert isinstance(m, folium.Map)


def test_create_choropleth_map_income_single_value():
    # Test vmin == vmax case
    df = pd.DataFrame({
        "geoid": ["1", "2"],
        "population": [100, 200],
        "median_income": [50000.0, 50000.0],
        "accessibility_score": [75.0, 80.0],
        "equity_category": ["High Access", "High Access"],
        "geometry": [box(0, 0, 1, 1), box(1, 1, 2, 2)]
    })
    gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
    m = create_choropleth_map(gdf, metric="median_income")
    assert isinstance(m, folium.Map)
