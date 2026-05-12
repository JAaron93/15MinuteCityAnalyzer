
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
    print(f"Metadata keys: {meta.keys()}")
    
    # Let's find our keys
    flat_meta = {k.decode('utf-8'): v.decode('utf-8') for k, v in meta.items() if not k.startswith(b'geo')}
    print(f"Flattened metadata: {flat_meta}")
    
    # In current code, one will overwrite the other.
    # If the bug is present, we will only have one 'a.b'
    assert 'a.b' in flat_meta
    # This test "passes" currently because it doesn't assert AGAINST the bug yet.
    # We want to assert that we have BOTH or a disambiguated one.

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
    
    print(f"Sequence metadata: {flat_meta}")
    # Current behavior:
    # flat_meta['list'] == '[1, 2, 3]'
    # We want it to be JSON: '[1, 2, 3]' (which is the same string representation for a simple list, but different for complex ones)
    # Actually, str([1, 2, 3]) is '[1, 2, 3]', and json.dumps([1, 2, 3]) is '[1, 2, 3]'.
    # But for a tuple: str((4, 5)) is '(4, 5)', while json.dumps((4, 5)) is '[4, 5]'.
    
    assert flat_meta['tuple'] == '(4, 5)' # Current buggy behavior
