"""
Unit tests for earthworks.py
Tests DataFrame building, segment summaries, and KPI aggregation.
"""

import pytest
import pandas as pd
from src.earthworks import build_dataframe, build_segment_summary, overall_kpis


class TestBuildDataframe:
    """Tests for build_dataframe function"""

    def test_single_alignment(self):
        """Single alignment should be converted to DataFrame correctly"""
        alignments = [
            {
                "file_name": "test.kml",
                "access_id": "Access_1",
                "stations": [
                    {
                        "station_m": 0.0,
                        "cut_vol_m3": 10.0,
                        "fill_vol_m3": 5.0,
                        "cut_vol_cum_m3": 10.0,
                        "fill_vol_cum_m3": 5.0,
                    },
                    {
                        "station_m": 20.0,
                        "cut_vol_m3": 15.0,
                        "fill_vol_m3": 8.0,
                        "cut_vol_cum_m3": 25.0,
                        "fill_vol_cum_m3": 13.0,
                    },
                ],
            }
        ]

        df = build_dataframe(alignments, shrink_swell=1.125)

        assert len(df) == 2
        assert "file_name" in df.columns
        assert "access_id" in df.columns
        assert "mass_balance_m3" in df.columns
        assert df["file_name"].iloc[0] == "test.kml"
        assert df["access_id"].iloc[0] == "Access_1"

    def test_multiple_alignments(self):
        """Multiple alignments should be concatenated correctly"""
        alignments = [
            {
                "file_name": "file1.kml",
                "access_id": "Access_1",
                "stations": [
                    {"station_m": 0.0, "cut_vol_m3": 10.0, "fill_vol_m3": 5.0},
                ],
            },
            {
                "file_name": "file2.kml",
                "access_id": "Access_2",
                "stations": [
                    {"station_m": 0.0, "cut_vol_m3": 20.0, "fill_vol_m3": 10.0},
                ],
            },
        ]

        df = build_dataframe(alignments, shrink_swell=1.125)

        assert len(df) == 2
        assert df["file_name"].tolist() == ["file1.kml", "file2.kml"]
        assert df["access_id"].tolist() == ["Access_1", "Access_2"]

    def test_cumulative_volumes_recalculated_per_alignment(self):
        """Cumulative volumes should reset for each alignment"""
        alignments = [
            {
                "file_name": "file1.kml",
                "access_id": "Access_1",
                "stations": [
                    {"station_m": 0.0, "cut_vol_m3": 10.0, "fill_vol_m3": 5.0, "cut_vol_cum_m3": 10.0, "fill_vol_cum_m3": 5.0},
                    {"station_m": 20.0, "cut_vol_m3": 10.0, "fill_vol_m3": 5.0, "cut_vol_cum_m3": 20.0, "fill_vol_cum_m3": 10.0},
                ],
            },
            {
                "file_name": "file2.kml",
                "access_id": "Access_2",
                "stations": [
                    {"station_m": 0.0, "cut_vol_m3": 15.0, "fill_vol_m3": 8.0, "cut_vol_cum_m3": 15.0, "fill_vol_cum_m3": 8.0},
                    {"station_m": 20.0, "cut_vol_m3": 15.0, "fill_vol_m3": 8.0, "cut_vol_cum_m3": 30.0, "fill_vol_cum_m3": 16.0},
                ],
            },
        ]

        df = build_dataframe(alignments, shrink_swell=1.125)

        # Check that cumulative volumes are correct per alignment
        access1 = df[df["access_id"] == "Access_1"]
        access2 = df[df["access_id"] == "Access_2"]

        # Access 1 cumulative should be 10, 20
        assert access1["cut_vol_cum_m3"].tolist() == [10.0, 20.0]
        assert access1["fill_vol_cum_m3"].tolist() == [5.0, 10.0]

        # Access 2 cumulative should be 15, 30 (not continuing from Access 1)
        assert access2["cut_vol_cum_m3"].tolist() == [15.0, 30.0]
        assert access2["fill_vol_cum_m3"].tolist() == [8.0, 16.0]

    def test_mass_balance_calculation(self):
        """Mass balance should be calculated correctly"""
        alignments = [
            {
                "file_name": "test.kml",
                "access_id": "Access_1",
                "stations": [
                    {
                        "station_m": 0.0,
                        "cut_vol_m3": 100.0,
                        "fill_vol_m3": 50.0,
                    },
                ],
            }
        ]

        shrink_swell = 1.2
        df = build_dataframe(alignments, shrink_swell=shrink_swell)

        # Mass balance = cut * shrink_swell - fill
        # 100 * 1.2 - 50 = 120 - 50 = 70
        expected_balance = 100.0 * shrink_swell - 50.0
        assert df["mass_balance_m3"].iloc[0] == pytest.approx(expected_balance, abs=0.1)


