"""
types.py
Type definitions for KML Earthworks data structures.
Uses TypedDict for better IDE support and type checking.
"""

from typing import TypedDict, List


class Point(TypedDict, total=False):
    """
    Basic coordinate point with optional elevation.

    Required fields: lat, lon
    Optional fields: z_terrain_m
    """
    lat: float
    lon: float
    z_terrain_m: float  # Added by elevation enrichment


class StationPoint(TypedDict, total=False):
    """
    Station point with terrain data and optional grade line results.

    Inherits Point fields and adds stationing and earthworks data.
    """
    # From Point
    lat: float
    lon: float
    z_terrain_m: float

    # From stationing
    station_m: float
    stake_20m: bool
    terrain_slope_pct: float

    # From grade computation
    z_grade_m: float
    grade_slope_pct: float
    cut_height_m: float
    fill_height_m: float
    cut_area_m2: float
    fill_area_m2: float
    cut_vol_m3: float
    fill_vol_m3: float
    cut_vol_cum_m3: float
    fill_vol_cum_m3: float

    # Road geometry params
    road_width_m: float
    cut_slope_hv: float
    fill_slope_hv: float


class Alignment(TypedDict):
    """
    KML alignment with points or station data.
    """
    file_name: str
    access_id: str
    points: List[Point]


class AlignmentWithStations(TypedDict):
    """
    Alignment with processed station data.
    """
    file_name: str
    access_id: str
    stations: List[StationPoint]


class ValidationReport(TypedDict):
    """
    Validation report for elevation enrichment.
    """
    missing_count: int
    total_count: int
    success_rate: float
    failed_batches: List[tuple]  # List of (batch_index, batch_size)


class SegmentSummary(TypedDict):
    """
    Summary statistics for one alignment segment.
    """
    file_name: str
    access_id: str
    length_m: float
    cut_total_m3: float
    fill_total_m3: float
    net_m3: float
    borrow_m3: float
    waste_m3: float


class OverallKPIs(TypedDict):
    """
    Overall project KPIs aggregated across all alignments.
    """
    total_length_m: float
    cut_total_m3: float
    fill_total_m3: float
    borrow_m3: float
    waste_m3: float
    net_m3: float


# Type aliases for clearer function signatures
PointList = List[Point]
StationList = List[StationPoint]
AlignmentList = List[Alignment]
AlignmentWithStationsList = List[AlignmentWithStations]
