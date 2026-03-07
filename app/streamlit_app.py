"""
streamlit_app.py
kml-earthworks — KML → Terrain Profiles → Cut/Fill Volumes
"""

import sys
import os
import uuid
import inspect
import hashlib
import time

# Allow imports from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd

from src.io_kml import parse_multiple_kml
from src.elevation import enrich_elevation
from src.stationing import build_stationing
from src.grade import compute_grade
from src.earthworks import build_dataframe, build_segment_summary, overall_kpis
from src import plots, exports, db

_COMPUTE_GRADE_SUPPORTS_OBJECTIVE = "objective_mode" in inspect.signature(compute_grade).parameters

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KML Earthworks",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Hero header */
    .hero {
        background: linear-gradient(135deg, #1A1A2E 0%, #16213E 60%, #0F3460 100%);
        color: white;
        padding: 1.75rem 2rem;
        border-radius: 0.75rem;
        margin-bottom: 1.5rem;
    }
    .hero h1 { font-size: 2rem; font-weight: 800; margin: 0; letter-spacing: -0.02em; }
    .hero p  { opacity: 0.75; margin: 0.25rem 0 0; font-size: 0.95rem; }

    /* KPI metric cards */
    [data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #E8EAF0;
        border-radius: 0.65rem;
        padding: 0.75rem 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem; text-transform: uppercase;
                                    letter-spacing: 0.06em; opacity: 0.6; }

    /* Sidebar */
    [data-testid="stSidebar"] { background: #F7F8FC; }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div { color: #1A1A2E !important; }
    .sidebar-title { font-weight: 700; font-size: 0.7rem; text-transform: uppercase;
                     letter-spacing: 0.1em; color: #888 !important; margin: 1rem 0 0.25rem; }

    /* Tab strip */
    [data-testid="stTab"] { font-weight: 600; }

    /* Download buttons */
    .stDownloadButton button {
        background: #0F3460; color: white; border: none;
        border-radius: 0.5rem; font-weight: 600;
    }
    .stDownloadButton button:hover { background: #16213E; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ──────────────────────────────────────────────────────────────────────────────
for key in (
    "results_df",
    "summary_df",
    "kpis",
    "figures",
    "params_used",
    "base_alignments",
    "base_input_signature",
    "base_input_label",
    "applied_design_params",
    "last_design_signature",
    "access_log_id",
):
    if key not in st.session_state:
        st.session_state[key] = None

if "last_exit_ping_ts" not in st.session_state:
    st.session_state.last_exit_ping_ts = 0.0

if "auto_update_design" not in st.session_state:
    st.session_state.auto_update_design = True

if "lead_submitted" not in st.session_state:
    st.session_state.lead_submitted = True

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    row_id = db.log_access(st.session_state.session_id)
    if row_id:
        st.session_state.access_log_id = row_id
        st.session_state.last_exit_ping_ts = time.time()

# Best-effort "last seen": updates exit_time periodically during active reruns.
if st.session_state.access_log_id:
    now_ts = time.time()
    if now_ts - float(st.session_state.last_exit_ping_ts or 0.0) >= 30.0:
        db.update_access_exit_time(st.session_state.access_log_id)
        st.session_state.last_exit_ping_ts = now_ts


def _make_input_signature(data_source: str, sample_choice, files_data):
    if data_source == "Use a sample KML":
        return ("sample", sample_choice) if sample_choice else None
    if not files_data:
        return None
    files_sig = []
    for f in files_data:
        payload = f["content"]
        payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.md5(payload_bytes).hexdigest()[:12]
        files_sig.append((f["name"], len(payload_bytes), digest))
    return ("upload", tuple(sorted(files_sig)))


def _design_signature(params: dict):
    objective_tag = params["objective_mode"] if _COMPUTE_GRADE_SUPPORTS_OBJECTIVE else "legacy_min_volume"
    return (
        round(float(params["road_width_m"]), 3),
        round(float(params["max_slope_pct"]), 3),
        round(float(params["cut_slope_hv"]), 3),
        round(float(params["fill_slope_hv"]), 3),
        round(float(params["shrink_swell"]), 6),
        round(float(params["max_height_m"]), 3),
        objective_tag,
    )


def _run_design_from_base(base_alignments, design_params: dict):
    """Recompute grade/volumes/charts using cached station base (no elevation API)."""
    alignments_data = []
    for a in base_alignments:
        grade_kwargs = dict(
            road_width_m=design_params["road_width_m"],
            max_slope_pct=design_params["max_slope_pct"],
            max_height_m=design_params["max_height_m"],
            cut_slope_hv=design_params["cut_slope_hv"],
            fill_slope_hv=design_params["fill_slope_hv"],
            shrink_swell=design_params["shrink_swell"],
        )
        if _COMPUTE_GRADE_SUPPORTS_OBJECTIVE:
            grade_kwargs["objective_mode"] = design_params["objective_mode"]

        try:
            stations = compute_grade(a["stations_base"], **grade_kwargs)
        except TypeError as exc:
            if "objective_mode" in str(exc):
                grade_kwargs.pop("objective_mode", None)
                stations = compute_grade(a["stations_base"], **grade_kwargs)
            else:
                raise

        alignments_data.append(
            {
                "file_name": a["file_name"],
                "access_id": a["access_id"],
                "stations": stations,
            }
        )

    results_df = build_dataframe(alignments_data, shrink_swell=design_params["shrink_swell"])
    summary_df = build_segment_summary(results_df, shrink_swell=design_params["shrink_swell"])
    kpis = overall_kpis(summary_df)

    figs = {
        "Plan View": plots.fig_plan_view(results_df),
        "Profile": plots.fig_profile(results_df),
        "Cut / Fill Heights": plots.fig_cut_fill_bars(results_df),
        "Mass Diagram": plots.fig_mass_diagram(results_df, design_params["shrink_swell"]),
    }

    params_used = {
        "Input Method": st.session_state.base_input_label or "Cached Base",
        "Road width": f"{design_params['road_width_m']} m",
        "Max slope": f"{design_params['max_slope_pct']} %",
        "Cut side slope": f"{design_params['cut_slope_hv']} H:V",
        "Fill side slope": f"{design_params['fill_slope_hv']} H:V",
        "Shrink/Swell factor": f"{design_params['shrink_swell']:.3f}",
        "Max cut/fill height": f"{design_params['max_height_m']} m",
        "Earthworks objective": (
            design_params["objective_label"]
            if _COMPUTE_GRADE_SUPPORTS_OBJECTIVE
            else "Legacy engine (min total volume)"
        ),
        "Stake interval": "20 m",
        "Elevation source": "Open-Meteo (free, ~30 m resolution)",
    }

    st.session_state.results_df = results_df
    st.session_state.summary_df = summary_df
    st.session_state.kpis = kpis
    st.session_state.figures = figs
    st.session_state.params_used = params_used
    st.session_state.applied_design_params = design_params.copy()
    st.session_state.last_design_signature = _design_signature(design_params)

# ──────────────────────────────────────────────────────────────────────────────
# HERO
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero">
      <h1>⛏️ KML Earthworks</h1>
      <p>Upload Google Earth alignments → terrain profiles → cut &amp; fill volumes, instantly.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# MAIN AREA — UPLOAD
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("### Input Data")
data_source = st.radio(
    "Choose input method:", 
    ["Upload your own KML", "Use a sample KML"],
    horizontal=True
)

files_data = []
sample_choice = None

if data_source == "Upload your own KML":
    uploaded_files = st.file_uploader(
        "KML files",
        type=["kml"],
        accept_multiple_files=True,
        help="Draw LineStrings in Google Earth, export as KML, upload here.",
        disabled=not st.session_state.lead_submitted,
    )
    if uploaded_files:
        files_data = [{"name": f.name, "content": f.read()} for f in uploaded_files]
else:
    sample_choice = st.pills("Select a sample to analyze:", ["AC-2.kml", "AC-3.kml", "AC-4.kml"])

# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR — PARAMETERS
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="sidebar-title">Road Parameters</p>', unsafe_allow_html=True)
    road_width   = st.slider("Road width (m)",        3.0, 12.0, 6.0, 0.5)
    max_slope    = st.slider("Max slope (%)",          2.0, 20.0, 16.0, 0.5)
    cut_slope    = st.slider("Cut side slope (H:V)",  1.0,  3.0,  1.0, 0.25)
    fill_slope   = st.slider("Fill side slope (H:V)", 1.0,  3.0,  1.5, 0.25)
    shrink_swell = st.slider("Shrink/Swell factor",  0.90, 1.30, 1.125, 0.005, format="%.3f")
    max_height   = st.slider("Max cut/fill height (m)", 2.0, 20.0, 10.0, 0.5)
    objective_label = st.radio(
        "Earthworks objective",
        ["Balanced mass", "Minimum total volume"],
        horizontal=False,
        help="Balanced mass targets cut≈fill after shrink/swell. Minimum total volume reduces total movement regardless of balance.",
    )
    objective_mode = "balanced" if objective_label == "Balanced mass" else "min_volume"
    st.markdown('<p class="sidebar-title">Design Updates</p>', unsafe_allow_html=True)
    auto_update_design = st.toggle(
        "Auto-update design",
        key="auto_update_design",
        help="Recalculate cut/fill, KPIs and charts automatically when parameters change (without refetching elevation).",
    )
    update_design_clicked = st.button(
        "🔄 Update design",
        use_container_width=True,
        disabled=st.session_state.base_alignments is None,
    )
    st.markdown("---")
    st.markdown("### Feedback")
    st.caption("Tell me what you liked and what can be improved.")
    st.markdown("Contact: **caiozanetti@gmail.com**")

design_params = {
    "road_width_m": road_width,
    "max_slope_pct": max_slope,
    "cut_slope_hv": cut_slope,
    "fill_slope_hv": fill_slope,
    "shrink_swell": shrink_swell,
    "max_height_m": max_height,
    "objective_mode": objective_mode,
    "objective_label": objective_label,
}

run_disabled = False
if data_source == "Upload your own KML" and not files_data:
    run_disabled = True
elif data_source == "Use a sample KML" and not sample_choice:
    run_disabled = True

st.write("---")
# Main Content Area Bottom
run = st.button(
    "⚡ Run Analysis",
    type="primary",
    use_container_width=True,
    disabled=run_disabled or not st.session_state.lead_submitted,
)


# ──────────────────────────────────────────────────────────────────────────────
# RUN PIPELINE
# ──────────────────────────────────────────────────────────────────────────────
current_input_signature = _make_input_signature(data_source, sample_choice, files_data)
input_changed_since_base = False
design_outdated = False

if run and not run_disabled:
    if data_source == "Use a sample KML" and sample_choice:
        try:
            with open(os.path.join(os.path.dirname(__file__), "..", "sample", sample_choice), "r") as f:
                files_data = [{"name": sample_choice, "content": f.read()}]
        except Exception as e:
            st.error(f"Error loading sample: {e}")
            files_data = []

    if files_data:
        with st.status("Processing alignments…", expanded=True) as status:
            # 1. Parse KML
            st.write("📂 Parsing KML files…")
            alignments = parse_multiple_kml(files_data)
            if not alignments:
                st.error("No LineString alignments found in the uploaded files.")
                st.stop()
            st.write(f"   → {len(alignments)} alignment(s) detected")

            # 2. Elevation
            st.write("🌍 Fetching terrain elevations (Open-Meteo)…")
            progress_bar = st.progress(0)

            def update_progress(done, total):
                progress_bar.progress(done / total)

            all_points_flat = [p for a in alignments for p in a["points"]]
            enrich_elevation(all_points_flat, progress_callback=update_progress)

            # Re-distribute enriched points back to alignments
            idx = 0
            for a in alignments:
                n = len(a["points"])
                a["points"] = all_points_flat[idx : idx + n]
                idx += n
            progress_bar.empty()
            st.write(f"   → {len(all_points_flat):,} points enriched")

            # 3. Build and cache station base (no design params yet)
            st.write("📏 Building station base…")
            base_alignments = []
            for a in alignments:
                stations_base = build_stationing(a["points"])
                base_alignments.append(
                    {
                        "file_name": a["file_name"],
                        "access_id": a["access_id"],
                        "stations_base": stations_base,
                    }
                )
            st.write(f"   → {sum(len(a['stations_base']) for a in base_alignments):,} station points cached")

            # 4. Save cached base + run design once
            st.session_state.base_alignments = base_alignments
            st.session_state.base_input_signature = _make_input_signature(data_source, sample_choice, files_data)
            st.session_state.base_input_label = (
                f"Sample: {sample_choice}" if data_source == "Use a sample KML" else "Custom Upload"
            )

            st.write("📊 Updating engineering outputs…")
            _run_design_from_base(base_alignments, design_params)

            status.update(label="✅ Analysis complete!", state="complete")

# Recalculate from cached base when only design parameters changed
if st.session_state.base_alignments is not None:
    if current_input_signature is not None and st.session_state.base_input_signature != current_input_signature:
        input_changed_since_base = True
    else:
        latest_sig = st.session_state.last_design_signature
        current_sig = _design_signature(design_params)
        design_outdated = latest_sig is not None and current_sig != latest_sig
        if design_outdated and (auto_update_design or update_design_clicked):
            with st.spinner("Updating design from cached base…"):
                _run_design_from_base(st.session_state.base_alignments, design_params)
            design_outdated = False

# ──────────────────────────────────────────────────────────────────────────────
# RESULTS
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.results_df is not None:
    df        = st.session_state.results_df
    summary   = st.session_state.summary_df
    kpis      = st.session_state.kpis
    figs      = st.session_state.figures
    params    = st.session_state.params_used
    applied_design = st.session_state.applied_design_params or design_params
    active_shrink_swell = float(applied_design["shrink_swell"])
    active_max_slope = float(applied_design["max_slope_pct"])
    active_max_height = float(applied_design["max_height_m"])

    if input_changed_since_base:
        st.warning("Input data changed. Click **Run Analysis** to refresh the cached base before updating design.")
    elif design_outdated and not auto_update_design:
        st.info("Parameters changed. Click **Update design** in the sidebar to refresh charts and quantities.")

    # ── KPI strip ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total length",  f"{kpis['total_length_m']:,.0f} m")
    c2.metric("Total cut",     f"{kpis['cut_total_m3']:,.0f} m³")
    c3.metric("Total fill",    f"{kpis['fill_total_m3']:,.0f} m³")
    waste  = kpis["waste_m3"]
    borrow = kpis["borrow_m3"]
    c4.metric("Waste",         f"{waste:,.0f} m³",  delta=None)
    c5.metric("Borrow",        f"{borrow:,.0f} m³", delta=None)

    # ── Engineering sanity checks ──
    max_abs_grade = float(df["grade_slope_pct"].abs().max())
    max_cut_h = float(df["cut_height_m"].max())
    max_fill_h = float(df["fill_height_m"].max())
    eq_cut_total = float(kpis["cut_total_m3"] * active_shrink_swell)
    fill_total = float(kpis["fill_total_m3"])
    imbalance_pct = (abs(eq_cut_total - fill_total) / fill_total * 100.0) if fill_total > 0 else 0.0

    qa_msgs = []
    if max_abs_grade > active_max_slope + 1e-6:
        qa_msgs.append(f"Grade slope exceeds limit: {max_abs_grade:.2f}% > {active_max_slope:.2f}%")
    if max_cut_h > active_max_height + 1e-6 or max_fill_h > active_max_height + 1e-6:
        qa_msgs.append(
            f"Cut/fill height exceeds limit: cut {max_cut_h:.2f} m, fill {max_fill_h:.2f} m (limit {active_max_height:.2f} m)"
        )
    if imbalance_pct > 20:
        qa_msgs.append(f"Mass imbalance is high: {imbalance_pct:.1f}% of fill volume")

    if qa_msgs:
        st.warning("Engineering checks: " + " | ".join(qa_msgs))
    else:
        st.success(
            f"Engineering checks OK: max grade {max_abs_grade:.2f}% | max cut/fill {max_cut_h:.2f}/{max_fill_h:.2f} m | imbalance {imbalance_pct:.1f}%"
        )

    st.divider()

    # ── Tabs ──
    tab_map, tab_profile, tab_xsec, tab_vol, tab_tables, tab_export = st.tabs(
        ["🗺 Plan View", "📈 Profile", "✂ Cross Section", "📊 Volumes", "📋 Tables", "⬇ Export"]
    )

    # ── Filter helpers ──
    access_ids = df["access_id"].unique().tolist()

    with tab_map:
        st.plotly_chart(figs["Plan View"], use_container_width=True)

    with tab_profile:
        sel_acc = st.selectbox("Access alignment", ["All"] + access_ids, key="prof_sel")
        acc_filter = None if sel_acc == "All" else sel_acc
        sub_prof = df[df["access_id"] == acc_filter] if acc_filter else df
        cut_count = int((sub_prof["cut_height_m"] > 0.01).sum())
        fill_count = int((sub_prof["fill_height_m"] > 0.01).sum())
        if cut_count == 0 and fill_count == 0:
            st.info("No cut/fill zones detected for this selection.")
        else:
            st.caption(f"Detected zones: {cut_count} cut stations, {fill_count} fill stations.")
        st.plotly_chart(
            plots.fig_profile(df, acc_filter),
            use_container_width=True,
        )

    with tab_xsec:
        sel_acc_x = st.selectbox("Access alignment", ["All"] + access_ids, key="xsec_sel")
        acc_filter_x = None if sel_acc_x == "All" else sel_acc_x
        sub_x = df[df["access_id"] == acc_filter_x] if acc_filter_x else df

        station_filter = st.radio(
            "Station filter",
            ["All stations", "Cut only", "Fill only"],
            horizontal=True,
            key="xsec_station_filter",
        )

        if station_filter == "Cut only":
            station_pool = sub_x[sub_x["cut_height_m"] > 0.01]
        elif station_filter == "Fill only":
            station_pool = sub_x[sub_x["fill_height_m"] > 0.01]
        else:
            station_pool = sub_x

        if station_pool.empty:
            st.info("No stations match this filter for the selected alignment. Showing all stations.")
            station_pool = sub_x

        quick_pin = st.radio(
            "Quick pin",
            ["Mid", "Max cut", "Max fill"],
            horizontal=True,
            key="xsec_quick_pin",
        )

        station_options = sorted({float(v) for v in station_pool["station_m"].round(2).tolist()})
        if quick_pin == "Max cut":
            target_station = float(sub_x.loc[sub_x["cut_height_m"].idxmax(), "station_m"])
        elif quick_pin == "Max fill":
            target_station = float(sub_x.loc[sub_x["fill_height_m"].idxmax(), "station_m"])
        else:
            target_station = float(station_options[len(station_options) // 2])

        nearest_station = min(station_options, key=lambda s: abs(float(s) - target_station))
        sta_sel = st.select_slider(
            "Station (m)",
            options=station_options,
            value=nearest_station,
            key=f"xsec_sta_{sel_acc_x}_{station_filter}",
        )

        col_xA, col_xB = st.columns([3, 1])
        with col_xA:
            st.plotly_chart(
                plots.fig_cross_section(df, float(sta_sel), acc_filter_x),
                use_container_width=True,
            )
        with col_xB:
            row_x = sub_x.iloc[(sub_x["station_m"] - float(sta_sel)).abs().argsort()[:1]]
            if not row_x.empty:
                r = row_x.iloc[0]
                if r["cut_height_m"] > 0.01:
                    st.caption("Section type: **CUT**")
                elif r["fill_height_m"] > 0.01:
                    st.caption("Section type: **FILL**")
                else:
                    st.caption("Section type: **ON GRADE**")
                st.metric("Terrain elev.", f"{r['z_terrain_m']:.2f} m")
                st.metric("Grade elev.",   f"{r['z_grade_m']:.2f} m")
                st.metric("Cut height",    f"{r['cut_height_m']:.2f} m")
                st.metric("Fill height",   f"{r['fill_height_m']:.2f} m")
                st.metric("Cut area",      f"{r['cut_area_m2']:.1f} m²")
                st.metric("Fill area",     f"{r['fill_area_m2']:.1f} m²")

    with tab_vol:
        sel_acc2 = st.selectbox("Access alignment", ["All"] + access_ids, key="vol_sel")
        acc_filter2 = None if sel_acc2 == "All" else sel_acc2
        sub_vol = df[df["access_id"] == acc_filter2].copy() if acc_filter2 else df.copy()
        if acc_filter2 is None and sub_vol["access_id"].nunique() > 1:
            agg = (
                sub_vol.groupby("station_m", as_index=False)[["cut_vol_m3", "fill_vol_m3"]]
                .sum()
                .sort_values("station_m")
            )
            cut_end = float(agg["cut_vol_m3"].cumsum().iloc[-1]) if not agg.empty else 0.0
            fill_end = float(agg["fill_vol_m3"].cumsum().iloc[-1]) if not agg.empty else 0.0
        else:
            sub_vol = sub_vol.sort_values("station_m")
            cut_end = float(sub_vol["cut_vol_cum_m3"].iloc[-1]) if not sub_vol.empty else 0.0
            fill_end = float(sub_vol["fill_vol_cum_m3"].iloc[-1]) if not sub_vol.empty else 0.0

        cut_equiv = cut_end * active_shrink_swell
        net_bal = cut_equiv - fill_end
        st.caption(
            f"Mass balance formula: (Cut in-situ × {active_shrink_swell:.3f}) - Fill = {net_bal:,.0f} m³."
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cut in-situ", f"{cut_end:,.0f} m³")
        m2.metric("Cut equivalent", f"{cut_equiv:,.0f} m³")
        m3.metric("Fill", f"{fill_end:,.0f} m³")
        m4.metric("Mass balance", f"{net_bal:,.0f} m³")

        st.markdown("#### Cut / Fill Heights")
        st.plotly_chart(
            plots.fig_cut_fill_bars(df, acc_filter2),
            use_container_width=True,
        )
        st.markdown("#### Mass Diagram")
        st.plotly_chart(
            plots.fig_mass_diagram(df, active_shrink_swell, acc_filter2),
            use_container_width=True,
        )

    with tab_tables:
        # ── Segment summary ──
        st.subheader("Segment Summary")
        fmt_summary = summary.copy()
        for col in ["cut_total_m3", "fill_total_m3", "net_m3", "borrow_m3", "waste_m3"]:
            fmt_summary[col] = fmt_summary[col].apply(lambda x: f"{x:,.0f}")
        fmt_summary["length_m"] = fmt_summary["length_m"].apply(lambda x: f"{x:,.0f}")
        st.dataframe(fmt_summary, use_container_width=True, hide_index=True)

        st.divider()

        # ── Detailed table with filters ──
        st.subheader("Station Detail")
        fc1, fc2, fc3, fc4 = st.columns(4)
        filt_acc  = fc1.multiselect("Access", access_ids, default=access_ids)
        filt_type = fc2.radio("Show", ["All", "Cut only", "Fill only"], horizontal=True)
        max_sta   = float(df["station_m"].max())
        filt_sta  = fc3.slider(
            "Station range (m)", 0.0, max_sta, (0.0, max_sta), step=20.0
        )

        filtered = df[df["access_id"].isin(filt_acc)]
        filtered = filtered[
            (filtered["station_m"] >= filt_sta[0]) &
            (filtered["station_m"] <= filt_sta[1])
        ]
        if filt_type == "Cut only":
            filtered = filtered[filtered["cut_height_m"] > 0]
        elif filt_type == "Fill only":
            filtered = filtered[filtered["fill_height_m"] > 0]

        fc4.metric("Rows shown", f"{len(filtered):,}")

        detail_cols = [
            "access_id", "station_m", "z_terrain_m", "z_grade_m",
            "slope_pct", "cut_height_m", "fill_height_m",
            "cut_vol_m3", "fill_vol_m3", "cut_vol_cum_m3", "fill_vol_cum_m3",
        ]
        show_cols = [c for c in detail_cols if c in filtered.columns]
        st.dataframe(
            filtered[show_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "station_m":        st.column_config.NumberColumn("Station (m)",   format="%.0f"),
                "z_terrain_m":      st.column_config.NumberColumn("Terrain (m)",   format="%.2f"),
                "z_grade_m":        st.column_config.NumberColumn("Grade (m)",     format="%.2f"),
                "slope_pct":        st.column_config.NumberColumn("Slope (%)",     format="%.1f"),
                "cut_height_m":     st.column_config.NumberColumn("Cut H (m)",     format="%.2f"),
                "fill_height_m":    st.column_config.NumberColumn("Fill H (m)",    format="%.2f"),
                "cut_vol_m3":       st.column_config.NumberColumn("Cut Vol (m³)",  format="%.1f"),
                "fill_vol_m3":      st.column_config.NumberColumn("Fill Vol (m³)", format="%.1f"),
                "cut_vol_cum_m3":   st.column_config.NumberColumn("Cum Cut (m³)",  format="%.0f"),
                "fill_vol_cum_m3":  st.column_config.NumberColumn("Cum Fill (m³)", format="%.0f"),
            },
        )

    with tab_export:
        st.subheader("Download Results")
        exp1, exp2 = st.columns(2)

        # ── Excel ──
        with exp1:
            st.markdown("#### 📊 Excel Report")
            st.caption("Two sheets: full station table + segment summary.")
            xlsx_bytes = exports.to_excel_bytes(df, summary)
            st.download_button(
                "⬇ Download Excel (.xlsx)",
                data=xlsx_bytes,
                file_name="kml_earthworks_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        # ── HTML ──
        with exp2:
            st.markdown("#### 🌐 HTML Report")
            st.caption("Beautiful self-contained report with all charts embedded.")
            html_str = exports.to_html_report(
                detail_df=df,
                summary_df=summary,
                kpis=kpis,
                figures=figs,
                params=params,
            )
            st.download_button(
                "⬇ Download HTML Report",
                data=html_str.encode("utf-8"),
                file_name="kml_earthworks_report.html",
                mime="text/html",
                use_container_width=True,
            )

        st.divider()
        st.subheader("Analysis Parameters Used")
        params_df = pd.DataFrame(params.items(), columns=["Parameter", "Value"])
        st.dataframe(params_df, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────────────────────
# EMPTY STATE
# ──────────────────────────────────────────────────────────────────────────────
elif st.session_state.lead_submitted:
    st.info(
        "👈 **Upload a KML file or choose a sample** in the sidebar, "
        "adjust parameters, then click **Run Analysis**.",
        icon="📂",
    )

    with st.expander("How it works"):
        st.markdown(
            """
1. **Draw** one or more access lines in Google Earth (LineString).
2. **Export** as KML (File → Save Place As → .kml).
3. **Upload** here — each LineString becomes one access alignment.
4. The app **automatically**:
   - Extracts WGS84 coordinates
   - Fetches terrain elevation from Open-Meteo (free, ~30 m resolution)
   - Builds chainage with stakes every 20 m
   - Computes an optimised grade line (minimises total earthworks)
   - Calculates cut & fill cross-sections and volumes
5. **Review** interactive charts: plan view, profile, cut/fill bars, mass diagram.
6. **Download** an Excel spreadsheet or a self-contained HTML report.
            """
        )
