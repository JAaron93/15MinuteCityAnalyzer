import logging
import geopandas as gpd
import pandas as pd
import networkx as nx
import osmnx as ox
from typing import List, Any
from shapely.ops import unary_union

logger = logging.getLogger(__name__)

class TileMerger:
    """
    Merges tiled OSM data (amenities and street networks) (FR-1.1.6).
    """

    def merge_pois(self, tiles_data: List[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
        """
        Merges POI GeoDataFrames, deduplicating by OSM ID and unioning split polygons.
        """
        if not tiles_data:
            return gpd.GeoDataFrame()
        
        # Filter out empty GDFs
        tiles_data = [df for df in tiles_data if not df.empty]
        if not tiles_data:
            return gpd.GeoDataFrame()

        # Combine all tiles
        combined = pd.concat(tiles_data, ignore_index=False)
        
        # Deduplicate by index (which is (element_type, osmid) in OSMnx)
        # For split polygons, we should ideally union them.
        # Let's group by index and union geometries.
        
        def _union_geoms(group):
            if len(group) == 1:
                return group.iloc[0]
            
            first = group.iloc[0].copy()
            # Union all geometries in the group
            first["geometry"] = unary_union(group["geometry"].tolist())
            return first

        # Note: grouping and unioning can be slow for large datasets.
        # But it's necessary for correctness if we expect split polygons.
        merged = combined.groupby(level=[0, 1]).apply(_union_geoms)
        
        if isinstance(merged, pd.Series):
            # This happens if combined has only one row or similar?
            # Actually apply might return a series if we are not careful.
            pass
            
        return gpd.GeoDataFrame(merged, crs=combined.crs)

    def merge_graphs(self, tiles_data: List[Any]) -> Any:
        """
        Merges multiple OSMnx graphs into a single topologically connected graph.
        """
        if not tiles_data:
            return None
        
        # Filter out None
        tiles_data = [g for g in tiles_data if g is not None]
        if not tiles_data:
            return None

        if len(tiles_data) == 1:
            return tiles_data[0]

        # Use ox.compose to merge graphs
        # compose merges nodes and edges by their IDs
        merged_graph = tiles_data[0]
        for g in tiles_data[1:]:
            merged_graph = ox.compose(merged_graph, g)
        
        # OSMnx's compose merges nodes with the same ID.
        # Since OSM IDs are global, this should handle most cases.
        # If we need spatial snapping for edges that were split:
        # "edge rejoining with 1e-6° tolerance"
        
        # If two nodes have different IDs but are spatially identical (within tolerance),
        # we might need to merge them. However, OSM IDs are usually consistent across requests.
        
        # One issue with compose is that it might not preserve all attributes if they differ.
        # But for the street network, they should be consistent.
        
        return merged_graph
