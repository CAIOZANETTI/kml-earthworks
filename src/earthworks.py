"""
earthworks.py
Aggregate cut/fill results into per-segment and overall summaries.
Segment = one access alignment (file_name + access_id).
"""

import pandas as pd
from typing import List, Dict

from src.types import AlignmentWithStationsList, OverallKPIs


def build_dataframe(
    alignments_data: AlignmentWithStationsList,
    shrink_swell: float = 1.125,
) -> pd.DataFrame:
    """
    Combine all enriched station points from multiple alignments into
    a single tidy DataFrame with file_name and access_id columns.

    Args:
        alignments_data: list of {"file_name", "access_id", "stations": [...]}
        shrink_swell: factor applied to cut volume for mass balance

    Returns:
        pd.DataFrame with all per-station columns
    """
    rows = []
    for alignment in alignments_data:
        for pt in alignment["stations"]:
            rows.append(
                {
                    "file_name": alignment["file_name"],
                    "access_id": alignment["access_id"],
                    **pt,
                }
            )

    df = pd.DataFrame(rows)

    # Recalculate cumulative volumes per alignment to ensure correctness
    # when multiple alignments are concatenated
    df["cut_vol_cum_m3"] = df.groupby(["file_name", "access_id"])["cut_vol_m3"].cumsum()
    df["fill_vol_cum_m3"] = df.groupby(["file_name", "access_id"])["fill_vol_m3"].cumsum()

    # Mass balance calculation using shrink/swell factor
    #
    # Engineering convention (shrink_swell > 1.0):
    #   - Cut volume is measured in-situ (natural ground, compacted by nature)
    #   - When excavated, soil expands (~15-30% swell during transport)
    #   - When recompacted as fill, soil shrinks but doesn't reach original in-situ density
    #   - Net effect: Need more cut volume than fill volume to achieve mass balance
    #
    # Example with shrink_swell = 1.125 (12.5% factor):
    #   - To fill 100 m³, you need 112.5 m³ of cut material
    #   - Cut loses density when excavated and doesn't fully recover when recompacted
    #
    # Mass balance formula: cut * shrink_swell - fill
    #   - Positive result = waste (surplus cut material)
    #   - Negative result = borrow (need additional fill material)
    #   - Zero = balanced earthworks (ideal for cost optimization)
    df["mass_balance_m3"] = (
        df["cut_vol_cum_m3"] * shrink_swell - df["fill_vol_cum_m3"]
    )

    return df


def build_segment_summary(df: pd.DataFrame, shrink_swell: float = 1.125) -> pd.DataFrame:
    """
    Produce one summary row per access alignment.

    Returns DataFrame with:
        file_name, access_id, length_m,
        cut_total_m3, fill_total_m3,
        net_m3 (cut*shrink - fill),
        borrow_m3, waste_m3
    """
    records = []
    for (file_name, access_id), grp in df.groupby(["file_name", "access_id"], sort=False):
        length_m = grp["station_m"].max()
        cut_total = grp["cut_vol_m3"].sum()
        fill_total = grp["fill_vol_m3"].sum()
        # Net mass balance: cut * shrink_swell - fill
        # (see detailed explanation in build_dataframe function)
        net = cut_total * shrink_swell - fill_total

        records.append(
            {
                "file_name": file_name,
                "access_id": access_id,
                "length_m": round(length_m, 1),
                "cut_total_m3": round(cut_total, 0),
                "fill_total_m3": round(fill_total, 0),
                "net_m3": round(net, 0),
                "borrow_m3": round(max(-net, 0), 0),
                "waste_m3": round(max(net, 0), 0),
            }
        )

    return pd.DataFrame(records)


def overall_kpis(summary_df: pd.DataFrame) -> OverallKPIs:
    """Return dict of overall KPI values for the header cards."""
    return {
        "total_length_m": summary_df["length_m"].sum(),
        "cut_total_m3": summary_df["cut_total_m3"].sum(),
        "fill_total_m3": summary_df["fill_total_m3"].sum(),
        "borrow_m3": summary_df["borrow_m3"].sum(),
        "waste_m3": summary_df["waste_m3"].sum(),
        "net_m3": summary_df["net_m3"].sum(),
    }
