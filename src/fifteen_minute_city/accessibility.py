"""15-minute city accessibility calculations."""

import logging
from typing import Any, Dict, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Point


logger = logging.getLogger(__name__)

# Walking speed in meters per minute (average human walking speed ~5 km/h = 83 m/min)
WALKING_SPEED_MPM = 83.0
DEFAULT_TIME_MINUTES = 15


def calculate_walking_isochrones(
    graph: nx.MultiDiGraph,
    center_point: Tuple[float, float],
    time_minutes: int = DEFAULT_TIME_MINUTES,
    walking_speed_mpm: float = WALKING_SPEED_MPM,
) -> gpd.GeoDataFrame:
    """Calculate 15-minute walking coverage from a center point.

    Args:
        graph: OSMnx street network graph
        center_point: (lat, lon) tuple
        time_minutes: Time threshold for isochrone
        walking_speed_mpm: Walking speed in meters per minute

    Returns:
        GeoDataFrame with isochrone polygon
    """
    # Get nearest node to center point
    center_node = ox.nearest_nodes(graph, center_point[1], center_point[0])

    # Calculate distances from center node (convert time to distance for cutoff)
    max_distance = time_minutes * walking_speed_mpm
    distances = nx.single_source_dijkstra_path_length(
        graph, center_node, cutoff=max_distance, weight="length"
    )

    # All nodes returned are within max_distance due to cutoff
    reachable_nodes = list(distances.keys())

    # Get node coordinates
    node_coords = []
    for node in reachable_nodes:
        y = graph.nodes[node]["y"]
        x = graph.nodes[node]["x"]
        node_coords.append((x, y))

    if not node_coords:
        return gpd.GeoDataFrame(
            columns=["time_minutes", "center_lat", "center_lon", "geometry"],
            crs="EPSG:4326",
            geometry="geometry",
        )

    # Create convex hull polygon from reachable nodes
    points = [Point(x, y) for x, y in node_coords]
    gdf = gpd.GeoDataFrame(geometry=points, crs="EPSG:4326")

    # Buffer points slightly and get convex hull
    gdf_buffered = gdf.buffer(0.0001)  # Small buffer for visualization
    isochrone = gdf_buffered.unary_union.convex_hull

    result = gpd.GeoDataFrame(
        geometry=[isochrone],
        data={
            "time_minutes": [time_minutes],
            "center_lat": [center_point[0]],
            "center_lon": [center_point[1]],
        },
        crs="EPSG:4326",
    )

    return result


def calculate_accessibility_score(
    point: Tuple[float, float],
    amenities: Dict[str, gpd.GeoDataFrame],
    graph: nx.MultiDiGraph,
    time_threshold_minutes: int = DEFAULT_TIME_MINUTES,
    walking_speed_mpm: float = WALKING_SPEED_MPM,
) -> Dict[str, Any]:
    """Calculate accessibility score for a single point.

    Args:
        point: (lat, lon) tuple
        amenities: Dictionary of amenity GeoDataFrames
        graph: OSMnx street network
        time_threshold_minutes: Time threshold for access
        walking_speed_mpm: Walking speed in meters per minute

    Returns:
        Dictionary with accessibility metrics
    """
    max_distance = time_threshold_minutes * walking_speed_mpm

    # Get nearest node to the point
    nearest_node = ox.nearest_nodes(graph, point[1], point[0])

    # Calculate distances to all nodes
    try:
        distances = nx.single_source_dijkstra_path_length(
            graph, nearest_node, cutoff=max_distance, weight="length"
        )
    except nx.NetworkXError:
        # Node not reachable
        distances = {nearest_node: 0}

    # For each amenity type, count how many are reachable
    scores = {}
    for amenity_type, gdf in amenities.items():
        if gdf.empty:
            scores[amenity_type] = 0
            continue

        # Count amenities within walking distance
        count = 0
        min_time = float("inf")

        # Collect coordinates for all valid geometries in this amenity type
        amenity_coords = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue

            # Get centroid for polygons
            if geom.geom_type in ["Polygon", "MultiPolygon"]:
                amenity_point = geom.centroid
            elif geom.geom_type == "Point":
                amenity_point = geom
            else:
                continue
            amenity_coords.append((amenity_point.x, amenity_point.y))

        if not amenity_coords:
            scores[amenity_type] = {"count": 0, "min_time": None}
            continue

        # Find nearest nodes to all amenities in one vectorized call
        xs = [c[0] for c in amenity_coords]
        ys = [c[1] for c in amenity_coords]
        try:
            amenity_nodes = ox.nearest_nodes(graph, xs, ys)

            for amenity_node in amenity_nodes:
                if amenity_node in distances:
                    distance_m = distances[amenity_node]
                    time_min = distance_m / walking_speed_mpm
                    if time_min <= time_threshold_minutes:
                        count += 1
                        min_time = min(min_time, time_min)
        except Exception:
            # Handle potential OSMnx errors in vectorized call
            pass

        scores[amenity_type] = {
            "count": count,
            "min_time": min_time if min_time < float("inf") else None,
        }

    # Calculate overall score (simple average of normalized scores)
    overall_score = 0
    n_categories = len(scores)

    for cat, metrics in scores.items():
        if isinstance(metrics, dict):
            # Score based on count (1 = good, 0 = poor)
            cat_score = min(metrics["count"], 1) * 100
            overall_score += cat_score

    overall_score = overall_score / n_categories if n_categories > 0 else 0

    return {
        "lat": point[0],
        "lon": point[1],
        "overall_score": overall_score,
        "amenities": scores,
        "time_threshold": time_threshold_minutes,
    }


