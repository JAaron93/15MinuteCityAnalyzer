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
        Merges POI GeoDataFrames, deduplicating by OSM ID and unioning split polygons (FR-1.1.6).
        Optimized to handle points separately from polygons/linestrings for performance.
        """
        if not tiles_data:
            return gpd.GeoDataFrame()
        
        # Filter out empty GDFs
        tiles_data = [df for df in tiles_data if not df.empty]
        if not tiles_data:
            return gpd.GeoDataFrame()

        # Combine all tiles
        combined = pd.concat(tiles_data, ignore_index=False)
        
        # 1. Identify points vs non-points (Polygons/LineStrings)
        # Points never need unioning, they just need deduplication.
        is_point = combined.geometry.type == "Point"
        points = combined[is_point]
        non_points = combined[~is_point]
        
        # 2. Fast deduplication for points
        # Keep first occurrence of each OSM ID (index level 1)
        if not points.empty:
            points = points[~points.index.duplicated(keep="first")]
            
        # 3. Union non-points (split polygons)
        if not non_points.empty:
            # Only group if there are actually duplicates
            if non_points.index.duplicated().any():
                logger.info("Unioning split polygons/linestrings in tiled OSM data.")
                
                def _union_geoms(group):
                    if len(group) == 1:
                        return group.iloc[0]
                    first = group.iloc[0].copy()
                    first["geometry"] = unary_union(group["geometry"].tolist())
                    return first
                
                non_points = non_points.groupby(level=[0, 1]).apply(_union_geoms)
            else:
                pass # No duplicates, no need to group
        
        # 4. Recombine
        result = pd.concat([points, non_points])
        return gpd.GeoDataFrame(result, crs=combined.crs)

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
        
        # 1e-7 degrees is ~1cm at equator, sufficient for topological rejoining (FR-1.1.6)
        tolerance = 1e-7
        
        # We can use ox.consolidate_intersections but that simplifies the network.
        # Instead, we'll manually merge nodes that are spatially identical but have different IDs.
        # This is rare with OSM IDs but ensures robustness against split-edge artifacts.
        
        nodes_df = ox.graph_to_gdfs(merged_graph, nodes=True, edges=False)
        if nodes_df.empty:
            return merged_graph
            
        # Standardize coordinates
        nodes_df["x_round"] = nodes_df["x"].round(7)
        nodes_df["y_round"] = nodes_df["y"].round(7)
        
        # Find groups of nodes at the same location
        duplicates = nodes_df.groupby(["x_round", "y_round"]).filter(lambda x: len(x) > 1)
        
        if not duplicates.empty:
            logger.info(f"Rejoining {len(duplicates)} spatially identical nodes across tile boundaries.")
            node_mapping = {}
            for _, group in duplicates.groupby(["x_round", "y_round"]):
                keep_node = group.index[0]
                for other_node in group.index[1:]:
                    node_mapping[other_node] = keep_node
            
            # Update edges and remove merged nodes
            # networkx.relabel_nodes with copy=False is efficient
            nx.relabel_nodes(merged_graph, node_mapping, copy=False)
            
            # Relabeling in MultiDiGraph might create multi-edges if they already existed.
            # But here it just ensures connectivity.
            
        return merged_graph
