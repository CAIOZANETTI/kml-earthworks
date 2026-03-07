"""
elevation.py
Fetch terrain elevation for coordinates using Open-Meteo Elevation API.
Free, no API key required.
"""

import time
import requests
from typing import List, Dict


_API_URL = "https://api.open-meteo.com/v1/elevation"
_BATCH_SIZE = 100
_RETRY_DELAYS = [1, 2, 5, 10]  # seconds


def _fetch_batch(lats: List[float], lons: List[float]) -> List[float]:
    """Fetch elevation for a single batch with retry and fallback logic."""
    url_meteo = (
        f"{_API_URL}"
        f"?latitude={','.join(str(x) for x in lats)}"
        f"&longitude={','.join(str(x) for x in lons)}"
    )

    url_topo = (
        f"https://api.opentopodata.org/v1/srtm30m"
        f"?locations={'|'.join(f'{lat},{lon}' for lat, lon in zip(lats, lons))}"
    )

    # Attempt Open-Meteo first
    for attempt, delay in enumerate([0, 1, 2]):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url_meteo, timeout=10)
            if resp.status_code == 200:
                elevations = resp.json().get("elevation", [])
                if len(elevations) == len(lats):
                    time.sleep(0.1)
                    return elevations
            elif resp.status_code == 429:
                continue
        except requests.RequestException:
            pass
    
    # Fallback to OpenTopoData
    for attempt, delay in enumerate([0, 1, 5]):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url_topo, timeout=15)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                elevations = [r.get("elevation", 0.0) for r in results]
                if len(elevations) == len(lats):
                    time.sleep(1.0) # OpenTopoData is strict (1 req/sec)
                    return elevations
            elif resp.status_code == 429:
                continue
        except requests.RequestException:
            pass

    raise RuntimeError("Elevation API: max retries exceeded for both Open-Meteo and OpenTopoData")


def enrich_elevation(points: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Add 'z_terrain_m' to each point dict.

    Args:
        points: list of {"lat": float, "lon": float, ...}
        progress_callback: optional callable(processed, total) for UI updates

    Returns:
        same list with 'z_terrain_m' added in place
    """
    total = len(points)
    all_elevations = []

    for i in range(0, total, _BATCH_SIZE):
        batch = points[i : i + _BATCH_SIZE]
        lats = [p["lat"] for p in batch]
        lons = [p["lon"] for p in batch]
        elevations = _fetch_batch(lats, lons)
        all_elevations.extend(elevations)

        if progress_callback:
            progress_callback(min(i + _BATCH_SIZE, total), total)

    for point, z in zip(points, all_elevations):
        point["z_terrain_m"] = float(z)

    return points