def generate_grid_accessibility(
    bounds: Tuple[float, float, float, float],
    amenities: Dict[str, gpd.GeoDataFrame],
    graph: nx.MultiDiGraph,
    grid_resolution: int = 20,
    time_threshold_minutes: int = DEFAULT_TIME_MINUTES,
) -> pd.DataFrame:
    """Generate accessibility scores across a grid.

    Args:
        bounds: (min_lat, min_lon, max_lat, max_lon) bounding box
        amenities: Dictionary of amenity GeoDataFrames
        graph: OSMnx street network
        grid_resolution: Number of points per dimension
        time_threshold_minutes: Walking time threshold

    Returns:
        DataFrame with grid points and accessibility scores
    """
    min_lat, min_lon, max_lat, max_lon = bounds

    # Generate grid points
    lats = np.linspace(min_lat, max_lat, grid_resolution)
    lons = np.linspace(min_lon, max_lon, grid_resolution)

    results = []
    for lat in lats:
        for lon in lons:
            try:
                score = calculate_accessibility_score(
                    (lat, lon),
                    amenities,
                    graph,
                    time_threshold_minutes,
                )
                results.append(score)
            except Exception:
                logger.debug(
                    "Skipping grid point (lat=%.6f, lon=%.6f): %s",
                    lat,
                    lon,
                    exc_info=True,
                )
                continue

    return pd.DataFrame(results)


def calculate_equity_metrics(
    accessibility_df: pd.DataFrame,
    neighborhoods: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Calculate transit equity metrics by neighborhood.

    Args:
        accessibility_df: DataFrame with accessibility scores per grid point
        neighborhoods: GeoDataFrame with neighborhood boundaries and names

    Returns:
        DataFrame with equity metrics per neighborhood
    """
    # Validate required columns before any DataFrame construction so that
    # missing columns raise a clear ValueError rather than a cryptic
    # AttributeError inside gpd.points_from_xy or a KeyError inside
    # gpd.sjoin / joined.groupby("name").
    required_accessibility_cols = {"lat", "lon", "overall_score"}
    missing_accessibility = required_accessibility_cols - set(accessibility_df.columns)
    if missing_accessibility:
        raise ValueError(
            f"accessibility_df is missing required column(s): {sorted(missing_accessibility)}. "
            f"Present columns: {list(accessibility_df.columns)}"
        )

    if "name" not in neighborhoods.columns:
        raise ValueError(
            f"neighborhoods is missing the required 'name' column. "
            f"Present columns: {list(neighborhoods.columns)}"
        )

    # Convert accessibility points to GeoDataFrame
    points_gdf = gpd.GeoDataFrame(
        accessibility_df,
        geometry=gpd.points_from_xy(
            accessibility_df.lon, accessibility_df.lat
        ),
        crs="EPSG:4326",
    )

    # Spatial join with neighborhoods.
    # "intersects" is used instead of "within" so that points lying exactly
    # on a neighborhood boundary are included rather than silently dropped.
    # When neighborhoods overlap a point can match more than one polygon, so
    # we deduplicate immediately: keep the first match per original point
    # index (deterministic tie-break by neighborhood index order).
    joined = gpd.sjoin(points_gdf, neighborhoods, predicate="intersects")
    joined = joined[~joined.index.duplicated(keep="first")]

    # Calculate metrics per neighborhood
    metrics = []
    for name, group in joined.groupby("name"):
        scores = group["overall_score"]
        metrics.append(
            {
                "neighborhood": name,
                "mean_score": scores.mean(),
                "median_score": scores.median(),
                "min_score": scores.min(),
                "max_score": scores.max(),
                "std_score": scores.std(),
                "pct_above_80": (scores >= 80).mean() * 100,
                "pct_below_40": (scores < 40).mean() * 100,
            }
        )

    return pd.DataFrame(metrics)
