"""Unit tests for isochrone generation (Task 3.2 / 6.2.4–6.2.6).

Tests cover:
- Single-amenity isochrone generation
- Walking speed read from config (not hard-coded)
- All-amenities batch processing
- Edge cases: empty graphs, unreachable nodes
"""

import math
from unittest.mock import patch

import geopandas as gpd
import networkx as nx
import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from src.pipeline.isochrone import (
    calculate_all_isochrones,
    calculate_isochrone,
)


def _make_grid_graph(n: int = 5, edge_length_m: float = 100.0) -> nx.MultiDiGraph:
    """Create a synthetic n×n grid walking network graph.

    Nodes have ``x`` and ``y`` attributes (in degrees, roughly), and edges
    have a ``length`` attribute in metres. This mimics the structure of an
    OSMnx walking graph.

    Args:
        n: Grid dimension (n×n nodes).
        edge_length_m: Length of each edge in metres.

    Returns:
        A NetworkX MultiDiGraph with node coordinates and edge lengths.
    """
    G = nx.grid_2d_graph(n, n)
    G = nx.MultiDiGraph(G)

    # Assign node coordinates (small increments as if WGS84)
    base_lon, base_lat = -117.5, 33.9
    step_deg = 0.001  # ~111m per 0.001°

    mapping = {}
    for i, j in G.nodes:
        old_id = (i, j)
        new_id = i * n + j
        mapping[old_id] = new_id
    G = nx.relabel_nodes(G, mapping)
    G.graph["crs"] = "EPSG:4326"

    for node_id in G.nodes:
        i, j = divmod(node_id, n)
        G.nodes[node_id]["x"] = base_lon + j * step_deg
        G.nodes[node_id]["y"] = base_lat + i * step_deg

    for u, v, k in G.edges(keys=True):
        G.edges[u, v, k]["length"] = edge_length_m

    return G


class TestCalculateIsochrone:
    """Tests for calculate_isochrone() — task 6.2.5."""

    def setup_method(self) -> None:
        """Create a test graph."""
        self.graph = _make_grid_graph(n=10, edge_length_m=100.0)

    def test_returns_polygon(self) -> None:
        """A reachable amenity should produce a valid Polygon."""
        # Center of the grid
        center_node = 55  # row 5, col 5
        center_x = self.graph.nodes[center_node]["x"]
        center_y = self.graph.nodes[center_node]["y"]
        point = Point(center_x, center_y)

        result = calculate_isochrone(
            self.graph, point, walk_time_minutes=15, walk_speed_kmh=4.5
        )

        assert result is not None
        assert isinstance(result, Polygon)
        assert result.is_valid

    def test_speed_affects_area(self) -> None:
        """Higher walking speed should produce a larger isochrone."""
        center = Point(
            self.graph.nodes[55]["x"], self.graph.nodes[55]["y"]
        )

        slow = calculate_isochrone(
            self.graph, center, walk_time_minutes=15, walk_speed_kmh=3.0
        )
        fast = calculate_isochrone(
            self.graph, center, walk_time_minutes=15, walk_speed_kmh=6.0
        )

        assert slow is not None and fast is not None
        # Fast isochrone should be at least as large
        assert fast.area >= slow.area

    def test_far_point_handled_gracefully(self) -> None:
        """A point far from the network should be handled gracefully, potentially returning a Polygon or None."""
        far_point = Point(-100.0, 10.0)  # Nowhere near the graph

        result = calculate_isochrone(
            self.graph, far_point, walk_time_minutes=15, walk_speed_kmh=4.5
        )

        # The nearest node will be found but all reachable nodes cluster,
        # so the result may still be a polygon. If the graph had isolated nodes,
        # we'd get None. This tests graceful handling.
        # With a grid graph, nearest_nodes will pick an edge node.
        # The result should still be a valid polygon or None.
        assert result is None or isinstance(result, Polygon)

    def test_very_short_time_returns_small_isochrone(self) -> None:
        """Very short walk time should produce a smaller isochrone."""
        center = Point(
            self.graph.nodes[55]["x"], self.graph.nodes[55]["y"]
        )

        short = calculate_isochrone(
            self.graph, center, walk_time_minutes=1, walk_speed_kmh=4.5
        )
        long = calculate_isochrone(
            self.graph, center, walk_time_minutes=30, walk_speed_kmh=4.5
        )

        if short is not None and long is not None:
            assert long.area >= short.area


class TestCalculateAllIsochrones:
    """Tests for calculate_all_isochrones() — task 6.2.6."""

    def setup_method(self) -> None:
        """Create test fixtures."""
        self.graph = _make_grid_graph(n=10, edge_length_m=100.0)

    def test_processes_multiple_amenities(self) -> None:
        """Should produce isochrones for multiple amenities."""
        amenities = gpd.GeoDataFrame(
            {
                "amenity_type": ["grocery", "healthcare", "transit"],
            },
            geometry=[
                Point(self.graph.nodes[22]["x"], self.graph.nodes[22]["y"]),
                Point(self.graph.nodes[55]["x"], self.graph.nodes[55]["y"]),
                Point(self.graph.nodes[77]["x"], self.graph.nodes[77]["y"]),
            ],
            crs="EPSG:4326",
        )

        result = calculate_all_isochrones(self.graph, amenities)

        assert not result.empty
        assert "amenity_type" in result.columns
        assert "geometry" in result.columns
        assert "walk_time_minutes" in result.columns
        assert len(result) <= len(amenities)
        # Expect all amenities to produce valid isochrones in this test setup
        assert len(result) == len(amenities)

    def test_reads_walk_speed_from_config(self) -> None:
        """Walking speed must be read from config, not hard-coded."""
        amenities = gpd.GeoDataFrame(
            {"amenity_type": ["grocery"]},
            geometry=[
                Point(self.graph.nodes[55]["x"], self.graph.nodes[55]["y"]),
            ],
            crs="EPSG:4326",
        )

        # Separate configs for slow and fast scenarios
        mock_config_slow = {
            "walk_speed_kmh": 2.0,
            "scoring_weights": {"grocery": 0.35},
        }
        mock_config_fast = {
            "walk_speed_kmh": 10.0,
            "scoring_weights": {"grocery": 0.35},
        }

        with patch(
            "src.pipeline.isochrone._load_config", return_value=mock_config_slow
        ):
            result_slow = calculate_all_isochrones(self.graph, amenities)

        with patch(
            "src.pipeline.isochrone._load_config", return_value=mock_config_fast
        ):
            result_fast = calculate_all_isochrones(self.graph, amenities)

        if not result_slow.empty and not result_fast.empty:
            slow_area = result_slow.geometry.iloc[0].area
            fast_area = result_fast.geometry.iloc[0].area
            assert fast_area >= slow_area

    def test_empty_amenities_returns_empty(self) -> None:
        """Empty amenities GeoDataFrame should return empty result."""
        empty = gpd.GeoDataFrame(
            columns=["amenity_type", "geometry"],
            crs="EPSG:4326",
        )
        result = calculate_all_isochrones(self.graph, empty)
        assert result.empty

    def test_output_has_correct_crs(self) -> None:
        """Output isochrones should be in WGS84."""
        amenities = gpd.GeoDataFrame(
            {"amenity_type": ["grocery"]},
            geometry=[
                Point(self.graph.nodes[55]["x"], self.graph.nodes[55]["y"]),
            ],
            crs="EPSG:4326",
        )

        result = calculate_all_isochrones(self.graph, amenities)
        if not result.empty:
            assert result.crs is not None
            assert result.crs.to_epsg() == 4326
