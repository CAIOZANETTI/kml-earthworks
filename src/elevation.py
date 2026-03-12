"""
elevation.py
Fetch terrain elevation for coordinates using Open-Meteo Elevation API.
Free, no API key required.
"""

import re
import time
import requests
from typing import Dict, List, Optional, Tuple

from src.logger import get_logger
from src.types import PointList, ValidationReport

logger = get_logger(__name__)


_API_URL = "https://api.open-meteo.com/v1/elevation"
_BATCH_SIZE = 100
_METEO_TIMEOUT = (3, 8)
_TOPO_TIMEOUT = (3, 12)
_METEO_RETRY_DELAYS = [0, 0.5]
_TOPO_RETRY_DELAYS = [0, 1, 3]
_TOPO_RATE_LIMIT_DELAY_S = 0.8
_METEO_COOLDOWN_DEFAULT_S = 60


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
    cooldown_state: Optional[Dict] = None,
) -> List[float]:
    """Fetch elevation for a single batch with retry and fallback logic.

    Args:
        cooldown_state: Optional dict to store cooldown state across calls.
                       Should have a 'meteo_cooldown_until' key.
                       If None, creates a module-level fallback (not session-safe).
    """
    if cooldown_state is None:
        cooldown_state = {}

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
    meteo_cooldown_until = cooldown_state.get('meteo_cooldown_until', 0.0)
    meteo_ready = now >= meteo_cooldown_until

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
                new_cooldown_until = time.time() + cooldown
                cooldown_state['meteo_cooldown_until'] = max(meteo_cooldown_until, new_cooldown_until)
                details = reason.strip() or f"cooldown {cooldown}s"
                last_error = f"Open-Meteo 429 Rate Limit: {details}"
                break

            last_error = f"Open-Meteo {resp.status_code}: {resp.text}"
            if resp.status_code < 500:
                break
    else:
        remaining = max(1, int(meteo_cooldown_until - now))
        last_error = f"Open-Meteo cooldown active ({remaining}s remaining)"
    
    # Fallback to OpenTopoData (using POST to avoid URL length limits)
    for delay in _TOPO_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            resp = http.post(url_topo, data=topo_data, timeout=_TOPO_TIMEOUT)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                # Use None for missing elevation data (not 0.0, which is valid sea level)
                elevations = [r.get("elevation") for r in results]
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


def enrich_elevation(
    points: PointList,
    progress_callback=None,
    cooldown_state: Optional[Dict] = None
) -> Tuple[PointList, ValidationReport]:
    """
    Add 'z_terrain_m' to each point dict.

    Args:
        points: list of {"lat": float, "lon": float, ...}
        progress_callback: optional callable(processed, total) for UI updates
        cooldown_state: Optional dict to store API cooldown state across calls.
                       Use st.session_state in Streamlit to avoid cross-session interference.

    Returns:
        Tuple of (enriched points list, validation dict with keys:
            - 'missing_count': number of points with missing/zero elevation
            - 'total_count': total number of points
            - 'success_rate': percentage of successful elevations
        )
    """
    total = len(points)
    all_elevations = []
    failed_batches = []

    with requests.Session() as session:
        for i in range(0, total, _BATCH_SIZE):
            batch = points[i : i + _BATCH_SIZE]
            lats = [p["lat"] for p in batch]
            lons = [p["lon"] for p in batch]

            try:
                elevations = _fetch_batch(lats, lons, session=session, cooldown_state=cooldown_state)
                all_elevations.extend(elevations)
            except RuntimeError as e:
                logger.error(f"Failed to fetch elevation for batch at index {i}: {e}")
                # Use None as marker for failed batch (0.0 is valid sea level)
                all_elevations.extend([None] * len(batch))
                failed_batches.append((i, len(batch)))

            if progress_callback:
                progress_callback(min(i + _BATCH_SIZE, total), total)

    # Count only truly missing elevations (None), not sea level (0.0)
    missing_count = 0
    for point, z in zip(points, all_elevations):
        if z is None:
            missing_count += 1
            point["z_terrain_m"] = 0.0  # Fallback to 0.0 for backward compatibility
        else:
            point["z_terrain_m"] = float(z)

    # Build validation report
    validation = {
        'missing_count': missing_count,
        'total_count': total,
        'success_rate': ((total - missing_count) / total * 100) if total > 0 else 0.0,
        'failed_batches': failed_batches,
    }

    if missing_count > 0:
        failure_rate = 100 - validation['success_rate']
        logger.warning(
            f"Elevation data missing for {missing_count}/{total} points "
            f"({failure_rate:.1f}% failure rate)"
        )

        # CRITICAL: Stop execution if too many points failed
        # Using fallback 0.0 elevation produces incorrect earthworks calculations
        if failure_rate > 10.0:
            raise RuntimeError(
                f"Elevation data failed for {failure_rate:.1f}% of points "
                f"({missing_count}/{total}). Cannot proceed with unreliable data. "
                f"Check API rate limits and connectivity."
            )

    return points, validation
