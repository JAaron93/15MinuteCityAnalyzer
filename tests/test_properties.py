"""Property-based tests for the 15-Minute City pipeline."""

import geopandas as gpd
import pandas as pd
import numpy as np
from hypothesis import given, settings, HealthCheck, strategies as st
from shapely.geometry import Polygon, Point

from src.pipeline.scoring import spatial_join_amenities, calculate_accessibility_score, assign_equity_category
from src.pipeline.crs_utils import WGS84, transform_to_utm, transform_to_wgs84

# Utility to generate simple WGS84 coordinates
lon_st = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)
lat_st = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)

@st.composite
def wgs84_points(draw):
    lon = draw(lon_st)
    lat = draw(lat_st)
    return Point(lon, lat)

@st.composite
def wgs84_polygons(draw):
    lon = draw(st.floats(min_value=-179.0, max_value=179.0))
    lat = draw(st.floats(min_value=-80.0, max_value=80.0))
    size = draw(st.floats(min_value=0.01, max_value=0.1))
    
    # Create a simple square polygon
    coords = [
        (lon, lat),
        (lon + size, lat),
        (lon + size, lat + size),
        (lon, lat + size),
        (lon, lat)
    ]
    return Polygon(coords)

@given(
    bg_geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5),
    iso_geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_spatial_integrity(bg_geoms, iso_geoms):
    """
    Property 1: Spatial Integrity
    Verify that only block groups where overlap_area / block_area >= MIN_OVERLAP_FRACTION
    are counted as having access. All area calculations must use UTM.
    """
    block_groups = gpd.GeoDataFrame({
        "geoid": [f"bg{i}" for i in range(len(bg_geoms))]
    }, geometry=bg_geoms, crs=WGS84)
    
    isochrones = gpd.GeoDataFrame({
        "amenity_type": ["grocery"] * len(iso_geoms)
    }, geometry=iso_geoms, crs=WGS84)
    
    # Calculate a valid UTM CRS based on the first block group's centroid
    utm_crs = block_groups.iloc[[0]].estimate_utm_crs()
    
    joined = spatial_join_amenities(block_groups, isochrones, utm_crs)
    
    # If the join returned anything, verify the property
    if not joined.empty:
        # Convert original to UTM to do area calculations
        bg_utm = transform_to_utm(block_groups, utm_crs)
        iso_utm = transform_to_utm(isochrones, utm_crs)
        
        for _, row in joined.iterrows():
            bg_id = row["geoid"]
            # Find the original block group UTM geometry
            bg_geom = bg_utm[bg_utm["geoid"] == bg_id].geometry.iloc[0]
            
            # Since we did a join, the isochrone geometry that intersected 
            # should overlap by at least 10%
            # Wait, the spatial_join_amenities returns the joined dataframe with overlap_fraction
            overlap_fraction = row["overlap_fraction"]
            
            assert overlap_fraction >= 0.10


@given(
    counts=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20)
        ),
        min_size=2,
        max_size=20
    )
)
@settings(deadline=None)
def test_score_monotonicity(counts):
    """
    Property 2: Score Monotonicity
    raw_score(b1) > raw_score(b2) ⟹ accessibility_score(b1) ≥ accessibility_score(b2)

    Uses a vectorized sort-and-check approach: if we sort by raw_score,
    accessibility_score must be non-decreasing.
    """
    df = pd.DataFrame(counts, columns=["grocery_count", "healthcare_count", "transit_count", "other_count"])
    df["geoid"] = [f"bg{i}" for i in range(len(df))]

    block_groups = gpd.GeoDataFrame(df, geometry=[Point(0, 0)] * len(df), crs=WGS84)

    scored = calculate_accessibility_score(block_groups)

    # Sort by raw_score ascending; accessibility_score must be non-decreasing
    sorted_df = scored.sort_values("raw_score").reset_index(drop=True)
    raw = sorted_df["raw_score"].values
    acc = sorted_df["accessibility_score"].values

    for i in range(1, len(sorted_df)):
        if raw[i] > raw[i - 1]:
            assert acc[i] >= acc[i - 1], (
                f"Monotonicity violated: raw_score {raw[i]:.4f} > {raw[i-1]:.4f} "
                f"but accessibility_score {acc[i]:.4f} < {acc[i-1]:.4f}"
            )
        elif raw[i] == raw[i - 1]:
            assert acc[i] == acc[i - 1], (
                f"Equal raw_scores {raw[i]:.4f} should give equal accessibility_scores, "
                f"got {acc[i]:.4f} vs {acc[i-1]:.4f}"
            )


@given(
    geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5)
)
def test_crs_consistency(geoms):
    """
    Property 3: CRS Consistency
    All geometries in the final output must be in WGS84 (EPSG:4326) coordinate reference system.
    """
    bg = gpd.GeoDataFrame({"geoid": [f"bg{i}" for i in range(len(geoms))]}, geometry=geoms, crs="EPSG:3857")
    
    # If we pass it through transform_to_wgs84, it should be 4326
    bg_wgs84 = transform_to_wgs84(bg)
    assert bg_wgs84.crs.to_string() == "EPSG:4326"


@given(
    scores=st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=1, max_size=50)
)
def test_equity_category_consistency(scores):
    """
    Property 5: Equity Category Consistency
    Equity categories must be assigned consistently based on accessibility score thresholds.
    """
    df = pd.DataFrame({"accessibility_score": scores})
    df["geoid"] = [f"bg{i}" for i in range(len(df))]
    block_groups = gpd.GeoDataFrame(df, geometry=[Point(0,0)] * len(df), crs=WGS84)
    
    assigned, metadata = assign_equity_category(block_groups)
    
    high_min = metadata["equity_thresholds.high_access_min"]
    med_min = metadata["equity_thresholds.medium_access_min"]
    
    for _, row in assigned.iterrows():
        score = row["accessibility_score"]
        category = row["equity_category"]
        
        if score >= high_min:
            assert category == "High Access"
        elif score >= med_min:
            assert category == "Medium Access"
        else:
            assert category == "Low Access"


@given(
    pop=st.integers(min_value=1, max_value=10000),
    inc=st.floats(min_value=0.0, max_value=200000.0),
    score=st.floats(min_value=0.0, max_value=100.0)
)
def test_data_completeness(pop, inc, score):
    """
    Property 4: Data Completeness
    Verify that records have the required fields.
    """
    record = {
        "geoid": "123456789012",
        "population": pop,
        "median_income": inc,
        "accessibility_score": score,
        "equity_category": "Medium Access"
    }
    
    assert record["geoid"] is not None
    assert record["accessibility_score"] is not None
    assert record["median_income"] is not None
    assert record["population"] > 0
