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
        # Keep first occurrence of each unique index (element_type, osm_id)
        if not points.empty:
            points = points[~points.index.duplicated(keep="first")]
            
        # 3. Union non-points (split polygons)
        if not non_points.empty:
            # Capture original index names to restore later
            original_index_names = non_points.index.names
            
            # Reset index to ensure consistent grouping behavior
            non_points_flat = non_points.reset_index()
            
            # Determine grouping columns: prefer (element_type, osmid) if they exist
            group_cols = [c for c in ["element_type", "osmid"] if c in non_points_flat.columns]
            if not group_cols:
                # Fallback to whatever index levels were present if standard OSM names are missing
                group_cols = [c for c in original_index_names if c is not None]
            
            # Only group if there are actually duplicates in the ID columns
            if group_cols and non_points_flat.duplicated(subset=group_cols).any():
                logger.info(f"Unioning split polygons/linestrings using grouping: {group_cols}")
                
                def _union_geoms(group):
                    # Always return a DataFrame (not a Series) with the same columns
                    # Using iloc[[0]] preserves the row as a single-row DataFrame
                    res = group.iloc[[0]].copy()
                    if len(group) > 1:
                        res["geometry"] = unary_union(group["geometry"].tolist())
                    return res
                
                # Use groupby on columns and apply the union logic
                non_points = non_points_flat.groupby(group_cols, group_keys=False).apply(_union_geoms)
                
                # Restore the original index structure if possible
                restorable_names = [name for name in original_index_names if name is not None]
                if restorable_names and all(name in non_points.columns for name in restorable_names):
                    non_points = non_points.set_index(restorable_names)
            else:
                # No duplicates or no grouping columns found, keep as is
                pass
        
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

        # Use nx.compose to merge graphs
        # compose merges nodes and edges by their IDs
        merged_graph = tiles_data[0]
        for g in tiles_data[1:]:
            merged_graph = nx.compose(merged_graph, g)
        
        # 1e-7 degrees is ~1cm at equator, sufficient for topological rejoining (FR-1.1.6)
        tolerance = 1e-7
        precision = 7  # Derived from tolerance 1e-7
        
        # We can use ox.consolidate_intersections but that simplifies the network.
        # Instead, we'll manually merge nodes that are spatially identical but have different IDs.
        # This is rare with OSM IDs but ensures robustness against split-edge artifacts.
        
        nodes_df = ox.graph_to_gdfs(merged_graph, nodes=True, edges=False)
        if nodes_df.empty:
            return merged_graph
            
        # Standardize coordinates
        nodes_df["x_round"] = nodes_df["x"].round(precision)
        nodes_df["y_round"] = nodes_df["y"].round(precision)
        
        # Find groups of nodes at the same location
        duplicates = nodes_df.groupby(["x_round", "y_round"]).filter(lambda x: len(x) > 1)
        
        if not duplicates.empty:
            logger.info(f"Rejoining {len(duplicates)} spatially identical nodes across tile boundaries.")
            node_mapping = {}
            for _, group in duplicates.groupby(["x_round", "y_round"]):
                keep_node = group.index[0]
                for other_node in group.index[1:]:
                    node_mapping[other_node] = keep_node
            
            # Find edges that will become self-loops after relabeling
            self_loops_to_remove = []
            for u, v, k in merged_graph.edges(keys=True):
                # If both u and v are being relabeled to the same node, 
                # or if one is being relabeled to the other
                new_u = node_mapping.get(u, u)
                new_v = node_mapping.get(v, v)
                if new_u == new_v and u != v:
                    self_loops_to_remove.append((u, v, k))

            # Update edges and remove merged nodes
            # networkx.relabel_nodes with copy=False is efficient
            nx.relabel_nodes(merged_graph, node_mapping, copy=False)
            
            # Remove the newly created self-loops
            if self_loops_to_remove:
                logger.info(f"Removing {len(self_loops_to_remove)} newly created self-loops.")
                # After relabeling, the edge (u, v, k) is now (new_u, new_u, k)
                for u, v, k in self_loops_to_remove:
                    new_node = node_mapping.get(u, u)
                    if merged_graph.has_edge(new_node, new_node, k):
                        merged_graph.remove_edge(new_node, new_node, k)
            
        return merged_graph
