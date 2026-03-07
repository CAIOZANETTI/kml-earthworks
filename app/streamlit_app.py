"""
streamlit_app.py
kml-earthworks — KML → Terrain Profiles → Cut/Fill Volumes
"""

import sys
import os
import uuid

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
from src import plots, exports, leads, db

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
for key in ("results_df", "summary_df", "kpis", "figures", "params_used"):
    if key not in st.session_state:
        st.session_state[key] = None

if "lead_submitted" not in st.session_state:
    st.session_state.lead_submitted = True

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    row_id = db.log_access(st.session_state.session_id)
    if row_id:
        st.session_state.access_log_id = row_id

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
# SIDEBAR — UPLOAD + PARAMETERS
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Upload")
    uploaded_files = st.file_uploader(
        "KML files",
        type=["kml"],
        accept_multiple_files=True,
        help="Draw LineStrings in Google Earth, export as KML, upload here.",
        disabled=not st.session_state.lead_submitted,
    )

    st.markdown('<p class="sidebar-title">Road Parameters</p>', unsafe_allow_html=True)
    road_width   = st.slider("Road width (m)",        3.0, 12.0, 6.0, 0.5)
    max_slope    = st.slider("Max slope (%)",          2.0, 20.0, 16.0, 0.5)
    cut_slope    = st.slider("Cut side slope (H:V)",  1.0,  3.0,  1.0, 0.25)
    fill_slope   = st.slider("Fill side slope (H:V)", 1.0,  3.0,  1.5, 0.25)
    shrink_swell = st.slider("Shrink/Swell factor",  0.90, 1.30, 1.125, 0.005, format="%.3f")
    max_height   = st.slider("Max cut/fill height (m)", 2.0, 20.0, 10.0, 0.5)

    run = st.button(
        "⚡ Run Analysis",
        type="primary",
        use_container_width=True,
        disabled=(not uploaded_files or not st.session_state.lead_submitted),
    )


# ──────────────────────────────────────────────────────────────────────────────
# RUN PIPELINE
# ──────────────────────────────────────────────────────────────────────────────
if run and uploaded_files:
    files_data = [
        {"name": f.name, "content": f.read()} for f in uploaded_files
    ]

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

        # 3. Stationing + grade per alignment
        st.write("📐 Computing grade lines and volumes…")
        alignments_data = []
        for a in alignments:
            stations = build_stationing(a["points"])
            stations = compute_grade(
                stations,
                road_width_m=road_width,
                max_slope_pct=max_slope,
                max_height_m=max_height,
                cut_slope_hv=cut_slope,
                fill_slope_hv=fill_slope,
                shrink_swell=shrink_swell,
            )
            alignments_data.append(
                {
                    "file_name": a["file_name"],
                    "access_id": a["access_id"],
                    "stations": stations,
                }
            )

        # 4. Aggregate
        results_df = build_dataframe(alignments_data, shrink_swell=shrink_swell)
        summary_df = build_segment_summary(results_df, shrink_swell=shrink_swell)
        kpis = overall_kpis(summary_df)

        # 5. Build all figures
        st.write("📊 Building charts…")
        figs = {
            "Plan View": plots.fig_plan_view(results_df),
            "Profile": plots.fig_profile(results_df),
            "Cut / Fill Heights": plots.fig_cut_fill_bars(results_df),
            "Mass Diagram": plots.fig_mass_diagram(results_df, shrink_swell),
            "3D View": plots.fig_3d(results_df),
        }

        params_used = {
            "Road width": f"{road_width} m",
            "Max slope": f"{max_slope} %",
            "Cut side slope": f"{cut_slope} H:V",
            "Fill side slope": f"{fill_slope} H:V",
            "Shrink/Swell factor": f"{shrink_swell:.3f}",
            "Max cut/fill height": f"{max_height} m",
            "Stake interval": "20 m",
            "Elevation source": "Open-Meteo (free, ~30 m resolution)",
        }

        st.session_state.results_df  = results_df
        st.session_state.summary_df  = summary_df
        st.session_state.kpis        = kpis
        st.session_state.figures     = figs
        st.session_state.params_used = params_used

        status.update(label="✅ Analysis complete!", state="complete")

