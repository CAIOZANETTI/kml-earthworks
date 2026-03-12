"""
stationing.py
Build chainage (stationing) from raw KML points with elevation.
Interpolates stakes every STAKE_INTERVAL metres along the alignment.
"""

import numpy as np
from typing import List, Dict

from src.types import PointList, StationList

STAKE_INTERVAL = 20.0  # metres
EARTH_RADIUS_M = 6_371_000.0


def _haversine_dist(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres between two WGS84 points."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_M * 2 * np.arcsin(np.sqrt(a))


def build_stationing(points: PointList, stake_interval: float = STAKE_INTERVAL) -> StationList:
    """
    Given raw points with lat/lon/z_terrain_m, return a denser list
    of station points interpolated every `stake_interval` metres.

    Each returned dict has:
        station_m, lat, lon, z_terrain_m, stake_20m (bool), terrain_slope_pct
    """
    if len(points) < 2:
        raise ValueError("Need at least 2 points to build stationing.")

    # Build cumulative chainage for raw points
    raw_x = [0.0]
    for i in range(1, len(points)):
        d = _haversine_dist(
            points[i - 1]["lat"], points[i - 1]["lon"],
            points[i]["lat"], points[i]["lon"],
        )
        raw_x.append(raw_x[-1] + d)

    raw_lats = np.array([p["lat"] for p in points])
    raw_lons = np.array([p["lon"] for p in points])
    raw_z = np.array([p["z_terrain_m"] for p in points])
    raw_x = np.array(raw_x)

    # Remove duplicates in x (can happen with identical coordinates)
    _, unique_idx = np.unique(raw_x, return_index=True)
    raw_x = raw_x[unique_idx]
    raw_lats = raw_lats[unique_idx]
    raw_lons = raw_lons[unique_idx]
    raw_z = raw_z[unique_idx]

    total_length = raw_x[-1]

    # Build station array: every stake_interval + last point
    stations = np.arange(0.0, total_length, stake_interval)
    if stations[-1] < total_length:
        stations = np.append(stations, total_length)

    # Interpolate lat/lon/z at each station
    interp_lats = np.interp(stations, raw_x, raw_lats)
    interp_lons = np.interp(stations, raw_x, raw_lons)
    interp_z = np.interp(stations, raw_x, raw_z)

    # Build result list
    station_points = []
    for i, (sta, lat, lon, z) in enumerate(
        zip(stations, interp_lats, interp_lons, interp_z)
    ):
        # terrain_slope_pct between this station and previous
        if i == 0:
            terrain_slope_pct = 0.0
        else:
            dz = float(interp_z[i]) - float(interp_z[i - 1])
            dx = float(stations[i]) - float(stations[i - 1])
            terrain_slope_pct = (dz / dx * 100) if dx > 0 else 0.0

        station_points.append(
            {
                "station_m": round(float(sta), 2),
                "lat": round(float(lat), 8),
                "lon": round(float(lon), 8),
                "z_terrain_m": round(float(z), 2),
                "stake_20m": True,  # all interpolated stations ARE stakes
                "terrain_slope_pct": round(terrain_slope_pct, 2),
            }
        )

    return station_points
