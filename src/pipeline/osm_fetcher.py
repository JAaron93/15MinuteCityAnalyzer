import logging
import yaml
import osmnx as ox
import geopandas as gpd
import pandas as pd
from typing import List, Tuple, Optional, Dict, Any
from shapely.geometry import box, MultiPoint, MultiPolygon, Point, Polygon
from src.pipeline.utils import retry_with_policy
from src.pipeline.tile_merger import TileMerger
from src.pipeline.data_validator import DataValidator

logger = logging.getLogger(__name__)

class OSMFetcher:
    """
    Fetches OpenStreetMap data (amenities and street networks) with tiling support (FR-1.1.5, FR-1.1.6).
    """

    def __init__(self, config_path: str = "pipeline_config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
        self.bbox_limits = self.config.get("bbox_limits", {})
        self.retry_policy = self.config.get("retry_policy", {})
        
        # Configure OSMnx
        ox.settings.timeout = self.retry_policy.get("per_request_timeout_s", 10)
        ox.settings.use_cache = True
        ox.settings.log_console = False

        # Tag sets from DR-3.1.5
        self.amenity_tags = {
            "grocery": {"shop": ["supermarket", "convenience", "deli"]},
            "healthcare": {"amenity": ["hospital", "clinic", "doctors", "pharmacy"]},
            "transit": {"amenity": ["bus_station", "train_station", "subway_entrance"], 
                        "highway": ["bus_stop"]},
            "other": {"amenity": ["library", "post_office", "school"], 
                      "leisure": ["park", "playground"]}
        }

    def fetch_amenities(self, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        """
        Fetches POIs for all amenity types within the bounding box (FR-1.1.1, FR-1.1.2).
        """
        self._validate_bbox(bbox)

        if self.bbox_limits.get("enable_tiling", False):
            df = self._fetch_with_tiling(bbox, "amenities")
        else:
            df = self._fetch_amenities_batch(bbox)
        
        DataValidator.validate_osm_data(df)
        return df

    def fetch_street_network(self, bbox: Tuple[float, float, float, float]) -> Any:
        """
        Fetches the walkable street network within the bounding box (FR-1.1.1, FR-1.1.3).
        """
        self._validate_bbox(bbox)

        if self.bbox_limits.get("enable_tiling", False):
            return self._fetch_with_tiling(bbox, "network")

        return self._fetch_network_batch(bbox)

    def _validate_bbox(self, bbox: Tuple[float, float, float, float]) -> None:
        """
        Validates the bounding box against limits (FR-1.1.5).
        """
        north, south, east, west = bbox
        edge_ns = abs(north - south)
        edge_ew = abs(east - west)
        area = edge_ns * edge_ew
        
        max_edge = self.bbox_limits.get("max_edge_degrees", 1.0)
        max_area = self.bbox_limits.get("max_area_sq_degrees", 1.0)
        
        if (edge_ns > max_edge or edge_ew > max_edge or area > max_area) and not self.bbox_limits.get("enable_tiling", False):
            msg = (
                f"Bounding box exceeds limits: edges={edge_ns:.2f}°, {edge_ew:.2f}° (max={max_edge:.2f}°), "
                f"area={area:.2f} sq° (max={max_area:.2f} sq°). "
                f"Enable tiling to process larger areas."
            )
            logger.error(msg)
            raise Exception(msg) # Should be BoundingBoxTooLargeError

    @retry_with_policy({"attempts": 3, "per_request_timeout_s": 10}) # Simplified for internal use
    def _fetch_amenities_batch(self, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        """
        Internal batch fetcher for amenities.
        """
        all_pois = []
        north, south, east, west = bbox
        
        for amenity_type, tags in self.amenity_tags.items():
            try:
                # Combine tags into a single dictionary for ox.features_from_bbox
                # Actually, ox.features_from_bbox takes a dict of {tag: values}
                pois = ox.features_from_bbox(north, south, east, west, tags)
                if not pois.empty:
                    pois["amenity_type"] = amenity_type
                    all_pois.append(pois)
            except ox._errors.InsufficientResponseError:
                logger.info(f"No {amenity_type} found in bbox.")
            except Exception as e:
                logger.warning(f"Error fetching {amenity_type}: {e}")
        
        if not all_pois:
            return gpd.GeoDataFrame()
        
        return pd.concat(all_pois, ignore_index=False)

    def _fetch_network_batch(self, bbox: Tuple[float, float, float, float]) -> Any:
        """
        Internal batch fetcher for street network.
        """
        north, south, east, west = bbox
        logger.info(f"Fetching street network for bbox: {bbox}")
        
        @retry_with_policy(self.retry_policy)
        def _execute():
            return ox.graph_from_bbox(north, south, east, west, network_type="walk")
        
        G = _execute()
        logger.info(f"Fetched network with {len(G.nodes)} nodes and {len(G.edges)} edges.")
        return G

    def _fetch_with_tiling(self, bbox: Tuple[float, float, float, float], mode: str) -> Any:
        """
        Implements bbox tiling logic (FR-1.1.6).
        """
        north, south, east, west = bbox
        max_edge = self.bbox_limits.get("max_edge_degrees", 1.0)
        max_area = self.bbox_limits.get("max_area_sq_degrees", 1.0)
        
        # Calculate number of tiles needed
        edge_ns = north - south
        edge_ew = east - west
        
        nx = int(edge_ew // max_edge) + 1
        ny = int(edge_ns // max_edge) + 1
        
        # Ensure each tile is within area limit too
        while (edge_ew / nx) * (edge_ns / ny) > max_area:
            if edge_ew / nx > edge_ns / ny:
                nx += 1
            else:
                ny += 1
        
        logger.info(f"Subdividing bbox into {nx}x{ny} tiles.")
        
        dx = edge_ew / nx
        dy = edge_ns / ny
        
        tiles_data = []
        skipped_count = 0
        total_tiles = nx * ny
        
        merger = TileMerger()
        
        for i in range(nx):
            for j in range(ny):
                tile_west = west + i * dx
                tile_east = west + (i + 1) * dx
                tile_south = south + j * dy
                tile_north = south + (j + 1) * dy
                tile_bbox = (tile_north, tile_south, tile_east, tile_west)
                
                try:
                    if mode == "amenities":
                        data = self._fetch_amenities_batch(tile_bbox)
                    else:
                        data = self._fetch_network_batch(tile_bbox)
                    
                    if data:
                        tiles_data.append(data)
                except Exception as e:
                    logger.warning(f"Failed to fetch tile ({i}, {j}): {e}")
                    skipped_count += 1
        
        failure_threshold = self.config.get("bbox_limits", {}).get("tiling", {}).get("failure_threshold", 0.20)
        if skipped_count / total_tiles > failure_threshold:
            raise Exception(f"Tiling failure: {skipped_count}/{total_tiles} tiles failed (threshold {failure_threshold}).")

        if mode == "amenities":
            return merger.merge_pois(tiles_data)
        else:
            return merger.merge_graphs(tiles_data)
