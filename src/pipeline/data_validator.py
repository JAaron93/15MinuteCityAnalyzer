import logging
import geopandas as gpd
from typing import List

logger = logging.getLogger(__name__)

class DataValidator:
    """
    Utilities for validating fetched data (FR-1.1.7, FR-1.4.1).
    """

    @staticmethod
    def validate_census_data(df: gpd.GeoDataFrame) -> bool:
        """
        Validates Census block group data.
        """
        if df.empty:
            logger.error("Census data is empty.")
            return False

        # Check for required columns
        required_cols = ["geoid", "geometry", "population", "median_income"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Census data missing columns: {missing_cols}")
            return False

        # Check for null geometries
        null_geoms = df[df.geometry.isnull()]
        if not null_geoms.empty:
            logger.warning(f"Found {len(null_geoms)} Census rows with null geometry. Dropping them.")
            df.dropna(subset=["geometry"], inplace=True)

        # Check for invalid population (negative)
        neg_pop = df[df.population < 0]
        if not neg_pop.empty:
            logger.warning(f"Found {len(neg_pop)} rows with negative population. Setting to 0.")
            df.loc[df.population < 0, "population"] = 0

        logger.info(f"Census data validated: {len(df)} block groups.")
        return True

    @staticmethod
    def validate_osm_data(df: gpd.GeoDataFrame) -> bool:
        """
        Validates OSM POI data.
        """
        if df.empty:
            logger.warning("OSM POI data is empty.")
            return True # Not necessarily an error if no POIs exist in bbox

        if "amenity_type" not in df.columns:
            logger.error("OSM data missing 'amenity_type' column.")
            return False

        # Check for null geometries
        null_geoms = df[df.geometry.isnull()]
        if not null_geoms.empty:
            logger.warning(f"Found {len(null_geoms)} OSM rows with null geometry. Dropping them.")
            df.dropna(subset=["geometry"], inplace=True)

    @staticmethod
    def validate_crs(df: gpd.GeoDataFrame, expected_crs: str = "EPSG:4326") -> bool:
        """
        Verifies coordinate reference system (FR-1.4.1).
        """
        if df.crs is None:
            logger.warning(f"Data has no CRS. Setting to {expected_crs}.")
            df.set_crs(expected_crs, inplace=True)
            return True
        
        if df.crs.to_string() != expected_crs:
            logger.warning(f"Data has CRS {df.crs}, expected {expected_crs}. Re-projecting.")
            df.to_crs(expected_crs, inplace=True)
        
        return True

    @staticmethod
    def repair_geometries(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Repairs invalid geometries using buffer(0) technique (2.3.5).
        """
        invalid_count = (~df.is_valid).sum()
        if invalid_count > 0:
            logger.warning(f"Repairing {invalid_count} invalid geometries.")
            df.geometry = df.geometry.buffer(0)
        return df

    @staticmethod
    def validate_demographics(df: gpd.GeoDataFrame) -> bool:
        """
        Checks for missing or invalid demographic data (2.3.4).
        """
        missing_pop = df["population"].isnull().sum()
        missing_income = df["median_income"].isnull().sum()
        
        if missing_pop > 0 or missing_income > 0:
            logger.warning(f"Missing demographics: population={missing_pop}, income={missing_income}.")
            # Fill missing population with 0
            df["population"] = df["population"].fillna(0)
            # Median income is trickier, maybe leave as null or fill with median of others
            # For now, let's keep as is but log.
            
        return True
