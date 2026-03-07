"""
elevation.py
Fetch terrain elevation for coordinates using Open-Meteo Elevation API.
Free, no API key required.
"""

import re
import time
import requests
from typing import Dict, List, Optional


_API_URL = "https://api.open-meteo.com/v1/elevation"
_BATCH_SIZE = 100
_METEO_TIMEOUT = (3, 8)
_TOPO_TIMEOUT = (3, 12)
_METEO_RETRY_DELAYS = [0, 0.5]
_TOPO_RETRY_DELAYS = [0, 1, 3]
_TOPO_RATE_LIMIT_DELAY_S = 0.8
_METEO_COOLDOWN_DEFAULT_S = 60
_METEO_COOLDOWN_UNTIL = 0.0


def _guess_meteo_wait_seconds(reason: str) -> int:
    """Parse rate-limit wait hints from Open-Meteo response text."""
    text = (reason or "").lower()

    minute_match = re.search(r"(\d+)\s*minute", text)
    if minute_match:
        return max(1, int(minute_match.group(1))) * 60

    second_match = re.search(r"(\d+)\s*second", text)
    if second_match:
        return max(1, int(second_match.group(1)))

    if "one minute" in text:
        return 60

    return _METEO_COOLDOWN_DEFAULT_S


def _fetch_batch(
    lats: List[float],
    lons: List[float],
    session: Optional[requests.Session] = None,
) -> List[float]:
    """Fetch elevation for a single batch with retry and fallback logic."""
    global _METEO_COOLDOWN_UNTIL

    http = session or requests
    url_topo = "https://api.opentopodata.org/v1/srtm30m"
    meteo_params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
    }
    topo_data = {"locations": "|".join(f"{lat},{lon}" for lat, lon in zip(lats, lons))}

    last_error = ""

    # Attempt Open-Meteo first
    now = time.time()
    meteo_ready = now >= _METEO_COOLDOWN_UNTIL

    if meteo_ready:
        for delay in _METEO_RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                resp = http.get(_API_URL, params=meteo_params, timeout=_METEO_TIMEOUT)
            except requests.RequestException as e:
                last_error = f"Open-Meteo Error: {e}"
                continue

            if resp.status_code == 200:
                elevations = resp.json().get("elevation", [])
                if len(elevations) == len(lats):
                    return elevations
                last_error = (
                    f"Open-Meteo size mismatch ({len(elevations)} for {len(lats)} points)"
                )
                break

            if resp.status_code == 429:
                reason = ""
                try:
                    reason = resp.json().get("reason", "")
                except ValueError:
                    reason = resp.text or ""
                cooldown = _guess_meteo_wait_seconds(reason)
                _METEO_COOLDOWN_UNTIL = max(_METEO_COOLDOWN_UNTIL, time.time() + cooldown)
                details = reason.strip() or f"cooldown {cooldown}s"
                last_error = f"Open-Meteo 429 Rate Limit: {details}"
                break

            last_error = f"Open-Meteo {resp.status_code}: {resp.text}"
            if resp.status_code < 500:
                break
    else:
        remaining = max(1, int(_METEO_COOLDOWN_UNTIL - now))
        last_error = f"Open-Meteo cooldown active ({remaining}s remaining)"
    
    # Fallback to OpenTopoData (using POST to avoid URL length limits)
    for delay in _TOPO_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            resp = http.post(url_topo, data=topo_data, timeout=_TOPO_TIMEOUT)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                elevations = [r.get("elevation", 0.0) for r in results]
                if len(elevations) == len(lats):
                    time.sleep(_TOPO_RATE_LIMIT_DELAY_S)
                    return elevations
                last_error += (
                    f" | OpenTopoData size mismatch ({len(elevations)} for {len(lats)} points)"
                )
                continue
            elif resp.status_code == 429:
                last_error += " | OpenTopoData 429 Rate Limit"
                continue
            else:
                last_error += f" | OpenTopoData {resp.status_code}: {resp.text}"
                if resp.status_code < 500:
                    break
        except requests.RequestException as e:
            last_error += f" | OpenTopoData Error: {e}"

    raise RuntimeError(f"Elevation API failed. Last errors: {last_error}")


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

    with requests.Session() as session:
        for i in range(0, total, _BATCH_SIZE):
            batch = points[i : i + _BATCH_SIZE]
            lats = [p["lat"] for p in batch]
            lons = [p["lon"] for p in batch]
            elevations = _fetch_batch(lats, lons, session=session)
            all_elevations.extend(elevations)

            if progress_callback:
                progress_callback(min(i + _BATCH_SIZE, total), total)

    for point, z in zip(points, all_elevations):
        point["z_terrain_m"] = float(z)

    return points
