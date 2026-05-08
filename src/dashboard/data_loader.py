import logging
import os

import geopandas as gpd
import streamlit as st

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Exception raised for errors in the input data validation."""
    pass


@st.cache_data
def load_geoparquet(file_path: str) -> gpd.GeoDataFrame:
    """
    Load GeoParquet file with caching.

    Args:
        file_path (str): Path to the GeoParquet file.

    Returns:
        gpd.GeoDataFrame: The loaded dataset.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If the data is invalid.
    """
    if not os.path.exists(file_path):
        logger.error(f"GeoParquet file not found at {file_path}")
        raise FileNotFoundError(
            f"Processed data not found at {file_path}. "
            "Please run the pipeline first."
        )

    try:
        gdf = gpd.read_parquet(file_path)
        logger.info(f"Loaded {len(gdf)} records from {file_path}")

        # Validation checks
        required_columns = [
            "geoid",
            "geometry",
            "population",
            "median_income",
            "raw_score",
            "accessibility_score",
            "equity_category",
        ]
        missing = [col for col in required_columns if col not in gdf.columns]
        if missing:
            msg = f"Missing required columns in dataset: {missing}"
            raise ValidationError(msg)

        if gdf.crs is None:
            logger.warning("Dataset missing CRS, assuming EPSG:4326")
            gdf.set_crs("EPSG:4326", inplace=True)
        else:
            current_epsg = gdf.crs.to_epsg()
            if current_epsg != 4326:
                if current_epsg is None:
                    logger.warning(f"Non-standard CRS detected: {gdf.crs}")
                logger.info(f"Reprojecting from {gdf.crs} to EPSG:4326")
                gdf = gdf.to_crs("EPSG:4326")

        return gdf
    except ValidationError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        logger.error(f"Error loading GeoParquet: {str(e)}")
        raise RuntimeError(f"Failed to load processed data: {str(e)}") from e
