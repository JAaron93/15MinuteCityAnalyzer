import sys
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point


@pytest.fixture(scope="module")
def mock_cenpy():
    """Fixture to mock cenpy and prevent leaks across the pytest session."""
    mp = pytest.MonkeyPatch()
    mock = MagicMock()
    mock.products.ACS = MagicMock()
    mock.explorer.fips_table = MagicMock()

    # Use monkeypatch to safely set sys.modules
    mp.setitem(sys.modules, "cenpy", mock)
    mp.setitem(sys.modules, "cenpy.products", mock.products)
    mp.setitem(sys.modules, "cenpy.explorer", mock.explorer)

    yield mock
    mp.undo()


@pytest.fixture(scope="module")
def CensusFetcher(mock_cenpy):
    """Fixture to import and return the CensusFetcher class after mocking cenpy."""
    from src.pipeline.census_fetcher import CensusFetcher

    return CensusFetcher


@pytest.fixture
def mock_config(tmp_path):
    config_file = tmp_path / "pipeline_config.yaml"
    config_file.write_text("census_year: 2021\nretry_policy:\n  attempts: 1")
    return str(config_file)


def test_get_state_fips(CensusFetcher, mock_cenpy, mock_config):
    fetcher = CensusFetcher(mock_config)

    # Test digit input
    assert fetcher._get_state_fips("36") == "36"
    assert fetcher._get_state_fips("1") == "01"

    # Test name lookup
    mock_cenpy.explorer.fips_table.return_value = pd.DataFrame([{"state": 36}])
    assert fetcher._get_state_fips("New York") == "36"

    # Test failure fallback
    with pytest.raises(ValueError, match="Could not resolve state 'UnknownState'"):
        mock_cenpy.explorer.fips_table.side_effect = Exception("API Error")
        try:
            fetcher._get_state_fips("UnknownState")
        finally:
            mock_cenpy.explorer.fips_table.side_effect = None


def test_get_county_fips(CensusFetcher, mock_config):
    fetcher = CensusFetcher(mock_config)

    assert fetcher._get_county_fips("36", "1") == "001"
    assert fetcher._get_county_fips("36", "061") == "061"
    assert fetcher._get_county_fips("36", "Albany") == "Albany"


def test_fetch_county_block_groups_normalization(
    CensusFetcher, mock_cenpy, mock_config
):
    fetcher = CensusFetcher(mock_config)

    # Mock ACS products
    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs

    # Create a dummy response
    data = {
        "GEOID": ["360610001001"],
        "B01003_001E": [1000],
        "B19013_001E": [50000],
        "geometry": [Point(0, 0)],
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


def test_fetch_county_block_groups_preserves_existing_fips(
    CensusFetcher, mock_cenpy, mock_config
):
    fetcher = CensusFetcher(mock_config)

    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs

    data = {
        "GEOID": ["360610001001"],
        "B01003_001E": [1000],
        "B19013_001E": [50000],
        "state": [36],
        "county": [61],
        "geometry": [Point(0, 0)],
    }
    df = gpd.GeoDataFrame(data, crs="EPSG:4326")
    mock_acs.from_county.return_value = df

    result = fetcher._fetch_county_block_groups("36", "061")

    assert result.iloc[0]["state"] == "36"
    assert result.iloc[0]["county"] == "061"


def test_identify_counties(CensusFetcher, mock_cenpy, mock_config):
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
        "geometry": [Point(0, 0), Point(1, 1)],
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


def test_log_conflicts(CensusFetcher, mock_config, caplog):
    """Test that conflicting attribute values across counties are logged."""
    import logging

    fetcher = CensusFetcher(mock_config)

    duplicates = pd.DataFrame(
        {
            "geoid": ["bg1", "bg1"],
            "population": [100, 200],
            "median_income": [50000, 50000],
            "county": ["001", "002"],
        }
    )

    # Should not raise, just log
    with caplog.at_level(logging.WARNING):
        fetcher._log_conflicts(duplicates)

    assert "Conflict for geoid bg1 in field 'population'" in caplog.text
    assert "Values [100, 200] found in counties ['001', '002']" in caplog.text


def test_fetch_county_block_groups_empty(CensusFetcher, mock_cenpy, mock_config):
    """Test empty result from county query."""
    fetcher = CensusFetcher(mock_config)

    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs
    mock_acs.from_county.return_value = gpd.GeoDataFrame()

    result = fetcher._fetch_county_block_groups("36", "001")
    assert result.empty


def test_identify_counties_empty(CensusFetcher, mock_cenpy, mock_config):
    """Test _identify_counties returns empty list when no counties found."""
    mock_cenpy.explorer.fips_table.reset_mock()
    fetcher = CensusFetcher(mock_config)

    mock_cenpy.explorer.fips_table.return_value = pd.DataFrame([{"state": 36}])
    mock_acs = MagicMock()
    mock_cenpy.products.ACS.return_value = mock_acs
    mock_acs.from_polygon.return_value = gpd.GeoDataFrame()

    counties = fetcher._identify_counties("New York", (0, 0, 1, 1))
    assert counties == []


def test_identify_counties_exception(CensusFetcher, mock_cenpy, mock_config, caplog):
    """Test _identify_counties returns empty list on exception."""
    import logging

    mock_cenpy.explorer.fips_table.reset_mock()
    fetcher = CensusFetcher(mock_config)

    mock_cenpy.explorer.fips_table.side_effect = Exception("API down")
    try:
        with caplog.at_level(logging.ERROR):
            counties = fetcher._identify_counties("New York", (0, 0, 1, 1))
        assert counties == []
        assert "Error identifying counties: API down" in caplog.text
    finally:
        mock_cenpy.explorer.fips_table.side_effect = None
