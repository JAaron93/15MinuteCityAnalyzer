"""Unit tests for CRS transformation utilities (Task 3.1 / 6.2.1–6.2.3).

Tests cover:
- UTM zone determination from bounding boxes
- WGS84 → UTM and UTM → WGS84 transformations
- CRS validation
- Error handling for invalid inputs
"""

import geopandas as gpd
import pytest
from shapely.geometry import Point

from src.pipeline.crs_utils import (
    CRSTransformationError,
    determine_utm_zone,
    transform_to_utm,
    transform_to_wgs84,
    validate_wgs84,
)


class TestDetermineUtmZone:
    """Tests for determine_utm_zone() — task 6.2.2."""

    def test_corona_ca_bbox(self) -> None:
        """Corona, CA should resolve to a UTM zone in band 11N."""
        # bbox: (north, south, east, west) for Corona, CA area
        bbox = (33.95, 33.82, -117.50, -117.64)
        utm_crs = determine_utm_zone(bbox)

        assert utm_crs is not None
        # UTM zone 11N for Southern California
        assert utm_crs.to_epsg() == 32611  # UTM zone 11N

    def test_new_york_bbox(self) -> None:
        """New York City should resolve to a projected UTM CRS."""
        bbox = (40.92, 40.48, -73.70, -74.26)
        utm_crs = determine_utm_zone(bbox)

        assert utm_crs is not None
        assert utm_crs.is_projected
        # Should be in UTM zone 18N (EPSG:32618)
        assert utm_crs.to_epsg() == 32618

    def test_returns_projected_crs(self) -> None:
        """The returned CRS must be a projected (metre-based) CRS."""
        bbox = (34.0, 33.9, -117.5, -117.6)
        utm_crs = determine_utm_zone(bbox)

        assert utm_crs.is_projected

    def test_deterministic(self) -> None:
        """Same bbox should always produce the same UTM CRS."""
        bbox = (34.0, 33.9, -117.5, -117.6)
        crs1 = determine_utm_zone(bbox)
        crs2 = determine_utm_zone(bbox)

        assert crs1.equals(crs2)


class TestTransformToUtm:
    """Tests for transform_to_utm() — task 6.2.3."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.gdf = gpd.GeoDataFrame(
            {"id": [1, 2]},
            geometry=[Point(-117.5, 33.9), Point(-117.6, 34.0)],
            crs="EPSG:4326",
        )
        self.utm_crs = determine_utm_zone((34.0, 33.9, -117.5, -117.6))

    def test_transforms_to_target_crs(self) -> None:
        """Output CRS must match the specified UTM CRS."""
        result = transform_to_utm(self.gdf, self.utm_crs)
        assert result.crs.equals(self.utm_crs)

    def test_preserves_row_count(self) -> None:
        """Transformation must not drop rows."""
        result = transform_to_utm(self.gdf, self.utm_crs)
        assert len(result) == len(self.gdf)

    def test_empty_geodataframe(self) -> None:
        """Empty GeoDataFrame should return empty without error."""
        empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        result = transform_to_utm(empty, self.utm_crs)
        assert result.empty

    def test_no_crs_assumes_wgs84(self) -> None:
        """GeoDataFrame with no CRS should be assumed WGS84."""
        no_crs = self.gdf.copy()
        no_crs.crs = None
        result = transform_to_utm(no_crs, self.utm_crs)
        assert result.crs.equals(self.utm_crs)


class TestTransformToWgs84:
    """Tests for transform_to_wgs84() — task 6.2.3."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.utm_crs = determine_utm_zone((34.0, 33.9, -117.5, -117.6))
        gdf_wgs84 = gpd.GeoDataFrame(
            {"id": [1]},
            geometry=[Point(-117.5, 33.9)],
            crs="EPSG:4326",
        )
        self.gdf_utm = gdf_wgs84.to_crs(self.utm_crs)

    def test_transforms_to_wgs84(self) -> None:
        """Output CRS must be EPSG:4326."""
        result = transform_to_wgs84(self.gdf_utm)
        assert result.crs.to_epsg() == 4326

    def test_round_trip_preserves_coordinates(self) -> None:
        """WGS84 → UTM → WGS84 should preserve coordinates (within tolerance)."""
        original = gpd.GeoDataFrame(
            {"id": [1]},
            geometry=[Point(-117.55, 33.95)],
            crs="EPSG:4326",
        )
        utm = transform_to_utm(original, self.utm_crs)
        back = transform_to_wgs84(utm)

        orig_coords = original.geometry.iloc[0].coords[0]
        back_coords = back.geometry.iloc[0].coords[0]

        assert abs(orig_coords[0] - back_coords[0]) < 1e-6
        assert abs(orig_coords[1] - back_coords[1]) < 1e-6

    def test_empty_geodataframe(self) -> None:
        """Empty GeoDataFrame should return empty without error."""
        empty = gpd.GeoDataFrame(geometry=[], crs=self.utm_crs)
        result = transform_to_wgs84(empty)
        assert result.empty


class TestValidateWgs84:
    """Tests for validate_wgs84() — task 3.1.6."""

    def test_valid_wgs84(self) -> None:
        """GeoDataFrame in WGS84 should pass validation."""
        gdf = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:4326")
        assert validate_wgs84(gdf) is None

    def test_non_wgs84_raises(self) -> None:
        """GeoDataFrame in a projected CRS should raise."""
        gdf = gpd.GeoDataFrame(geometry=[Point(500000, 3750000)], crs="EPSG:32611")
        with pytest.raises(CRSTransformationError, match="EPSG:4326"):
            validate_wgs84(gdf)

    def test_no_crs_raises(self) -> None:
        """GeoDataFrame with no CRS should raise."""
        gdf = gpd.GeoDataFrame(geometry=[Point(0, 0)])
        with pytest.raises(CRSTransformationError, match="no CRS"):
            validate_wgs84(gdf)
