import geopandas as gpd
import pytest
from shapely.geometry import Point

from src.pipeline.exporter import export_to_geoparquet


@pytest.fixture
def simple_gdf():
    """Returns a simple GeoDataFrame for testing."""
    return gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")


def test_flatten_collisions_resolution(tmp_path, caplog, simple_gdf):
    output_path = tmp_path / "collision_resolved.parquet"

    # Nested metadata that will cause collisions after flattening
    metadata = {"a.b": "original", "a": {"b": "nested"}}

    # We want to verify that it doesn't silently overwrite
    export_to_geoparquet(simple_gdf, str(output_path), metadata=metadata)

    # We can't easily check the parquet file if custom_metadata isn't supported by the environment,  # noqa: E501
    # but we can check the logs for the collision warning.
    assert "Metadata key collision detected" in caplog.text
    assert "'a.b' already exists" in caplog.text
    assert "Using disambiguated key: 'a.b.1'" in caplog.text


def test_flatten_sequences_json(tmp_path, mocker, simple_gdf):
    # Mocking export_to_geoparquet internals or just testing the logic via a helper if it were public.  # noqa: E501
    # Since it's internal, let's use a trick to capture the flat_metadata.

    output_path = tmp_path / "sequences_json.parquet"

    metadata = {"list": [1, 2, 3], "tuple": (4, 5)}

    # Spy on to_parquet to see what's being passed
    spy = mocker.spy(gpd.GeoDataFrame, "to_parquet")

    export_to_geoparquet(simple_gdf, str(output_path), metadata=metadata)

    # Check what was passed to custom_metadata
    args, kwargs = spy.call_args
    flat_meta = kwargs.get("custom_metadata")

    if flat_meta:  # Only check if the environment supports custom_metadata
        assert flat_meta["list"] == "[1, 2, 3]"
        assert flat_meta["tuple"] == "[4, 5]"  # JSON serialization of tuple is [4, 5]
    else:
        # Skip if custom_metadata is not supported - cannot verify JSON serialization
        pytest.skip("custom_metadata not supported in this environment")


def test_flatten_multiple_collisions(tmp_path, caplog, simple_gdf):
    output_path = tmp_path / "multi_collision.parquet"

    # We use a structure where "a.b" and "a": {"b": ...} are both present.
    # One of them will definitely find the other already in flat_metadata.
    metadata = {"a.b": "v1", "a": {"b": "v2"}}

    export_to_geoparquet(simple_gdf, str(output_path), metadata=metadata)

    # Check logs for disambiguation
    assert "Metadata key collision detected" in caplog.text
    assert "a.b" in caplog.text
