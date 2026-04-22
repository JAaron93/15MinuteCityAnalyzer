"""Unit tests for accessibility calculations."""

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from fifteen_minute_city.accessibility import (
    calculate_accessibility_score,
    DEFAULT_TIME_MINUTES,
    generate_grid_accessibility,
    WALKING_SPEED_MPM,
)
from fifteen_minute_city.data_loader import DEFAULT_AMENITIES


class TestAccessibilityCalculations:
    """Tests for 15-minute city accessibility calculations."""

    def test_default_constants(self) -> None:
        """Test that default constants are reasonable."""
        assert WALKING_SPEED_MPM == 83.0  # ~5 km/h
        assert DEFAULT_TIME_MINUTES == 15
        assert "grocery" in DEFAULT_AMENITIES
        assert "transit" in DEFAULT_AMENITIES

    def test_accessibility_score_structure(self) -> None:
        """Test that accessibility score returns the expected dict structure.

        A single-node graph is sufficient: ox.nearest_nodes resolves against
        any non-empty graph, nx.single_source_dijkstra is guarded internally,
        and per-amenity errors are swallowed inside the function. The return
        dict is always produced, so no exception is expected here.
        """
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.8715, x=-122.2730)

        amenities = {
            "grocery": gpd.GeoDataFrame(geometry=[Point(-122.2730, 37.8715)]),
        }
        point = (37.8715, -122.2730)

        result = calculate_accessibility_score(
            point,
            amenities,
            G,
            time_threshold_minutes=15,
        )

        assert "lat" in result
        assert "lon" in result
        assert "overall_score" in result
        assert "amenities" in result
        assert "time_threshold" in result


class TestGridGeneration:
    """Tests for grid-based accessibility generation."""

    def test_grid_parameters(self) -> None:
        """Test grid generation with various parameters."""
        bounds = (37.8, -122.3, 37.9, -122.2)
        resolution = 5

        # Create a simple mock graph
        G = nx.MultiDiGraph()

        # Add some nodes to the graph
        lats = np.linspace(bounds[0], bounds[2], resolution)
        lons = np.linspace(bounds[1], bounds[3], resolution)

        node_id = 0
        for lat in lats:
            for lon in lons:
                G.add_node(node_id, y=lat, x=lon)
                node_id += 1

        # Empty amenities
        amenities = {}

        # Should return an empty DataFrame or handle gracefully
        df = generate_grid_accessibility(
            bounds,
            amenities,
            G,
            grid_resolution=resolution,
        )
        assert isinstance(df, pd.DataFrame)

    def test_bounds_calculation(self) -> None:
        """Test that generate_grid_accessibility correctly interprets bounds.

        Verifies that the (min_lat, min_lon, max_lat, max_lon) tuple is
        unpacked and consumed properly by the project's grid-generation
        function, and that the resulting DataFrame's coordinate columns
        respect the requested bounding box and grid resolution.
        """
        min_lat, min_lon, max_lat, max_lon = 37.8, -122.3, 37.9, -122.2
        bounds = (min_lat, min_lon, max_lat, max_lon)
        resolution = 3  # small grid so the test stays fast

        # Build a graph whose nodes cover the bounding box so that
        # ox.nearest_nodes can resolve every grid point without raising.
        G = nx.MultiDiGraph()
        corner_nodes = [
            (0, min_lat, min_lon),
            (1, min_lat, max_lon),
            (2, max_lat, min_lon),
            (3, max_lat, max_lon),
        ]
        for node_id, lat, lon in corner_nodes:
            G.add_node(node_id, y=lat, x=lon)

        # Non-empty amenities ensure at least some grid points produce rows,
        # giving us lat/lon columns to inspect.
        amenities = {
            "grocery": gpd.GeoDataFrame(
                geometry=[Point(min_lon, min_lat)], crs="EPSG:4326"
            ),
        }

        df = generate_grid_accessibility(
            bounds,
            amenities,
            G,
            grid_resolution=resolution,
        )

        assert isinstance(df, pd.DataFrame)
        # The grid covers resolution×resolution points; every point should
        # produce a row because the mock graph is valid.
        assert len(df) == resolution * resolution, (
            f"Expected {resolution ** 2} rows, got {len(df)}"
        )
        # Confirm the project code correctly unpacked the bounds: the extreme
        # lat/lon values in the output must match what was passed in.
        assert df["lat"].min() == pytest.approx(min_lat)
        assert df["lat"].max() == pytest.approx(max_lat)
        assert df["lon"].min() == pytest.approx(min_lon)
        assert df["lon"].max() == pytest.approx(max_lon)


class TestDataLoader:
    """Tests for data loading utilities."""

    def test_default_amenities_structure(self) -> None:
        """Test that default amenities are properly defined."""
        assert isinstance(DEFAULT_AMENITIES, dict)
        assert len(DEFAULT_AMENITIES) > 0

        # Check that values are strings
        for key, value in DEFAULT_AMENITIES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)
            # Values should look like OSM tags
            assert "[" in value

    def test_amenity_categories(self) -> None:
        """Test that essential amenities are included."""
        essential = ["grocery", "healthcare", "transit"]
        for amenity in essential:
            assert amenity in DEFAULT_AMENITIES, f"Missing essential amenity: {amenity}"


class TestVisualization:
    """Tests for visualization utilities."""

    def test_color_palette_structure(self) -> None:
        """Test color palette has required keys."""
        from fifteen_minute_city.visualization import COLOR_PALETTE

        required_keys = ["low", "medium", "high", "background", "text"]
        for key in required_keys:
            assert key in COLOR_PALETTE, f"Missing color key: {key}"
            assert COLOR_PALETTE[key].startswith("#"), "Colors should be hex format"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
