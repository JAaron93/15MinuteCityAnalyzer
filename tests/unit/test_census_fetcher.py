import sys
from unittest.mock import MagicMock, patch

# COMPLETELY MOCK cenpy before any other imports
mock_cenpy = MagicMock()
mock_cenpy.products.ACS = MagicMock()
mock_cenpy.explorer.fips_table = MagicMock()
sys.modules["cenpy"] = mock_cenpy
sys.modules["cenpy.products"] = mock_cenpy.products
sys.modules["cenpy.explorer"] = mock_cenpy.explorer

import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from src.pipeline.census_fetcher import CensusFetcher

@pytest.fixture
def mock_config(tmp_path):
    config_file = tmp_path / "pipeline_config.yaml"
    config_file.write_text("census_year: 2021\nretry_policy:\n  attempts: 1")
    return str(config_file)

def test_get_state_fips(mock_config):
    fetcher = CensusFetcher(mock_config)
    
    # Test digit input
    assert fetcher._get_state_fips("36") == "36"
    assert fetcher._get_state_fips("1") == "01"
    
    # Test name lookup
    mock_cenpy.explorer.fips_table.return_value = pd.DataFrame([{"state": 36}])
    assert fetcher._get_state_fips("New York") == "36"
    
    # Test failure fallback
    mock_cenpy.explorer.fips_table.side_effect = Exception("API Error")
    assert fetcher._get_state_fips("UnknownState") == "UnknownState"
    # Reset side effect for other tests
    mock_cenpy.explorer.fips_table.side_effect = None

def test_get_county_fips(mock_config):
    fetcher = CensusFetcher(mock_config)
    
    assert fetcher._get_county_fips("36", "1") == "001"
    assert fetcher._get_county_fips("36", "061") == "061"
    assert fetcher._get_county_fips("36", "Albany") == "Albany"

def test_fetch_county_block_groups_normalization(mock_config):
    fetcher = CensusFetcher(mock_config)
    
    # Mock ACS products
    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs
    
    # Create a dummy response
    data = {
        "GEOID": ["360610001001"],
        "B01003_001E": [1000],
        "B19013_001E": [50000],
        "geometry": [Point(0, 0)]
    }
    df = gpd.GeoDataFrame(data, crs="EPSG:4326")
    mock_acs.from_county.return_value = df
    
    with patch.object(fetcher, "_get_state_fips", return_value="36"):
        result = fetcher._fetch_county_block_groups("New York", "61")
        
        assert result.iloc[0]["state"] == "36"
        assert result.iloc[0]["county"] == "061"
        assert isinstance(result.iloc[0]["state"], str)
        assert isinstance(result.iloc[0]["county"], str)
        
        mock_acs.from_county.assert_called_with(
            "36, 061", level="block group", variables=["B01003_001E", "B19013_001E"]
        )

def test_fetch_county_block_groups_preserves_existing_fips(mock_config):
    fetcher = CensusFetcher(mock_config)
    
    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs
    
    data = {
        "GEOID": ["360610001001"],
        "B01003_001E": [1000],
        "B19013_001E": [50000],
        "state": [36],
        "county": [61],
        "geometry": [Point(0, 0)]
    }
    df = gpd.GeoDataFrame(data, crs="EPSG:4326")
    mock_acs.from_county.return_value = df
    
    result = fetcher._fetch_county_block_groups("36", "061")
    
    assert result.iloc[0]["state"] == "36"
    assert result.iloc[0]["county"] == "061"

def test_identify_counties(mock_config):
    # Reset mock call count
    mock_cenpy.explorer.fips_table.reset_mock()
    fetcher = CensusFetcher(mock_config)
    
    # Mock state FIPS lookup
    mock_cenpy.explorer.fips_table.return_value = pd.DataFrame([{"state": 36}])
    
    # Mock ACS and from_polygon
    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs
    
    # Create mock counties GDF
    # One county in state 36, one in state 34 (NJ)
    counties_data = {
        "county": ["001", "003"],
        "state": [36, 34],
        "geometry": [Point(0, 0), Point(1, 1)]
    }
    counties_gdf = gpd.GeoDataFrame(counties_data, crs="EPSG:4326")
    mock_acs.from_polygon.return_value = counties_gdf
    
    # Should only return county "001" for state 36
    bbox = (0, 0, 1, 1)
    counties = fetcher._identify_counties("New York", bbox)
    
    assert counties == ["001"]
    # Verify it used the extracted state_fips_code (36) for filtering
    # and didn't call fips_table a second time
    assert mock_cenpy.explorer.fips_table.call_count == 1
