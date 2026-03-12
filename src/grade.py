"""
grade.py
Constrained grade line optimisation (V10 algorithm).
Minimises total earthworks volume subject to:
  - max longitudinal slope (%)
  - max cut/fill height (m)
"""

import numpy as np
from scipy.optimize import minimize_scalar
from typing import List, Dict, Tuple

from src.types import StationList


def _apply_grade_constraints(
    z_terrain: np.ndarray,
    x_stations: np.ndarray,
    offset: float,
    max_slope_pct: float,
    max_height_m: float,
) -> np.ndarray:
    """
    Build a constrained grade line that satisfies both:
      - max cut/fill height envelope
      - max longitudinal slope

    The method tightens feasible envelopes with forward/backward passes and
    then projects the target grade into the feasible region.
    """
    target = z_terrain + offset
    lower = z_terrain - max_height_m
    upper = z_terrain + max_height_m

    max_slope = max_slope_pct / 100.0
    dx = np.diff(x_stations)
    n = len(target)

    if n == 0:
        return target

    # Tighten feasible envelopes from left to right.
    for i in range(1, n):
        step = max_slope * dx[i - 1]
        lower[i] = max(lower[i], lower[i - 1] - step)
        upper[i] = min(upper[i], upper[i - 1] + step)
        if lower[i] > upper[i]:
            mid = (lower[i] + upper[i]) * 0.5
            lower[i] = mid
            upper[i] = mid

    # Tighten feasible envelopes from right to left.
    for i in range(n - 2, -1, -1):
        step = max_slope * dx[i]
        lower[i] = max(lower[i], lower[i + 1] - step)
        upper[i] = min(upper[i], upper[i + 1] + step)
        if lower[i] > upper[i]:
            mid = (lower[i] + upper[i]) * 0.5
            lower[i] = mid
            upper[i] = mid

    # Project target profile into the feasible region while preserving continuity.
    g = np.empty(n, dtype=np.float64)
    g[0] = np.clip(target[0], lower[0], upper[0])
    for i in range(1, n):
        step = max_slope * dx[i - 1]
        lo = max(lower[i], g[i - 1] - step)
        hi = min(upper[i], g[i - 1] + step)
        if lo > hi:
            mid = (lo + hi) * 0.5
            lo = mid
            hi = mid
        g[i] = np.clip(target[i], lo, hi)

    # Backward polish to reduce residual drift and keep feasibility.
    for i in range(n - 2, -1, -1):
        step = max_slope * dx[i]
        lo = max(lower[i], g[i + 1] - step)
        hi = min(upper[i], g[i + 1] + step)
        if lo > hi:
            mid = (lo + hi) * 0.5
            lo = mid
            hi = mid
        g[i] = np.clip(g[i], lo, hi)

    return g


