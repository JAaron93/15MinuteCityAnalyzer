"""CRS transformation utilities for the 15-Minute City pipeline.

Handles coordinate reference system conversions between WGS84 (EPSG:4326) for
input/output and local UTM for accurate distance and area calculations.

References:
    - FR-1.2.2: Area calculations in local UTM projection
    - FR-1.2.5: CRS transformation correctness
    - Design §CRS Transformation Workflow
"""

import logging
from typing import Tuple, Union

import geopandas as gpd
from pyproj import CRS

logger = logging.getLogger(__name__)

WGS84 = CRS.from_epsg(4326)


class CRSTransformationError(Exception):
    """Raised when a CRS transformation fails."""

    pass


def determine_utm_zone(
    bbox: Tuple[float, float, float, float],
) -> CRS:
    """Determine the local UTM CRS from the analysis bounding box centroid.

    Computes the centroid of the bounding box in WGS84 and derives the
    appropriate UTM zone using ``geopandas.GeoDataFrame.estimate_utm_crs``.
    This ensures deterministic, consistent projection across a single pipeline
    run (FR-1.2.2).

    Args:
        bbox: Bounding box as ``(north, south, east, west)`` in WGS84
            decimal degrees.

    Returns:
        The estimated UTM CRS for the bounding box centroid.

    Raises:
        CRSTransformationError: If the UTM zone cannot be determined.
    """
    try:
        north, south, east, west = bbox
        
        # Validate coordinate ranges
        if not (-90 <= south <= north <= 90):
            raise ValueError(f"Invalid latitude range: south={south}, north={north}")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError(f"Invalid longitude range: west={west}, east={east}")
        if west > east:
            raise ValueError(
                f"Antimeridian-crossing bounding boxes not supported: west={west}, east={east}"
            )
        
        centroid_lat = (north + south) / 2.0
        centroid_lon = (east + west) / 2.0

        # Create a minimal GeoDataFrame at the centroid to use estimate_utm_crs
        from shapely.geometry import Point

        centroid_gdf = gpd.GeoDataFrame(
            geometry=[Point(centroid_lon, centroid_lat)],
            crs="EPSG:4326",
        )
        utm_crs = centroid_gdf.estimate_utm_crs()

        logger.info(
            f"Determined UTM CRS: {utm_crs} "
            f"(centroid: {centroid_lat:.4f}, {centroid_lon:.4f})"
        )
        return utm_crs

    except Exception as e:
        msg = f"Failed to determine UTM zone for bbox {bbox}: {e}"
        logger.error(msg)
        raise CRSTransformationError(msg) from e


def transform_to_utm(
    gdf: gpd.GeoDataFrame,
    utm_crs: CRS,
) -> gpd.GeoDataFrame:
    """Transform a GeoDataFrame from WGS84 to a local UTM projection.

    Args:
        gdf: GeoDataFrame in WGS84 (EPSG:4326).
        utm_crs: Target UTM CRS (obtained from :func:`determine_utm_zone`).

    Returns:
        A new GeoDataFrame reprojected to the UTM CRS.

    Raises:
        CRSTransformationError: If the transformation fails.

    Note:
        If the GeoDataFrame has no CRS, WGS84 (EPSG:4326) is assumed.
    """
    if gdf.empty:
        logger.warning("Cannot transform empty GeoDataFrame to UTM.")
        return gdf.copy()

    try:
        if gdf.crs is None:
            logger.warning("GeoDataFrame has no CRS; assuming WGS84 (EPSG:4326).")
            gdf = gdf.set_crs("EPSG:4326")

        result = gdf.to_crs(utm_crs)
        logger.debug(f"Transformed {len(result)} features from {gdf.crs} to {utm_crs}")
        return result

    except Exception as e:
        msg = f"CRS transformation to UTM ({utm_crs}) failed: {e}"
        logger.error(msg)
        raise CRSTransformationError(msg) from e


def transform_to_wgs84(
    gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Transform a GeoDataFrame back to WGS84 (EPSG:4326).

    Args:
        gdf: GeoDataFrame in any projected CRS.

    Returns:
        A new GeoDataFrame reprojected to WGS84.

    Raises:
        CRSTransformationError: If the transformation fails.
    """
    if gdf.empty:
        logger.warning("Cannot transform empty GeoDataFrame to WGS84.")
        return gdf.copy()

    try:
        if gdf.crs is None:
            logger.warning(
                "GeoDataFrame has no CRS; setting to WGS84 without reprojection."
            )
            return gdf.set_crs("EPSG:4326")

        result = gdf.to_crs("EPSG:4326")
        logger.debug(f"Transformed {len(result)} features from {gdf.crs} to WGS84")
        return result

    except Exception as e:
        msg = f"CRS transformation to WGS84 failed: {e}"
        logger.error(msg)
        raise CRSTransformationError(msg) from e


def validate_wgs84(gdf: gpd.GeoDataFrame) -> None:
    """Validate that a GeoDataFrame is in WGS84 (EPSG:4326).

    Args:
        gdf: GeoDataFrame to validate.

    Raises:
        CRSTransformationError: If the CRS is not WGS84.
    """
    if gdf.crs is None:
        raise CRSTransformationError(
            "GeoDataFrame has no CRS set. Expected EPSG:4326."
        )

    if not gdf.crs.equals(WGS84):
        raise CRSTransformationError(
            f"GeoDataFrame CRS is {gdf.crs}, expected EPSG:4326 (WGS84). "
            f"Use transform_to_wgs84() before export."
        )

    logger.debug("CRS validation passed: EPSG:4326 (WGS84)")
