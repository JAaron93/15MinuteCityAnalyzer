
import json
import os
import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from src.pipeline.exporter import export_to_geoparquet
import pyarrow.parquet as pq

def test_flatten_collisions(tmp_path, caplog):
    output_path = tmp_path / "collision.parquet"
    gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
    
    # Nested metadata that will cause collisions after flattening
    metadata = {
        "a.b": "original",
        "a": {"b": "nested"}
    }
    
    export_to_geoparquet(gdf, str(output_path), metadata=metadata)
    
    # Read back metadata using pyarrow
    table = pq.read_table(output_path)
    # custom_metadata is a dict with bytes keys and values
    meta = table.schema.metadata
    # Note: GeoPandas might store its own metadata, custom_metadata should be there too
    # Actually, pyarrow's table.schema.metadata contains everything
    # Let's find our keys
    flat_meta = {k.decode('utf-8'): v.decode('utf-8') for k, v in meta.items() if not k.startswith(b'geo')}
    
    # Assert that flattening preserves both literal dotted key and nested value (with disambiguation)
    assert flat_meta.get("a.b") == "original"
    assert flat_meta.get("a.b.1") == "nested"

def test_flatten_sequences(tmp_path):
    output_path = tmp_path / "sequences.parquet"
    gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
    
    metadata = {
        "list": [1, 2, 3],
        "tuple": (4, 5)
    }
    
    export_to_geoparquet(gdf, str(output_path), metadata=metadata)
    
    table = pq.read_table(output_path)
    meta = table.schema.metadata
    flat_meta = {k.decode('utf-8'): v.decode('utf-8') for k, v in meta.items() if not k.startswith(b'geo')}
    
    # Assert that sequences are JSON-serialized
    assert flat_meta.get('list') == '[1, 2, 3]'
    assert flat_meta.get('tuple') == '[4, 5]'