def _compute_volumes(
    z_grade: np.ndarray,
    z_terrain: np.ndarray,
    x_stations: np.ndarray,
    road_width_m: float,
    cut_slope_hv: float,
    fill_slope_hv: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute incremental cut/fill areas and volumes using prismatoid method.

    Cross-section (trapezoidal):
      cut:  A = width * h_cut + cut_slope * h_cut²
      fill: A = width * h_fill + fill_slope * h_fill²
    """
    h = z_grade - z_terrain
    h_cut  = np.maximum(-h, 0.0)
    h_fill = np.maximum( h, 0.0)

    a_cut  = road_width_m * h_cut  + cut_slope_hv  * h_cut  ** 2
    a_fill = road_width_m * h_fill + fill_slope_hv * h_fill ** 2

    dx = np.diff(x_stations)

    # Prismatoid formula: V = (A1 + A2 + 4*Am) * L / 6
    # where Am is cross-sectional area at midpoint between stations
    # This is more accurate than average-end-area for irregular terrain

    # Calculate heights at midpoints (linear interpolation)
    h_cut_mid  = (h_cut[:-1] + h_cut[1:]) * 0.5
    h_fill_mid = (h_fill[:-1] + h_fill[1:]) * 0.5

    # Calculate areas at midpoints
    a_cut_mid  = road_width_m * h_cut_mid  + cut_slope_hv  * h_cut_mid  ** 2
    a_fill_mid = road_width_m * h_fill_mid + fill_slope_hv * h_fill_mid ** 2

    # Apply prismatoid formula
    v_cut  = (a_cut[:-1] + a_cut[1:] + 4.0 * a_cut_mid)  * dx / 6.0
    v_fill = (a_fill[:-1] + a_fill[1:] + 4.0 * a_fill_mid) * dx / 6.0

    return v_cut, v_fill, h_cut, h_fill


def compute_grade(
    station_points: StationList,
    road_width_m: float = 6.0,
    max_slope_pct: float = 16.0,
    max_height_m: float = 10.0,
    cut_slope_hv: float = 1.0,
    fill_slope_hv: float = 1.5,
    shrink_swell: float = 1.125,
    objective_mode: str = "balanced",
) -> StationList:
    """
    Given station points (with z_terrain_m), compute the optimal grade line
    and return enriched station dicts with cut/fill geometry.

    Args:
        station_points: from stationing.build_stationing()
        road_width_m:   platform width in metres
        max_slope_pct:  maximum longitudinal slope (%)
        max_height_m:   maximum cut or fill height (m)
        cut_slope_hv:   cut side slope H:V ratio
        fill_slope_hv:  fill side slope H:V ratio
        shrink_swell:   volume correction factor (> 1 = swell)
        objective_mode: "balanced" (target cut≈fill after factor)
                        or "min_volume" (minimum total earthworks)

    Returns:
        same list enriched with z_grade_m, cut_height_m, fill_height_m,
        cut_area_m2, fill_area_m2, cut_vol_m3, fill_vol_m3 (incremental),
        cut_vol_cum_m3, fill_vol_cum_m3
    """
    x = np.fromiter((p["station_m"]  for p in station_points), dtype=np.float64)
    z = np.fromiter((p["z_terrain_m"] for p in station_points), dtype=np.float64)
    n = len(x)

    def _metrics(offset):
        g = _apply_grade_constraints(z, x, offset, max_slope_pct, max_height_m)
        vc, vf, _, _ = _compute_volumes(g, z, x, road_width_m, cut_slope_hv, fill_slope_hv)
        cut_total = float(np.sum(vc))
        fill_total = float(np.sum(vf))
        total = cut_total + fill_total
        net = cut_total * shrink_swell - fill_total
        return total, net

    def total_vol(offset):
        total, _ = _metrics(offset)
        return total

    def balance_obj(offset):
        total, net = _metrics(offset)
        # Prioritise mass balance; tiny total-volume tie-breaker avoids unstable flats
        return abs(net) + (1e-6 * total)

    objective_fn = total_vol if objective_mode == "min_volume" else balance_obj

    # Global 1D search first (objective is not guaranteed unimodal), then local refine.
    grid = np.linspace(-max_height_m, max_height_m, 321)
    obj_vals = np.fromiter((objective_fn(off) for off in grid), dtype=np.float64)
    best_idx = int(np.argmin(obj_vals))
    best_off = float(grid[best_idx])
    best_obj = float(obj_vals[best_idx])

    lo = float(grid[max(best_idx - 1, 0)])
    hi = float(grid[min(best_idx + 1, len(grid) - 1)])
    if hi > lo:
        local = minimize_scalar(objective_fn, bounds=(lo, hi), method="bounded")
        if local.success and float(local.fun) <= best_obj:
            best_off = float(local.x)

    g_final = _apply_grade_constraints(z, x, best_off, max_slope_pct, max_height_m)
    v_cut_inc, v_fill_inc, h_cut, h_fill = _compute_volumes(
        g_final, z, x, road_width_m, cut_slope_hv, fill_slope_hv
    )

    # Areas per station (fully vectorised)
    a_cut  = road_width_m * h_cut  + cut_slope_hv  * h_cut  ** 2
    a_fill = road_width_m * h_fill + fill_slope_hv * h_fill ** 2

    # Incremental volumes: station[0] = 0, station[i] = v_inc[i-1]
    v_cut_col  = np.empty(n); v_cut_col [0] = 0.0; v_cut_col [1:] = v_cut_inc
    v_fill_col = np.empty(n); v_fill_col[0] = 0.0; v_fill_col[1:] = v_fill_inc

    v_cut_cum  = np.cumsum(v_cut_col)
    v_fill_cum = np.cumsum(v_fill_col)

    # Grade slope per station (vectorised)
    g_slope = np.empty(n); g_slope[0] = 0.0
    if n > 1:
        dz = np.diff(g_final)
        dx_arr = np.diff(x)
        g_slope[1:] = np.where(dx_arr > 0, dz / dx_arr * 100.0, 0.0)

    # Round all arrays once
    g_final    = np.round(g_final,    2)
    g_slope    = np.round(g_slope,    2)
    h_cut      = np.round(h_cut,      2)
    h_fill     = np.round(h_fill,     2)
    a_cut      = np.round(a_cut,      2)
    a_fill     = np.round(a_fill,     2)
    v_cut_col  = np.round(v_cut_col,  2)
    v_fill_col = np.round(v_fill_col, 2)
    v_cut_cum  = np.round(v_cut_cum,  2)
    v_fill_cum = np.round(v_fill_cum, 2)

    # Build enriched list with a single vectorised zip (avoids per-element round/float)
    enriched = [
        {
            **pt,
            "z_grade_m":       float(g_final   [i]),
            "grade_slope_pct": float(g_slope   [i]),
            "cut_height_m":    float(h_cut     [i]),
            "fill_height_m":   float(h_fill    [i]),
            "cut_area_m2":     float(a_cut     [i]),
            "fill_area_m2":    float(a_fill    [i]),
            "cut_vol_m3":      float(v_cut_col [i]),
            "fill_vol_m3":     float(v_fill_col[i]),
            "cut_vol_cum_m3":  float(v_cut_cum [i]),
            "fill_vol_cum_m3": float(v_fill_cum[i]),
            # Road geometry params (needed by cross-section and 3D plots)
            "road_width_m":  road_width_m,
            "cut_slope_hv":  cut_slope_hv,
            "fill_slope_hv": fill_slope_hv,
        }
        for i, pt in enumerate(station_points)
    ]

    return enriched