# ──────────────────────────────────────────────────────────────────────────────
# RESULTS
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.results_df is not None:
    df        = st.session_state.results_df
    summary   = st.session_state.summary_df
    kpis      = st.session_state.kpis
    figs      = st.session_state.figures
    params    = st.session_state.params_used

    # ── KPI strip ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total length",  f"{kpis['total_length_m']:,.0f} m")
    c2.metric("Total cut",     f"{kpis['cut_total_m3']:,.0f} m³")
    c3.metric("Total fill",    f"{kpis['fill_total_m3']:,.0f} m³")
    waste  = kpis["waste_m3"]
    borrow = kpis["borrow_m3"]
    c4.metric("Waste",         f"{waste:,.0f} m³",  delta=None)
    c5.metric("Borrow",        f"{borrow:,.0f} m³", delta=None)

    st.divider()

    # ── Tabs ──
    tab_map, tab_profile, tab_xsec, tab_vol, tab_3d, tab_tables, tab_export = st.tabs(
        ["🗺 Plan View", "📈 Profile", "✂ Cross Section", "📊 Volumes", "🧊 3D", "📋 Tables", "⬇ Export"]
    )

    # ── Filter helpers ──
    access_ids = df["access_id"].unique().tolist()

    with tab_map:
        st.plotly_chart(figs["Plan View"], use_container_width=True)

    with tab_profile:
        sel_acc = st.selectbox("Access alignment", ["All"] + access_ids, key="prof_sel")
        acc_filter = None if sel_acc == "All" else sel_acc
        st.plotly_chart(
            plots.fig_profile(df, acc_filter),
            use_container_width=True,
        )

    with tab_xsec:
        sel_acc_x = st.selectbox("Access alignment", ["All"] + access_ids, key="xsec_sel")
        acc_filter_x = None if sel_acc_x == "All" else sel_acc_x
        sub_x = df[df["access_id"] == acc_filter_x] if acc_filter_x else df
        sta_min = float(sub_x["station_m"].min())
        sta_max = float(sub_x["station_m"].max())
        sta_sel = st.slider(
            "Station (m)", min_value=sta_min, max_value=sta_max,
            value=(sta_min + sta_max) / 2, step=5.0, key="xsec_sta",
        )
        col_xA, col_xB = st.columns([3, 1])
        with col_xA:
            st.plotly_chart(
                plots.fig_cross_section(df, sta_sel, acc_filter_x),
                use_container_width=True,
            )
        with col_xB:
            row_x = sub_x.iloc[(sub_x["station_m"] - sta_sel).abs().argsort()[:1]]
            if not row_x.empty:
                r = row_x.iloc[0]
                st.metric("Terrain elev.", f"{r['z_terrain_m']:.2f} m")
                st.metric("Grade elev.",   f"{r['z_grade_m']:.2f} m")
                st.metric("Cut height",    f"{r['cut_height_m']:.2f} m")
                st.metric("Fill height",   f"{r['fill_height_m']:.2f} m")
                st.metric("Cut area",      f"{r['cut_area_m2']:.1f} m²")
                st.metric("Fill area",     f"{r['fill_area_m2']:.1f} m²")

    with tab_vol:
        sel_acc2 = st.selectbox("Access alignment", ["All"] + access_ids, key="vol_sel")
        acc_filter2 = None if sel_acc2 == "All" else sel_acc2
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(
                plots.fig_cut_fill_bars(df, acc_filter2),
                use_container_width=True,
            )
        with col_b:
            st.plotly_chart(
                plots.fig_mass_diagram(df, shrink_swell, acc_filter2),
                use_container_width=True,
            )

    with tab_3d:
        sel_acc3 = st.selectbox("Access alignment", ["All"] + access_ids, key="3d_sel")
        acc_filter3 = None if sel_acc3 == "All" else sel_acc3
        st.plotly_chart(
            plots.fig_3d(df, acc_filter3),
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

    # ── Survey ──
    st.divider()
    st.markdown("### 📝 O que achou do sistema?")
    st.caption("Deixe sua opinião e nos ajude a melhorar.")
    
    with st.form("feedback_form", clear_on_submit=True):
        f_nome = st.text_input("Seu nome:")
        f_email = st.text_input("Seu e-mail:")
        f_feedback = st.text_area("O que você gostou e o que não gostou?")
        f_submit = st.form_submit_button("Enviar avaliação", type="primary")
        
        if f_submit:
            if f_nome and f_email and f_feedback:
                if db.log_feedback(f_nome, f_email, f_feedback):
                    st.success("Obrigado pelo seu feedback!")
                else:
                    st.error("Erro ao salvar feedback. Tente novamente mais tarde.")
            else:
                st.warning("Por favor, preencha todos os campos para enviar.")

# ──────────────────────────────────────────────────────────────────────────────
# EMPTY STATE
# ──────────────────────────────────────────────────────────────────────────────
elif st.session_state.lead_submitted:
    st.info(
        "👈 **Upload one or more KML files** in the sidebar, "
        "adjust parameters, then click **Run Analysis**.",
        icon="📂",
    )
    
    # ── KML Samples ──
    st.markdown("#### Exemplos de KML")
    st.caption("Faça o download dos arquivos abaixo na pasta de exemplos e envie pelo menu lateral para testar a ferramenta.")
    sample_col1, sample_col2, sample_col3 = st.columns(3)
    
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", "sample", "AC-2.kml"), "r") as f:
            ac2_data = f.read()
            sample_col1.download_button("⬇ Baixar AC-2.kml", data=ac2_data, file_name="AC-2.kml", use_container_width=True)
            
        with open(os.path.join(os.path.dirname(__file__), "..", "sample", "AC-3.kml"), "r") as f:
            ac3_data = f.read()
            sample_col2.download_button("⬇ Baixar AC-3.kml", data=ac3_data, file_name="AC-3.kml", use_container_width=True)
            
        with open(os.path.join(os.path.dirname(__file__), "..", "sample", "AC-4.kml"), "r") as f:
            ac4_data = f.read()
            sample_col3.download_button("⬇ Baixar AC-4.kml", data=ac4_data, file_name="AC-4.kml", use_container_width=True)
    except Exception as e:
        st.warning(f"Exemplos não encontrados: {e}")

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
5. **Review** interactive charts: plan view, profile, cut/fill bars, mass diagram, 3D.
6. **Download** an Excel spreadsheet or a self-contained HTML report.
            """
        )
