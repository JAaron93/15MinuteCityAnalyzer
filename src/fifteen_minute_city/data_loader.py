"""Data loading utilities for OpenStreetMap and geospatial data."""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import osmnx as ox
import pandas as pd
import re
import unicodedata
from shapely.geometry import Polygon


logger = logging.getLogger(__name__)


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Return a filesystem-safe version of *name* suitable for use in filenames.

    Steps applied in order:
    1. Normalize Unicode to NFKD and encode to ASCII (replaces accented
       characters, ligatures, etc. with their closest ASCII equivalents).
    2. Replace path separators (/ and \\) and characters outside
       ``[A-Za-z0-9._-]`` with underscores.
    3. Compress consecutive underscores to a single one.
    4. Strip leading/trailing underscores and dots.
    5. Truncate to *max_length* characters.
    6. Fall back to ``_unnamed_`` if the result is empty.

    Args:
        name: Arbitrary string to sanitize (e.g. a city name).
        max_length: Maximum number of characters in the returned string.

    Returns:
        A non-empty string safe for use as a filename component.
    """
    # Step 1 — normalize Unicode and drop non-ASCII code points
    normalized = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", errors="ignore")
        .decode("ascii")
    )
    # Step 2 — replace unsafe characters (including path separators) with '_'
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", normalized)
    # Step 3 — compress runs of underscores
    safe = re.sub(r"_+", "_", safe)
    # Step 4 — strip leading/trailing underscores and dots
    safe = safe.strip("_. ")
    # Step 5 — enforce maximum length
    safe = safe[:max_length]
    # Step 6 — guarantee a non-empty result
    return safe or "_unnamed_"


DEFAULT_AMENITIES: Dict[str, str] = {
    "grocery": "[shop=supermarket]",
    "healthcare": "[amenity=hospital][amenity=clinic][amenity=doctors]",
    "transit": "[railway=station][highway=bus_stop]",
    "schools": "[amenity=school][amenity=kindergarten]",
    "parks": "[leisure=park][leisure=garden][natural=wood]",
    "pharmacy": "[amenity=pharmacy]",
}


def download_city_network(
    city_name: str,
    network_type: str = "walk",
    data_dir: Optional[Path] = None,
) -> Tuple[Any, Any]:
    """Download walking network for a city using OSMnx.

    Args:
        city_name: Name of the city (e.g., "Berkeley, California, USA")
        network_type: Type of network ('walk', 'drive', 'bike')
        data_dir: Directory to cache downloaded data

    Returns:
        Tuple of (graph, area_boundary)
    """
    ox.config(log_console=True, use_cache=True)

    # Get the city boundary
    area_boundary = ox.geocode_to_gdf(city_name)

    # Download the street network
    graph = ox.graph_from_place(city_name, network_type=network_type)

    if data_dir:
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        safe_city_name = sanitize_filename(city_name)
        ox.save_graphml(graph, filepath=data_dir / f"{safe_city_name}_network.graphml")

    return graph, area_boundary


def get_amenities(
    city_name: str,
    amenity_tags: Optional[Dict[str, str]] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, gpd.GeoDataFrame]:
    """Download amenity locations from OpenStreetMap.

    Args:
        city_name: Name of the city
        amenity_tags: Dict of amenity name to OSM tag query
        data_dir: Directory to save raw data

    Returns:
        Dictionary of amenity type to GeoDataFrame
    """
    tags = amenity_tags or DEFAULT_AMENITIES
    results = {}

    if data_dir:
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

    for name, tag_query in tags.items():
        try:
            # Parse the tag query
            # Simple parser for [key=value][key2=value2] format
            tags_dict = {}
            for part in tag_query.strip("[]").split("]["):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k in tags_dict:
                        if not isinstance(tags_dict[k], list):
                            tags_dict[k] = [tags_dict[k]]
                        tags_dict[k].append(v)
                    else:
                        tags_dict[k] = v

            gdf = ox.geometries_from_place(city_name, tags_dict)

            if data_dir:
                gdf.to_file(data_dir / f"{name}.geojson", driver="GeoJSON")

            results[name] = gdf
        except Exception as e:
            logger.warning(f"Could not fetch {name}: {e}", exc_info=True)
            results[name] = gpd.GeoDataFrame()

    return results


def load_processed_data(
    data_dir: Path,
    filename: str = "accessibility_data.parquet",
) -> Optional[pd.DataFrame]:
    """Load pre-computed accessibility data.

    Args:
        data_dir: Directory containing processed data
        filename: Name of the parquet file

    Returns:
        DataFrame with accessibility data or None if not found
    """
    filepath = Path(data_dir) / filename
    if not filepath.exists():
        return None
    return pd.read_parquet(filepath)


def save_processed_data(
    df: pd.DataFrame,
    data_dir: Path,
    filename: str = "accessibility_data.parquet",
) -> Path:
    """Save processed accessibility data.

    Args:
        df: DataFrame to save
        data_dir: Directory for processed data
        filename: Name of the output file

    Returns:
        Path to saved file
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    filepath = data_dir / filename
    df.to_parquet(filepath, index=False)
    return filepath
