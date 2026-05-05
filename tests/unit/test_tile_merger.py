import networkx as nx
import osmnx as ox
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from src.pipeline.tile_merger import TileMerger

def test_merge_pois_multiindex():
    merger = TileMerger()
    
    # Create two tiles with a 2-level MultiIndex (element_type, osmid)
    # Tile 1: A polygon split at boundary
    # Tile 2: The other half of the polygon
    poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    poly2 = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    
    idx = pd.MultiIndex.from_tuples([("way", 123)], names=["element_type", "osmid"])
    gdf1 = gpd.GeoDataFrame({"geometry": [poly1], "name": ["Test"]}, index=idx, crs="EPSG:4326")
    gdf2 = gpd.GeoDataFrame({"geometry": [poly2], "name": ["Test"]}, index=idx, crs="EPSG:4326")
    
    merged = merger.merge_pois([gdf1, gdf2])
    
    # Should have 1 row, unioned geometry
    assert len(merged) == 1
    assert merged.iloc[0]["geometry"].area == 2.0
    assert isinstance(merged.index, pd.MultiIndex)
    assert merged.index.names == ["element_type", "osmid"]

def test_merge_pois_flat_index():
    merger = TileMerger()
    
    # Create tiles with a flat index but having element_type and osmid columns
    poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    poly2 = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    
    gdf1 = gpd.GeoDataFrame({
        "geometry": [poly1], 
        "element_type": ["way"], 
        "osmid": [123], 
        "name": ["Test"]
    }, crs="EPSG:4326")
    gdf2 = gpd.GeoDataFrame({
        "geometry": [poly2], 
        "element_type": ["way"], 
        "osmid": [123], 
        "name": ["Test"]
    }, crs="EPSG:4326")
    
    merged = merger.merge_pois([gdf1, gdf2])
    
    # Should have 1 row, unioned geometry
    assert len(merged) == 1
    assert merged.iloc[0]["geometry"].area == 2.0
    assert "element_type" in merged.columns
    assert "osmid" in merged.columns

def test_merge_pois_mixed_types():
    merger = TileMerger()
    
    # Tile 1: A Point and a Polygon
    # Tile 2: The other half of the Polygon
    p = Point(0.5, 0.5)
    poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    poly2 = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    
    idx_p = pd.MultiIndex.from_tuples([("node", 1)], names=["element_type", "osmid"])
    idx_w = pd.MultiIndex.from_tuples([("way", 123)], names=["element_type", "osmid"])
    
    gdf1 = gpd.GeoDataFrame({"geometry": [p, poly1]}, index=idx_p.append(idx_w), crs="EPSG:4326")
    gdf2 = gpd.GeoDataFrame({"geometry": [poly2]}, index=idx_w, crs="EPSG:4326")
    
    merged = merger.merge_pois([gdf1, gdf2])
    
    # Should have 2 rows: 1 Point (unchanged), 1 Polygon (unioned)
    assert len(merged) == 2
    assert (merged.geometry.type == "Point").sum() == 1
    assert (merged.geometry.type == "Polygon").sum() == 1
    assert merged.loc[("way", 123), "geometry"].area == 2.0