class TestBuildSegmentSummary:
    """Tests for build_segment_summary function"""

    def test_single_segment_summary(self):
        """Single segment should be summarized correctly"""
        df = pd.DataFrame([
            {
                "file_name": "test.kml",
                "access_id": "Access_1",
                "station_m": 0.0,
                "cut_vol_m3": 10.0,
                "fill_vol_m3": 5.0,
            },
            {
                "file_name": "test.kml",
                "access_id": "Access_1",
                "station_m": 100.0,
                "cut_vol_m3": 15.0,
                "fill_vol_m3": 8.0,
            },
        ])

        summary = build_segment_summary(df, shrink_swell=1.125)

        assert len(summary) == 1
        assert summary["file_name"].iloc[0] == "test.kml"
        assert summary["access_id"].iloc[0] == "Access_1"
        assert summary["length_m"].iloc[0] == 100.0
        assert summary["cut_total_m3"].iloc[0] == 25.0  # 10 + 15
        assert summary["fill_total_m3"].iloc[0] == 13.0  # 5 + 8

    def test_multiple_segments_summary(self):
        """Multiple segments should be summarized separately"""
        df = pd.DataFrame([
            {"file_name": "file1.kml", "access_id": "Access_1", "station_m": 50.0, "cut_vol_m3": 10.0, "fill_vol_m3": 5.0},
            {"file_name": "file2.kml", "access_id": "Access_2", "station_m": 75.0, "cut_vol_m3": 20.0, "fill_vol_m3": 10.0},
        ])

        summary = build_segment_summary(df, shrink_swell=1.125)

        assert len(summary) == 2
        assert summary["length_m"].tolist() == [50.0, 75.0]

    def test_net_volume_calculation(self):
        """Net volume should account for shrink/swell"""
        df = pd.DataFrame([
            {
                "file_name": "test.kml",
                "access_id": "Access_1",
                "station_m": 100.0,
                "cut_vol_m3": 100.0,
                "fill_vol_m3": 50.0,
            },
        ])

        shrink_swell = 1.2
        summary = build_segment_summary(df, shrink_swell=shrink_swell)

        # net = cut * shrink_swell - fill = 100 * 1.2 - 50 = 70
        expected_net = 100.0 * shrink_swell - 50.0
        assert summary["net_m3"].iloc[0] == pytest.approx(expected_net, abs=0.1)

    def test_borrow_waste_calculation(self):
        """Borrow and waste should be calculated correctly"""
        df = pd.DataFrame([
            # Surplus cut (waste)
            {"file_name": "test1.kml", "access_id": "Access_1", "station_m": 100.0, "cut_vol_m3": 100.0, "fill_vol_m3": 50.0},
            # Deficit (borrow needed)
            {"file_name": "test2.kml", "access_id": "Access_2", "station_m": 100.0, "cut_vol_m3": 50.0, "fill_vol_m3": 100.0},
        ])

        summary = build_segment_summary(df, shrink_swell=1.0)  # No shrink/swell for simplicity

        # Access_1: net = 100 - 50 = 50 (waste)
        assert summary.iloc[0]["waste_m3"] == 50.0
        assert summary.iloc[0]["borrow_m3"] == 0.0

        # Access_2: net = 50 - 100 = -50 (borrow)
        assert summary.iloc[1]["waste_m3"] == 0.0
        assert summary.iloc[1]["borrow_m3"] == 50.0


class TestOverallKPIs:
    """Tests for overall_kpis function"""

    def test_overall_kpis_aggregation(self):
        """Overall KPIs should sum across all segments"""
        summary_df = pd.DataFrame([
            {
                "length_m": 100.0,
                "cut_total_m3": 50.0,
                "fill_total_m3": 30.0,
                "borrow_m3": 0.0,
                "waste_m3": 20.0,
                "net_m3": 20.0,
            },
            {
                "length_m": 150.0,
                "cut_total_m3": 80.0,
                "fill_total_m3": 60.0,
                "borrow_m3": 0.0,
                "waste_m3": 20.0,
                "net_m3": 20.0,
            },
        ])

        kpis = overall_kpis(summary_df)

        assert kpis["total_length_m"] == 250.0
        assert kpis["cut_total_m3"] == 130.0
        assert kpis["fill_total_m3"] == 90.0
        assert kpis["borrow_m3"] == 0.0
        assert kpis["waste_m3"] == 40.0
        assert kpis["net_m3"] == 40.0

    def test_kpis_empty_dataframe(self):
        """KPIs for empty DataFrame should be zero"""
        summary_df = pd.DataFrame(columns=[
            "length_m", "cut_total_m3", "fill_total_m3",
            "borrow_m3", "waste_m3", "net_m3"
        ])

        kpis = overall_kpis(summary_df)

        assert kpis["total_length_m"] == 0.0
        assert kpis["cut_total_m3"] == 0.0
        assert kpis["fill_total_m3"] == 0.0
        assert kpis["borrow_m3"] == 0.0
        assert kpis["waste_m3"] == 0.0
        assert kpis["net_m3"] == 0.0
