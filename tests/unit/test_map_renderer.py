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


def test_create_choropleth_map_score(sample_gdf):
    m = create_choropleth_map(sample_gdf, metric="accessibility_score")
    assert isinstance(m, folium.Map)
    # Verify the GeoJson layer was added by checking the map's children
    geojson_layer = None
    for child in m._children.values():
        if isinstance(child, folium.features.GeoJson):
            geojson_layer = child
            break
    assert geojson_layer is not None, "No GeoJson layer found in map children"

    # Check that the GeoJson data contains the expected feature properties
    geojson_data = geojson_layer.data
    assert geojson_data['type'] == 'FeatureCollection'
    assert len(geojson_data['features']) == 1
    feature = geojson_data['features'][0]
    expected_properties = {
        'geoid': '1',
        'population': 100,
        'median_income': 50000.0,
        'accessibility_score': 75.0,
        'equity_category': 'High Access'
    }
    for key, value in expected_properties.items():
        assert feature['properties'][key] == value, f"Property {key} mismatch"


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
