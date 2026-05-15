import logging
import os
from typing import List, Tuple

import cenpy
import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import box

from src.pipeline.data_validator import DataValidator
from src.pipeline.utils import retry_with_policy

logger = logging.getLogger(__name__)


class CensusFetcher:
    """
    Fetches Census block group data and demographics (FR-1.1.1, FR-1.1.7).
    """

    def __init__(self, config_path: str = "pipeline_config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.retry_policy = self.config.get("retry_policy", {})
        self.api_key = os.getenv("CENSUS_API_KEY")
        self.census_year = self.config.get("census_year", 2021)

        # Demographic variables from DR-3.1.4
        self.variables = {"B01003_001E": "population", "B19013_001E": "median_income"}

    def fetch_data(
        self, state: str, bbox: Tuple[float, float, float, float]
    ) -> gpd.GeoDataFrame:
        """
        Main entry point for fetching Census data for a given state and bounding box.
        Handles multi-county detection and merging (FR-1.1.7).
        """
        # 1. Identify counties intersecting the bounding box
        counties = self._identify_counties(state, bbox)
        logger.info(f"Identified counties in bbox: {counties}")

        if not counties:
            logger.warning("No counties identified for the given bounding box.")
            return gpd.GeoDataFrame()

        # 2. Fetch data per county
        all_county_data = []
        missing_counties = []

        for county_fips in counties:
            try:
                county_df = self._fetch_county_block_groups(state, county_fips)
                if not county_df.empty:
                    all_county_data.append(county_df)
                else:
                    missing_counties.append(county_fips)
            except Exception as e:
                logger.warning(f"Failed to fetch data for county {county_fips}: {e}")
                missing_counties.append(county_fips)

        if not all_county_data:
            raise Exception(
                f"No Census data returned for any county in {state} for the given bbox."
            )

        if missing_counties:
            logger.warning(f"Census data unavailable for counties: {missing_counties}")

        # 3. Concatenate and Deduplicate (FR-1.1.7 step 3)
        combined_df = pd.concat(all_county_data, ignore_index=True)

        logger.info(
            f"Merging data from {len(all_county_data)} counties. Total rows before dedup: {len(combined_df)}"
        )

        # Deterministic deduplication
        combined_df = combined_df.sort_values(by=["geoid", "state", "county"])

        duplicates = combined_df[combined_df.duplicated(subset="geoid", keep=False)]
        if not duplicates.empty:
            logger.info(
                f"Found {len(duplicates)} duplicate block group IDs across counties."
            )
            self._log_conflicts(duplicates)

        final_df = combined_df.drop_duplicates(subset="geoid", keep="first")

        # Filter to only block groups that actually intersect the bbox
        bbox_geom = box(*bbox)
        # Ensure final_df is in EPSG:4326 for intersection with bbox_geom
        DataValidator.validate_crs(final_df, "EPSG:4326")
        final_df = final_df[final_df.intersects(bbox_geom)]
        logger.info(f"Rows after spatial filter to bbox: {len(final_df)}")

        # 4. Validate data
        DataValidator.validate_census_data(final_df)

        return final_df

    def _identify_counties(
        self, state: str, bbox: Tuple[float, float, float, float]
    ) -> List[str]:
        """
        Identifies which counties intersect the analysis bounding box (FR-1.1.7 step 1).
        """
        # We can use cenpy to get the county boundaries for the state
        # Or a bundled GeoJSON if we had one. Let's use cenpy for now.
        try:
            # Get state FIPS
            state_fips = cenpy.explorer.fips_table(state)
            if state_fips.empty:
                logger.error(f"Could not find FIPS for state: {state}")
                return []

            # Fetch county boundaries for the state
            # Optimization (High): Use from_polygon to fetch only counties intersecting the bbox
            # instead of fetching all counties for the entire state.
            acs = cenpy.products.ACS(self.census_year)
            bbox_geom = box(*bbox)

            # Fetch counties intersecting the bbox
            # level='county' returns county features touching the polygon
            counties_gdf = acs.from_polygon(bbox_geom, level="county")

            if counties_gdf.empty:
                logger.warning("No counties found intersecting the bbox.")
                return []

            # Filter to the specified state if necessary
            # cenpy returns 'state' column with FIPS code
            if "state" in counties_gdf.columns:
                target_state_fips = str(state_fips.iloc[0]["state"]).zfill(2)
                counties_gdf = counties_gdf[
                    counties_gdf["state"].astype(str).str.zfill(2) == target_state_fips
                ]

            # Find the county column (case-insensitive)
            county_col = next(
                (col for col in counties_gdf.columns if col.lower() == "county"), None
            )
            if not county_col:
                logger.error(
                    f"Could not find county column in Census response. Columns: {counties_gdf.columns}"
                )
                return []

            return sorted(counties_gdf[county_col].unique().tolist())

        except Exception as e:
            logger.error(f"Error identifying counties: {e}")
            return []

    def _get_state_fips(self, state: str) -> str:
        """
        Normalizes a state name or abbreviation to a 2-digit FIPS string.

        Raises:
            ValueError: If the state cannot be resolved to a FIPS code.
        """
        if state.isdigit():
            return state.zfill(2)
        try:
            state_fips = cenpy.explorer.fips_table(state)
            if not state_fips.empty:
                return str(state_fips.iloc[0]["state"]).zfill(2)
        except Exception as e:
            logger.warning(f"Failed to lookup state FIPS for '{state}': {e}")
        raise ValueError(f"Could not resolve state '{state}' to a FIPS code")

    def _get_county_fips(self, state: str, county: str) -> str:
        """
        Normalizes a county identifier to a 3-digit FIPS string.
        """
        if county.isdigit():
            return county.zfill(3)
        # If not a digit, we could try to look it up, but cenpy's county lookup
        # is often combined with the fetch. For fallback normalization,
        # we at least ensure it's a string.
        return str(county)

    def _fetch_county_block_groups(self, state: str, county: str) -> gpd.GeoDataFrame:
        """
        Fetches block groups and demographics for a single county (FR-1.1.7 step 2).
        """
        # Normalize state and county to FIPS strings for consistency
        state_fips = self._get_state_fips(state)
        county_fips = self._get_county_fips(state, county)

        from typing import Any
        @retry_with_policy(self.retry_policy)
        def _execute_query(**kwargs: Any) -> gpd.GeoDataFrame:
            acs = cenpy.products.ACS(self.census_year)
            # Fetch block groups for the county
            # cenpy handles the API calls and geometry merging
            df = acs.from_county(
                f"{state_fips}, {county_fips}",
                level="block group",
                variables=list(self.variables.keys()),
            )
            return df

        df = _execute_query()

        if df.empty:
            return gpd.GeoDataFrame()

        # Rename variables to human-readable names
        df = df.rename(columns=self.variables)

        # Ensure geoid is 12 characters
        if "GEOID" in df.columns:
            df = df.rename(columns={"GEOID": "geoid"})

        # Ensure state and county columns exist (needed for conflict logging)
        # Normalize fallbacks to FIPS strings for consistent merging and logging
        if "state" not in df.columns:
            df["state"] = state_fips
        if "county" not in df.columns:
            df["county"] = county_fips

        # Ensure they are strings (sometimes cenpy returns them as objects/numbers)
        df["state"] = df["state"].astype(str).str.zfill(2)
        df["county"] = df["county"].astype(str).str.zfill(3)

        # Keep only required columns
        required_cols = [
            "geoid",
            "geometry",
            "population",
            "median_income",
            "state",
            "county",
        ]
        df = df[[col for col in required_cols if col in df.columns]]

        return df

    def _log_conflicts(self, duplicates: pd.DataFrame) -> None:
        """
        Logs warnings for conflicting attribute values across duplicate geoids (FR-1.1.7 step 3).
        """
        for geoid, group in duplicates.groupby("geoid"):
            # Compare population and median_income
            for col in ["population", "median_income"]:
                if group[col].nunique() > 1:
                    values = group[col].tolist()
                    counties = group["county"].tolist()
                    logger.warning(
                        f"Conflict for geoid {geoid} in field '{col}': "
                        f"Values {values} found in counties {counties}. "
                        f"Using first occurrence."
                    )
