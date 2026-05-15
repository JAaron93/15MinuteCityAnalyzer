"""Property-based tests for the 15-Minute City pipeline."""

import geopandas as gpd
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from src.pipeline.crs_utils import WGS84, transform_to_utm, transform_to_wgs84
from src.pipeline.scoring import (
    assign_equity_category,
    calculate_accessibility_score,
    spatial_join_amenities,
)

# Utility to generate simple WGS84 coordinates
lon_st = st.floats(
    min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False
)
lat_st = st.floats(
    min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False
)


@st.composite
def wgs84_points(draw):
    lon = draw(lon_st)
    lat = draw(lat_st)
    return Point(lon, lat)


@st.composite
def wgs84_polygons(draw):
    # Generate a center point in a safe range to avoid poles and dateline
    lon = draw(st.floats(min_value=-170.0, max_value=170.0))
    lat = draw(st.floats(min_value=-60.0, max_value=60.0))
    # Buffer distance in meters (approx 500m to 5km radius -> 1km to 10km side)
    dist_m = draw(st.floats(min_value=500.0, max_value=5000.0))

    point = Point(lon, lat)
    # Use GeoDataFrame to leverage estimate_utm_crs and robust reprojection
    gdf = gpd.GeoDataFrame(geometry=[point], crs=WGS84)
    utm_crs = gdf.estimate_utm_crs()

    # Project to UTM, buffer (square cap_style=3), and project back to WGS84
    buffered_gdf = gdf.to_crs(utm_crs).buffer(dist_m, cap_style=3).to_crs(WGS84)
    return buffered_gdf.iloc[0]


@given(
    bg_geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5),
    iso_geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_spatial_integrity(bg_geoms, iso_geoms):
    """
    Property 1: Spatial Integrity
    Verify that only block groups where overlap_area / block_area >= MIN_OVERLAP_FRACTION  # noqa: E501
    are counted as having access. All area calculations must use UTM.
    """
    block_groups = gpd.GeoDataFrame(
        {"geoid": [f"bg{i}" for i in range(len(bg_geoms))]},
        geometry=bg_geoms,
        crs=WGS84,
    )

    isochrones = gpd.GeoDataFrame(
        {"amenity_type": ["grocery"] * len(iso_geoms)}, geometry=iso_geoms, crs=WGS84
    )

    # Calculate a valid UTM CRS based on the first block group's centroid
    utm_crs = block_groups.iloc[[0]].estimate_utm_crs()

    joined = spatial_join_amenities(block_groups, isochrones, utm_crs)

    # If the join returned anything, independently verify the overlap fraction
    if not joined.empty:
        # Convert originals to UTM for independent area calculations
        bg_utm = transform_to_utm(block_groups, utm_crs)
        iso_utm = transform_to_utm(isochrones, utm_crs)

        for _, row in joined.iterrows():
            bg_id = row["geoid"]
            reported_fraction = row["overlap_fraction"]

            # Look up the block group geometry in UTM
            bg_geom = bg_utm[bg_utm["geoid"] == bg_id].geometry.iloc[0]
            bg_area = bg_geom.area
            assert bg_area > 0, f"Block group {bg_id} has zero area"

            # The output doesn't preserve which specific isochrone was
            # paired, so find the isochrone whose independently computed
            # overlap fraction matches the reported value.
            matched = False
            for iso_geom in iso_utm.geometry:
                intersection_area = bg_geom.intersection(iso_geom).area
                recalculated_fraction = intersection_area / bg_area
                if abs(recalculated_fraction - reported_fraction) < 1e-6:
                    matched = True
                    assert recalculated_fraction >= 0.10, (
                        f"Recalculated overlap {recalculated_fraction:.6f} "
                        f"< 0.10 for block group {bg_id}"
                    )
                    break

            assert matched, (
                f"No isochrone independently reproduced the reported "
                f"overlap_fraction {reported_fraction:.6f} for {bg_id}"
            )


@given(
    counts=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
        ),
        min_size=2,
        max_size=20,
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
    df = pd.DataFrame(
        counts,
        columns=["grocery_count", "healthcare_count", "transit_count", "other_count"],
    )
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
                f"Equal raw_scores {raw[i]:.4f} should give equal accessibility_scores, "  # noqa: E501
                f"got {acc[i]:.4f} vs {acc[i-1]:.4f}"
            )


@given(geoms=st.lists(wgs84_polygons(), min_size=1, max_size=5))
@settings(deadline=None)
def test_crs_consistency(geoms):
    """
    Property 3: CRS Consistency
    All geometries in the final output must be in WGS84 (EPSG:4326) coordinate reference system.  # noqa: E501
    """
    bg = gpd.GeoDataFrame(
        {"geoid": [f"bg{i}" for i in range(len(geoms))]},
        geometry=geoms,
        crs="EPSG:3857",
    )

    # If we pass it through transform_to_wgs84, it should be 4326
    bg_wgs84 = transform_to_wgs84(bg)
    assert bg_wgs84.crs.to_string() == "EPSG:4326"


@given(
    scores=st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=1, max_size=50)
)
@settings(deadline=None)
def test_equity_category_consistency(scores):
    """
    Property 5: Equity Category Consistency
    Equity categories must be assigned consistently based on accessibility score thresholds.  # noqa: E501
    """
    df = pd.DataFrame({"accessibility_score": scores})
    df["geoid"] = [f"bg{i}" for i in range(len(df))]
    block_groups = gpd.GeoDataFrame(df, geometry=[Point(0, 0)] * len(df), crs=WGS84)

    assigned, metadata = assign_equity_category(block_groups)

    thresholds = metadata["equity_thresholds"]
    high_min = thresholds["high_access_min"]
    med_min = thresholds["medium_access_min"]

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
    inc=st.floats(
        min_value=0.0, max_value=200000.0, allow_nan=False, allow_infinity=False
    ),
    grocery=st.integers(min_value=0, max_value=20),
    healthcare=st.integers(min_value=0, max_value=20),
    transit=st.integers(min_value=0, max_value=20),
    other=st.integers(min_value=0, max_value=20),
)
@settings(deadline=None)
def test_data_completeness(pop, inc, grocery, healthcare, transit, other):
    """
    Property 4: Data Completeness
    Generate input records via Hypothesis, run them through the scoring
    pipeline, and verify that the output contains required fields with
    valid (non-None) values and population > 0.
    """
    input_gdf = gpd.GeoDataFrame(
        {
            "geoid": ["123456789012"],
            "population": [pop],
            "median_income": [inc],
            "grocery_count": [grocery],
            "healthcare_count": [healthcare],
            "transit_count": [transit],
            "other_count": [other],
        },
        geometry=[Point(0, 0)],
        crs=WGS84,
    )

    scored = calculate_accessibility_score(input_gdf)

    # Assert required fields exist and are not None in the pipeline output
    for field in ("geoid", "accessibility_score", "median_income", "population"):
        assert field in scored.columns, f"Missing field: {field}"
        assert scored[field].notna().all(), f"Field '{field}' contains None"

    assert (scored["population"] > 0).all(), "population must be > 0"
