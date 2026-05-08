import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import os

df = pd.DataFrame({"a": [1], "geometry": [Point(0, 0)]})
gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

try:
    print("Trying custom_metadata...")
    gdf.to_parquet("test.parquet", custom_metadata={"test": "data"})
    print("Success with custom_metadata")
except Exception as e:
    print(f"Failed with custom_metadata: {type(e).__name__}: {e}")

try:
    print("Trying metadata...")
    gdf.to_parquet("test.parquet", metadata={"test": "data"})
    print("Success with metadata")
except Exception as e:
    print(f"Failed with metadata: {type(e).__name__}: {e}")

if os.path.exists("test.parquet"):
    os.remove("test.parquet")
