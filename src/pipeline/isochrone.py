"""Isochrone generation for 15-minute walking accessibility analysis.

Calculates walking isochrones (reachability polygons) around amenities using
network analysis on the OSMnx street graph. Each isochrone represents the area
reachable within a configurable walking time (default: 15 minutes at 4.5 km/h).

References:
    - FR-1.2.1: 15-minute walking isochrones
    - Design §Isochrone Generation Algorithm
"""

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import yaml
from shapely.geometry import MultiPoint, Point, Polygon

logger = logging.getLogger(__name__)


# Global variable for sharing the graph among parallel workers
# to avoid repeated pickling (Task 3.2 performance optimization)
_worker_graph: Optional[nx.MultiDiGraph] = None


def _init_worker(graph: nx.MultiDiGraph) -> None:
    """Initialise worker process with the shared graph."""
    global _worker_graph
    _worker_graph = graph


def _load_config(config_path: str = "pipeline_config.yaml") -> Dict[str, Any]:
    """Load pipeline configuration from YAML.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Parsed configuration dictionary.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_graph_crs(graph: nx.MultiDiGraph) -> Any:
    """Safely extract the CRS from an OSMnx graph, with fallback.

    Prefers graph.graph.get("crs") as the primary source of truth, falling back
    to "EPSG:4326" if missing.
    """
    return graph.graph.get("crs") or "EPSG:4326"


def calculate_isochrone(
    graph: nx.MultiDiGraph,
    amenity_point: Point,
    walk_time_minutes: int = 15,
    walk_speed_kmh: float = 4.5,
) -> Optional[Polygon]:
    """Generate a 15-minute walking isochrone for a single amenity.

    Finds the nearest network node to the amenity, computes shortest paths
    to all reachable nodes within the travel time budget, and constructs a
    convex hull around the reachable nodes.

    Args:
        graph: OSMnx walking network graph (``network_type='walk'``).
        amenity_point: Location of the amenity as a Shapely Point (in the
            same CRS as the graph — typically WGS84).
        walk_time_minutes: Maximum walking time in minutes.
        walk_speed_kmh: Walking speed in km/h. Default 4.5 per FR-1.2.1.

    Returns:
        A Polygon representing the isochrone, or ``None`` if the amenity
        cannot be snapped to the network or no nodes are reachable.
    """
    try:
        # Convert walk speed to metres per minute
        walk_speed_m_per_min = (walk_speed_kmh * 1000.0) / 60.0
        max_distance_m = walk_speed_m_per_min * walk_time_minutes

        # Find nearest network node to the amenity point
        nearest_node = ox.distance.nearest_nodes(
            graph, amenity_point.x, amenity_point.y
        )

        # Compute shortest path lengths from the nearest node using edge
        # 'length' attribute (metres) with a distance cutoff
        path_lengths = nx.single_source_dijkstra_path_length(
            graph, nearest_node, cutoff=max_distance_m, weight="length"
        )

        if len(path_lengths) < 3:
            # Need at least 3 points for a valid polygon
            logger.debug(
                f"Fewer than 3 reachable nodes from amenity at "
                f"({amenity_point.x:.4f}, {amenity_point.y:.4f}); skipping."
            )
            return None

        # Collect coordinates of all reachable nodes
        reachable_nodes = list(path_lengths.keys())
        node_coords = [
            (graph.nodes[node]["x"], graph.nodes[node]["y"])
            for node in reachable_nodes
            if "x" in graph.nodes[node] and "y" in graph.nodes[node]
        ]

        if len(node_coords) < 3:
            return None

        # Build convex hull around reachable nodes
        points = MultiPoint(node_coords)
        isochrone_polygon = points.convex_hull

        if isochrone_polygon.is_empty or not isinstance(isochrone_polygon, Polygon):
            return None

        return isochrone_polygon

    except Exception as e:
        logger.warning(
            f"Isochrone calculation failed for amenity at "
            f"({amenity_point.x:.4f}, {amenity_point.y:.4f}): {e}"
        )
        return None


def _calculate_single_isochrone_worker(
    args: Tuple[Any, ...],
) -> Optional[Dict[str, Any]]:
    """Worker function for parallel isochrone processing.

    Unpacks arguments and calls :func:`calculate_isochrone`. Designed to be
    called via ``ProcessPoolExecutor``.

    Args:
        args: Tuple of ``(amenity_point, amenity_type, amenity_id,
            walk_time_minutes, walk_speed_kmh)``.

    Returns:
        A dictionary with isochrone data, or ``None`` on failure.
    """
    (
        amenity_point,
        amenity_type,
        amenity_id,
        walk_time_minutes,
        walk_speed_kmh,
    ) = args

    if _worker_graph is None:
        logger.error("Worker graph not initialized.")
        return None

    polygon = calculate_isochrone(
        _worker_graph, amenity_point, walk_time_minutes, walk_speed_kmh
    )

    if polygon is not None:
        return {
            "amenity_id": amenity_id,
            "amenity_type": amenity_type,
            "geometry": polygon,
            "walk_time_minutes": walk_time_minutes,
        }
    return None


def calculate_all_isochrones(
    graph: nx.MultiDiGraph,
    amenities: gpd.GeoDataFrame,
    walk_time_minutes: int = 15,
    config_path: str = "pipeline_config.yaml",
    max_workers: Optional[int] = None,
) -> gpd.GeoDataFrame:
    """Calculate isochrones for all amenities.

    Processes each amenity sequentially by default or in parallel when
    ``max_workers > 1``. The walking speed is read from ``pipeline_config.yaml``
    (``walk_speed_kmh``, default 4.5 km/h) — it is never hard-coded (FR-1.2.1,
    task 3.2.3).

    Args:
        graph: OSMnx walking network graph.
        amenities: GeoDataFrame of amenities with ``geometry`` (Point) and
            ``amenity_type`` columns.
        walk_time_minutes: Maximum walking time in minutes.
        config_path: Path to the pipeline configuration file.
        max_workers: Number of parallel workers. ``None`` or ``1`` for
            sequential processing.

    Returns:
        GeoDataFrame with columns ``[amenity_id, amenity_type, geometry,
        walk_time_minutes]``. The geometry column contains the isochrone
        polygons in the same CRS as the input graph (typically WGS84).
    """
    config = _load_config(config_path)
    walk_speed_kmh: float = config.get("walk_speed_kmh", 4.5)

    logger.info(
        f"Calculating isochrones for {len(amenities)} amenities "
        f"(walk_speed={walk_speed_kmh} km/h, time={walk_time_minutes} min, "
        f"workers={max_workers or 1})"
    )

    results: List[Dict[str, Any]] = []

    if max_workers and max_workers > 1:
        # Parallel processing
        # NOTE: NetworkX graphs are not pickle-safe by default in all cases.
        # For large graphs, consider using threading or shared-memory approaches.
        # Here we attempt multiprocessing; fall back to sequential on failure.
        try:
            tasks = []
            for idx, row in amenities.iterrows():
                point = row.geometry
                if not isinstance(point, Point):
                    # For polygon/multipolygon amenities, use centroid
                    point = point.centroid
                amenity_type = row.get("amenity_type", "unknown")
                tasks.append(
                    (
                        point,
                        amenity_type,
                        idx,
                        walk_time_minutes,
                        walk_speed_kmh,
                    )
                )

            with ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=_init_worker,
                initargs=(graph,),
            ) as executor:
                futures = {
                    executor.submit(_calculate_single_isochrone_worker, t): i
                    for i, t in enumerate(tasks)
                }
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    if completed % 100 == 0:
                        logger.info(
                            f"Isochrone progress: {completed}/{len(tasks)}"
                        )
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        logger.warning(
                            f"Individual isochrone task failed: {e}"
                        )

        except Exception as e:
            logger.warning(
                f"Parallel processing failed ({e}); falling back to sequential."
            )
            results = _calculate_sequential(
                graph, amenities, walk_time_minutes, walk_speed_kmh
            )
    else:
        results = _calculate_sequential(
            graph, amenities, walk_time_minutes, walk_speed_kmh
        )

    if not results:
        logger.warning("No isochrones could be generated for any amenity.")
        empty_gdf = gpd.GeoDataFrame(
            columns=["amenity_id", "amenity_type", "geometry", "walk_time_minutes"],
        )
        # Inherit CRS from the graph
        return empty_gdf.set_crs(_get_graph_crs(graph))

    isochrones_gdf = gpd.GeoDataFrame(results, geometry="geometry")

    # Inherit CRS from the graph (OSMnx graphs are WGS84 by default)
    isochrones_gdf = isochrones_gdf.set_crs(_get_graph_crs(graph))

    logger.info(
        f"Generated {len(isochrones_gdf)} isochrones out of "
        f"{len(amenities)} amenities."
    )

    return isochrones_gdf


def _calculate_sequential(
    graph: nx.MultiDiGraph,
    amenities: gpd.GeoDataFrame,
    walk_time_minutes: int,
    walk_speed_kmh: float,
) -> List[Dict[str, Any]]:
    """Calculate isochrones sequentially with progress logging.

    Args:
        graph: Walking network graph.
        amenities: GeoDataFrame of amenities.
        walk_time_minutes: Walking time budget.
        walk_speed_kmh: Walking speed.

    Returns:
        List of isochrone result dictionaries.
    """
    results: List[Dict[str, Any]] = []
    total = len(amenities)

    for i, (idx, row) in enumerate(amenities.iterrows()):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info(f"Isochrone progress: {i + 1}/{total}")

        point = row.geometry
        if not isinstance(point, Point):
            point = point.centroid

        amenity_type = row.get("amenity_type", "unknown")

        polygon = calculate_isochrone(
            graph, point, walk_time_minutes, walk_speed_kmh
        )

        if polygon is not None:
            results.append(
                {
                    "amenity_id": idx,
                    "amenity_type": amenity_type,
                    "geometry": polygon,
                    "walk_time_minutes": walk_time_minutes,
                }
            )

    return results
