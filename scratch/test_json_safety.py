
import logging
import pytest
import geopandas as gpd
from shapely.geometry import Point
from src.pipeline.exporter import export_to_geoparquet
import tempfile
import os

def test_json_serialization_fallback(caplog):
    # Setup logger to capture warnings
    caplog.set_level(logging.WARNING)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_fallback.parquet")
        gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
        
        # A non-serializable object (a class instance)
        class NonSerializable:
            def __str__(self):
                return "NonSerializableObject"
        
        metadata = {
            "safe_list": [1, 2, 3],
            "unsafe_list": [1, NonSerializable(), 3]
        }
        
        # This should not raise TypeError
        export_to_geoparquet(gdf, output_path, metadata=metadata)
        
        # Check logs for the fallback warning
        assert "Failed to JSON-serialize metadata sequence for 'unsafe_list'" in caplog.text
        assert "Falling back to string representation" in caplog.text

if __name__ == "__main__":
    # Manual run if needed
    import sys
    pytest.main([__file__])
