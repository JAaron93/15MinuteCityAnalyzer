import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
import os

def create_mock_data():
    # Create some mock block groups around Los Angeles (approx)
    # Bbox: [-118.3, 34.0, -118.2, 34.1]
    
    geometries = [
        Polygon([(-118.25, 34.05), (-118.24, 34.05), (-118.24, 34.06), (-118.25, 34.06)]),
        Polygon([(-118.24, 34.05), (-118.23, 34.05), (-118.23, 34.06), (-118.24, 34.06)]),
        Polygon([(-118.25, 34.06), (-118.24, 34.06), (-118.24, 34.07), (-118.25, 34.07)]),
        Polygon([(-118.24, 34.06), (-118.23, 34.06), (-118.23, 34.07), (-118.24, 34.07)]),
    ]
    
    data = {
        'geoid': ['060371234561', '060371234562', '060371234563', '060371234564'],
        'population': [1500, 2000, 1200, 1800],
        'median_income': [25000.0, 85000.0, 31000.0, 120000.0],
        'grocery_count': [2, 5, 0, 8],
        'healthcare_count': [1, 3, 0, 4],
        'transit_count': [5, 10, 2, 15],
        'other_count': [3, 5, 1, 6],
    }
    
    df = pd.DataFrame(data)
    
    if len(geometries) != len(df):
        raise ValueError(
            f"Mismatch between geometries ({len(geometries)}) and data rows ({len(df)})"
        )
    
    # Calculate raw_score: 0.35*min(g,5) + 0.30*min(h,3) + 0.25*min(t,10) + 0.10*min(o,5)
    df['raw_score'] = (
        0.35 * df['grocery_count'].clip(upper=5) +
        0.30 * df['healthcare_count'].clip(upper=3) +
        0.25 * df['transit_count'].clip(upper=10) +
        0.10 * df['other_count'].clip(upper=5)
    )
    
    # Normalize (0-100)
    city_min = df['raw_score'].min()
    city_max = df['raw_score'].max()
    if city_max == city_min:
        df['accessibility_score'] = 50.0
    else:
        df['accessibility_score'] = 100 * (df['raw_score'] - city_min) / (city_max - city_min)
        
    # Total amenities
    df['total_amenities'] = df['grocery_count'] + df['healthcare_count'] + df['transit_count'] + df['other_count']
    
    # Equity category (default thresholds: 70, 40)
    df['equity_category'] = pd.cut(
        df['accessibility_score'],
        bins=[0, 40, 70, 100],
        labels=["Low Access", "Medium Access", "High Access"],
        include_lowest=True,
        right=False
    )
    
    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
    
    os.makedirs('data/processed', exist_ok=True)
    gdf.to_parquet('data/processed/processed_equity_data.parquet')
    print("Mock data created at data/processed/processed_equity_data.parquet")
    return gdf

if __name__ == "__main__":
    gdf = create_mock_data()
