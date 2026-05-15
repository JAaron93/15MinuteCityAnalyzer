from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from shapely.geometry import Point

from src.pipeline.osm_fetcher import OSMFetcher


def test_osm_fetcher_init():
    fetcher = OSMFetcher()
    assert fetcher.bbox_limits["max_edge_degrees"] == 1.0
    assert "grocery" in fetcher.amenity_tags


@pytest.fixture
def mock_insufficient_response_error():
    """Fixture to provide a custom InsufficientResponseError for OSMnx mocks."""

    class InsufficientResponseError(Exception):
        pass

    return InsufficientResponseError


def test_validate_bbox_pass():
    fetcher = OSMFetcher()
    # 0.5 x 0.5 is fine (area 0.25 < 1.0, edge 0.5 < 1.0)
    fetcher._validate_bbox((45.5, 45.0, -122.0, -122.5))


def test_validate_bbox_fail():
    fetcher = OSMFetcher()
    # 1.5 x 1.5 is too large (edge 1.5 > 1.0)
    with pytest.raises(Exception, match="Bounding box exceeds limits"):
        fetcher._validate_bbox((46.5, 45.0, -121.0, -122.5))


def test_validate_bbox_pass_when_tiling_enabled():
    """When tiling is enabled, oversized bbox should not raise."""
    fetcher = OSMFetcher()
    fetcher.bbox_limits["enable_tiling"] = True
    # This would fail without tiling, but should pass with tiling enabled
    fetcher._validate_bbox((46.5, 45.0, -121.0, -122.5))


@patch("src.pipeline.osm_fetcher.ox")
@patch("src.pipeline.osm_fetcher.DataValidator")
def test_fetch_amenities_batch(mock_validator, mock_ox):
    """Test _fetch_amenities_batch with mocked OSMnx."""
    fetcher = OSMFetcher()

    # Mock ox.features_from_bbox to return a small GeoDataFrame for each type
    mock_gdf = gpd.GeoDataFrame(
        {"geometry": [Point(0, 0)], "name": ["Test"]},
        crs="EPSG:4326",
    )
    mock_ox.features_from_bbox.return_value = mock_gdf

    bbox = (45.5, 45.0, -122.0, -122.5)
    # Call the underlying function directly (unwrap the retry decorator)
    result = fetcher._fetch_amenities_batch(bbox)

    assert not result.empty
    assert "amenity_type" in result.columns
    # Should have been called once per amenity type (4 types)
    assert mock_ox.features_from_bbox.call_count == len(fetcher.amenity_tags)


@patch("src.pipeline.osm_fetcher.ox")
@patch("src.pipeline.osm_fetcher.DataValidator")
def test_fetch_amenities_batch_empty(
    mock_validator, mock_ox, mock_insufficient_response_error
):
    """Test _fetch_amenities_batch when OSMnx returns no results."""
    fetcher = OSMFetcher()

    mock_ox._errors = MagicMock()
    mock_ox._errors.InsufficientResponseError = mock_insufficient_response_error
    mock_ox.features_from_bbox.side_effect = mock_insufficient_response_error()

    bbox = (45.5, 45.0, -122.0, -122.5)
    result = fetcher._fetch_amenities_batch(bbox)

    assert result.empty


@patch("src.pipeline.osm_fetcher.ox")
@patch("src.pipeline.osm_fetcher.DataValidator")
def test_fetch_amenities_with_validation(mock_validator, mock_ox):
    """Test that fetch_amenities calls validation."""
    fetcher = OSMFetcher()
    mock_gdf = gpd.GeoDataFrame(
        {"geometry": [Point(0, 0)], "amenity_type": ["grocery"]},
        crs="EPSG:4326",
    )
    mock_ox.features_from_bbox.return_value = mock_gdf
    mock_validator.validate_osm_data.return_value = True

    # Patch the decorated method to bypass retry
    with patch.object(fetcher, "_fetch_amenities_batch", return_value=mock_gdf):
        bbox = (45.5, 45.0, -122.0, -122.5)
        fetcher.fetch_amenities(bbox)
        mock_validator.validate_osm_data.assert_called_once()


@patch("src.pipeline.osm_fetcher.ox")
def test_fetch_street_network(mock_ox):
    """Test fetch_street_network calls ox.graph_from_bbox."""
    fetcher = OSMFetcher()
    mock_graph = MagicMock()
    mock_graph.nodes = {1: {"x": 0, "y": 0}}
    mock_graph.edges = [(1, 2)]

    # Patch the decorated method to bypass retry
    with patch.object(fetcher, "_fetch_network_batch", return_value=mock_graph):
        bbox = (45.5, 45.0, -122.0, -122.5)
        result = fetcher.fetch_street_network(bbox)
        assert result is not None


@patch("src.pipeline.osm_fetcher.ox")
@patch("src.pipeline.osm_fetcher.DataValidator")
def test_fetch_with_tiling_amenities(mock_validator, mock_ox):
    """Test tiling logic for amenities."""
    fetcher = OSMFetcher()
    fetcher.bbox_limits["enable_tiling"] = True
    fetcher.bbox_limits["max_edge_degrees"] = 0.5

    mock_gdf = gpd.GeoDataFrame(
        {"geometry": [Point(0, 0)], "amenity_type": ["grocery"]},
        crs="EPSG:4326",
    )
    mock_validator.validate_osm_data.return_value = True

    # Patch the decorated batch method to bypass retry
    with patch.object(fetcher, "_fetch_amenities_batch", return_value=mock_gdf):
        bbox = (45.5, 45.0, -122.0, -122.5)
        fetcher.fetch_amenities(bbox)
        # Should have called batch method multiple times (tiles > 1)
        assert fetcher._fetch_amenities_batch.call_count >= 2


@patch("src.pipeline.osm_fetcher.ox")
@patch("src.pipeline.osm_fetcher.DataValidator")
def test_fetch_with_tiling_failure_threshold(mock_validator, mock_ox):
    """Test tiling failure threshold raises exception."""
    fetcher = OSMFetcher()
    # Guard or initialize config before mutating it
    if not isinstance(fetcher.config, dict):
        fetcher.config = {}

    fetcher.bbox_limits["enable_tiling"] = True
    fetcher.bbox_limits["max_edge_degrees"] = 0.5
    fetcher.config.setdefault("bbox_limits", {}).setdefault("tiling", {})[
        "failure_threshold"
    ] = 0.0

    mock_validator.validate_osm_data.return_value = True

    # Patch the decorated batch method to raise
    with patch.object(
        fetcher, "_fetch_amenities_batch", side_effect=Exception("Network error")
    ):
        bbox = (45.5, 45.0, -122.0, -122.5)
        with pytest.raises(Exception, match="Tiling failure"):
            fetcher.fetch_amenities(bbox)


@patch("src.pipeline.osm_fetcher.ox")
def test_fetch_amenities_batch_mixed_results(mock_ox, mock_insufficient_response_error):
    """Test that some amenity types return data while others raise errors."""
    fetcher = OSMFetcher()

    mock_ox._errors = MagicMock()
    mock_ox._errors.InsufficientResponseError = mock_insufficient_response_error

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 0:
            raise mock_insufficient_response_error()
        return gpd.GeoDataFrame(
            {"geometry": [Point(0, 0)], "name": ["Test"]}, crs="EPSG:4326"
        )

    mock_ox.features_from_bbox.side_effect = side_effect

    bbox = (45.5, 45.0, -122.0, -122.5)
    result = fetcher._fetch_amenities_batch(bbox)

    # At least some results should come through
    assert not result.empty
    assert "amenity_type" in result.columns
