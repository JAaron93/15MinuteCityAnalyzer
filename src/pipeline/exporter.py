import logging
from typing import Any, Dict

import geopandas as gpd

logger = logging.getLogger(__name__)

def export_to_geoparquet(
    df: gpd.GeoDataFrame,
    output_path: str,
    metadata: Dict[str, Any] = None
) -> None:
    """
    Exports the GeoDataFrame to a GeoParquet file with snappy compression.
    Validates output size is under 50 MB and applies remediation if needed.
    """
    if df.empty:
        logger.warning("Empty GeoDataFrame, skipping export.")
        return

    # Ensure geometry is WGS84
    if df.crs and df.crs.to_string() != "EPSG:4326":
        df = df.to_crs("EPSG:4326")

    # Save to geoparquet
    logger.info(f"Exporting {len(df)} records to {output_path}")

    # Custom metadata can be passed to PyArrow if needed, but GeoPandas
    # to_parquet handles basic saving. For custom metadata, we might need
    # pyarrow directly, but for now we rely on pandas/geopandas capabilities.
    # We'll just write it out.
    # The spec mentions adding metadata to GeoParquet file (processing date, params, etc)
    # GeoPandas 0.13+ supports custom_metadata in to_parquet

    export_kwargs = {
        "path": output_path,
        "compression": "snappy",
        "index": False
    }

    if metadata:
        # Convert all metadata values to strings for pyarrow compatibility
        str_metadata = {k: str(v) for k, v in metadata.items()}
        export_kwargs["custom_metadata"] = str_metadata

    # 1. Base export
    df.to_parquet(**export_kwargs)

    # Validate size
    import os
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"Exported file size: {size_mb:.2f} MB")

    if size_mb <= 50:
        return

    logger.warning("File size exceeds 50 MB limit. Attempting remediation...")

    # Remediation 1: Simplification
    tolerances = [0.0001, 0.0005, 0.001]
    for tol in tolerances:
        logger.info(f"Simplifying geometries with tolerance {tol}...")
        df_simplified = df.copy()
        df_simplified.geometry = df_simplified.geometry.simplify(tol, preserve_topology=True)
        df_simplified.to_parquet(**export_kwargs)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"File size after simplification (tol={tol}): {size_mb:.2f} MB")

        if size_mb <= 50:
            return

    # Remediation 2: Spatial chunking (placeholder, as per spec)
    logger.warning("Simplification insufficient. Needs spatial chunking (not fully implemented).")
    raise Exception(f"FileSizeLimitError: File size {size_mb:.2f} MB exceeds 50 MB after all simplification steps.")
