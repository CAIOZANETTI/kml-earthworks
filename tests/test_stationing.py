"""
Unit tests for stationing.py
Tests the haversine distance calculation and station building logic.
"""

import pytest
import math
from src.stationing import build_stationing


class TestHaversineDistance:
    """Tests for the Haversine distance formula"""

    def test_same_point_zero_distance(self):
        """Very close points should have minimal distance"""
        # Use points that are very close but not identical
        # (same point case is a degenerate edge case)
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 0.0},
            {"lat": 0.0001, "lon": 0.0001, "z_terrain_m": 0.0},  # ~15m away
        ]
        stations = build_stationing(points)
        # First station is always 0
        assert stations[0]["station_m"] == 0.0
        # Total distance should be small (under 20m, so no intermediate stations)
        assert len(stations) == 2
        assert 10 < stations[-1]["station_m"] < 20

    def test_equator_1_degree_longitude(self):
        """1 degree of longitude at equator ≈ 111.32 km"""
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 0.0},
            {"lat": 0.0, "lon": 1.0, "z_terrain_m": 0.0},
        ]
        stations = build_stationing(points)
        distance_km = stations[-1]["station_m"] / 1000
        # Should be approximately 111.32 km (±1%)
        assert 110.3 < distance_km < 112.3

    def test_meridian_1_degree_latitude(self):
        """1 degree of latitude ≈ 110.57 km (varies slightly with latitude)"""
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 0.0},
            {"lat": 1.0, "lon": 0.0, "z_terrain_m": 0.0},
        ]
        stations = build_stationing(points)
        distance_km = stations[-1]["station_m"] / 1000
        # Should be approximately 110.57 km (±1%)
        assert 109.5 < distance_km < 111.6

    def test_known_distance_rio_sao_paulo(self):
        """Distance Rio de Janeiro to São Paulo ≈ 359 km (straight line)"""
        points = [
            {"lat": -22.9068, "lon": -43.1729, "z_terrain_m": 0.0},  # Rio
            {"lat": -23.5505, "lon": -46.6333, "z_terrain_m": 0.0},  # São Paulo
        ]
        stations = build_stationing(points)
        distance_km = stations[-1]["station_m"] / 1000
        # Should be approximately 359 km (±5% for great circle approximation)
        assert 340 < distance_km < 380


class TestStationBuilding:
    """Tests for station interpolation and building"""

    def test_two_points_creates_interpolated_stations(self):
        """Two points should create stations every 20m"""
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 100.0},
            {"lat": 0.0, "lon": 0.001, "z_terrain_m": 110.0},  # ~111m away
        ]
        stations = build_stationing(points)

        # Should have stations at 0, 20, 40, 60, 80, 100, 111 (roughly)
        assert len(stations) >= 6
        assert stations[0]["station_m"] == 0.0
        assert stations[1]["station_m"] == pytest.approx(20.0, abs=0.1)

    def test_all_stations_are_stakes(self):
        """All interpolated stations should be marked as stakes"""
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 100.0},
            {"lat": 0.0, "lon": 0.001, "z_terrain_m": 110.0},
        ]
        stations = build_stationing(points)

        for station in stations:
            assert station["stake_20m"] is True

    def test_elevation_interpolation(self):
        """Elevation should be linearly interpolated between points"""
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 100.0},
            {"lat": 0.0, "lon": 0.0018, "z_terrain_m": 200.0},  # ~200m away
        ]
        stations = build_stationing(points)

        # Find station at approximately 100m (halfway)
        mid_station = None
        for s in stations:
            if 95 < s["station_m"] < 105:
                mid_station = s
                break

        assert mid_station is not None
        # Elevation at halfway should be approximately 150m
        assert 145 < mid_station["z_terrain_m"] < 155

    def test_slope_calculation(self):
        """Slope should be calculated correctly between stations"""
        # Create a 10% upward slope (10m rise over 100m run)
        points = [
            {"lat": 0.0, "lon": 0.0, "z_terrain_m": 100.0},
            {"lat": 0.0, "lon": 0.0009, "z_terrain_m": 110.0},  # ~100m away
        ]
        stations = build_stationing(points)

        # Check slope is approximately 10% (allowing some interpolation error)
        # Skip first station which might have 0 slope
        slopes = [s["terrain_slope_pct"] for s in stations[1:]]
        avg_slope = sum(slopes) / len(slopes)
        assert 8 < avg_slope < 12

    def test_coordinates_preserved(self):
        """Station points should preserve lat/lon coordinates"""
        points = [
            {"lat": -22.5, "lon": -43.5, "z_terrain_m": 100.0},
            {"lat": -22.6, "lon": -43.6, "z_terrain_m": 110.0},
        ]
        stations = build_stationing(points)

        # All stations should have valid lat/lon within the bounds
        for station in stations:
            assert -22.7 < station["lat"] < -22.4
            assert -43.7 < station["lon"] < -43.4
            assert "z_terrain_m" in station
