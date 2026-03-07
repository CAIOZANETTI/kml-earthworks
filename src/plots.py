"""
plots.py
All Plotly figures for the kml-earthworks app.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Optional

_COLORS = px.colors.qualitative.Bold
_CUT_COLOR = "#E05252"
_FILL_COLOR = "#4A90D9"
_TERRAIN_COLOR = "#8B6914"
_GRADE_COLOR = "#1A1A2E"
_MASS_COLOR = "#7B2D8B"
_ZERO_COLOR = "#AAAAAA"


def _access_color(access_id: str, all_ids: list) -> str:
    idx = all_ids.index(access_id) if access_id in all_ids else 0
    return _COLORS[idx % len(_COLORS)]


# ─── 1. PLAN VIEW MAP ─────────────────────────────────────────────────────────

def fig_plan_view(df: pd.DataFrame) -> go.Figure:
    """Scatter mapbox with all alignments in distinct colors."""
    access_ids = df["access_id"].unique().tolist()
    fig = go.Figure()

    for acc in access_ids:
        sub = df[df["access_id"] == acc]
        color = _access_color(acc, access_ids)
        fig.add_trace(
            go.Scattermapbox(
                lat=sub["lat"],
                lon=sub["lon"],
                mode="lines+markers",
                name=acc,
                line=dict(width=3, color=color),
                marker=dict(size=4, color=color),
                customdata=np.stack(
                    [
                        sub["station_m"],
                        sub["z_terrain_m"],
                        sub.get("z_grade_m", sub["z_terrain_m"]),
                        sub.get("cut_height_m", np.zeros(len(sub))),
                        sub.get("fill_height_m", np.zeros(len(sub))),
                    ],
                    axis=-1,
                ),
                hovertemplate=(
                    "<b>%{customdata[0]:.0f} m</b><br>"
                    "Terrain: %{customdata[1]:.1f} m<br>"
                    "Grade: %{customdata[2]:.1f} m<br>"
                    "Cut: %{customdata[3]:.2f} m  Fill: %{customdata[4]:.2f} m<br>"
                    "Lat: %{lat:.6f}  Lon: %{lon:.6f}<extra>%{fullData.name}</extra>"
                ),
            )
        )

    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=13,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=480,
        legend=dict(
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#CCCCCC",
            borderwidth=1,
        ),
    )
    return fig


# ─── 2. TERRAIN vs GRADE PROFILE ──────────────────────────────────────────────

def fig_profile(df: pd.DataFrame, access_id: Optional[str] = None) -> go.Figure:
    """Terrain vs grade line profile with cut/fill shading."""
    sub = df[df["access_id"] == access_id] if access_id else df

    x = sub["station_m"].to_numpy()
    terrain = sub["z_terrain_m"].to_numpy()
    grade = sub["z_grade_m"].to_numpy()
    fill_mask = grade > terrain
    cut_mask = terrain > grade

    fill_bottom = np.where(fill_mask, terrain, np.nan)
    fill_top = np.where(fill_mask, grade, np.nan)
    cut_bottom = np.where(cut_mask, grade, np.nan)
    cut_top = np.where(cut_mask, terrain, np.nan)

    fig = go.Figure()

    # Shading: fill area (grade > terrain), shown only where mask is true
    fig.add_trace(
        go.Scatter(
            x=x,
            y=fill_bottom,
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=fill_top,
            fill="tonexty",
            fillcolor="rgba(74,144,217,0.25)",
            line=dict(width=0),
            name="Fill zone",
            hoverinfo="skip",
        )
    )

    # Shading: cut area (terrain > grade), shown only where mask is true
    fig.add_trace(
        go.Scatter(
            x=x,
            y=cut_bottom,
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=cut_top,
            fill="tonexty",
            fillcolor="rgba(224,82,82,0.25)",
            line=dict(width=0),
            name="Cut zone",
            hoverinfo="skip",
        )
    )

    # Terrain line
    fig.add_trace(
        go.Scatter(
            x=sub["station_m"],
            y=sub["z_terrain_m"],
            name="Terrain",
            line=dict(color=_TERRAIN_COLOR, width=2, dash="dot"),
            hovertemplate="Station %{x:.0f} m<br>Terrain: %{y:.2f} m<extra></extra>",
        )
    )

    # Grade line
    fig.add_trace(
        go.Scatter(
            x=sub["station_m"],
            y=sub["z_grade_m"],
            name="Grade line",
            line=dict(color=_GRADE_COLOR, width=3),
            hovertemplate="Station %{x:.0f} m<br>Grade: %{y:.2f} m<br>Slope: %{customdata:.1f}%<extra></extra>",
            customdata=sub.get("grade_slope_pct", sub["slope_pct"]),
        )
    )

    # Stake ticks every 20 m
    stakes = sub[sub["stake_20m"] == True]
    fig.add_trace(
        go.Scatter(
            x=stakes["station_m"],
            y=stakes["z_terrain_m"],
            mode="markers",
            name="Stakes (20 m)",
            marker=dict(symbol="line-ns", size=8, color="#555555", line=dict(width=1)),
            hoverinfo="skip",
        )
    )

    fig.update_layout(
        xaxis_title="Chainage (m)",
        yaxis_title="Elevation (m)",
        height=400,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


# ─── 3. CUT / FILL BARS ───────────────────────────────────────────────────────

def fig_cut_fill_bars(df: pd.DataFrame, access_id: Optional[str] = None) -> go.Figure:
    """Bar chart of incremental cut and fill per station."""
    sub = df[df["access_id"] == access_id] if access_id else df

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=sub["station_m"],
            y=sub["cut_height_m"],
            name="Cut height (m)",
            marker_color=_CUT_COLOR,
            hovertemplate="Station %{x:.0f} m<br>Cut: %{y:.2f} m<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=sub["station_m"],
            y=-sub["fill_height_m"],
            name="Fill height (m)",
            marker_color=_FILL_COLOR,
            hovertemplate="Station %{x:.0f} m<br>Fill: %{y:.2f} m<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="relative",
        xaxis_title="Chainage (m)",
        yaxis_title="Height (m)  ▲ Cut  ▼ Fill",
        height=360,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


# ─── 4. MASS DIAGRAM ──────────────────────────────────────────────────────────

def fig_mass_diagram(
    df: pd.DataFrame,
    shrink_swell: float = 1.125,
    access_id: Optional[str] = None,
) -> go.Figure:
    """
    Cumulative cut/fill + net balance (mass haul diagram).
    Uses an equivalent-cut curve (cut * shrink_swell) so balance is visually consistent.
    """
    sub = df[df["access_id"] == access_id].copy() if access_id else df.copy()

    if sub.empty:
        return go.Figure()

    if access_id is None and sub["access_id"].nunique() > 1:
        # For "All alignments", aggregate incremental volumes by chainage.
        # This avoids non-monotonic traces when different alignments restart at 0 m.
        sub = (
            sub.groupby("station_m", as_index=False)[["cut_vol_m3", "fill_vol_m3"]]
            .sum()
            .sort_values("station_m")
        )
        sub["cut_vol_cum_m3"] = sub["cut_vol_m3"].cumsum()
        sub["fill_vol_cum_m3"] = sub["fill_vol_m3"].cumsum()
    else:
        sub = sub.sort_values("station_m").copy()

    sub["cut_equiv_cum_m3"] = sub["cut_vol_cum_m3"] * shrink_swell
    sub["mass_balance_m3"] = sub["cut_equiv_cum_m3"] - sub["fill_vol_cum_m3"]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=sub["station_m"],
            y=sub["cut_equiv_cum_m3"],
            name=f"Equivalent Cut (m³) × {shrink_swell:.3f}",
            line=dict(color=_CUT_COLOR, width=2),
            fill="tozeroy",
            fillcolor="rgba(224,82,82,0.12)",
            hovertemplate="Station %{x:.0f} m<br>Equivalent cut: %{y:,.0f} m³<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=sub["station_m"],
            y=sub["fill_vol_cum_m3"],
            name="Cumulative Fill (m³)",
            line=dict(color=_FILL_COLOR, width=2),
            fill="tozeroy",
            fillcolor="rgba(74,144,217,0.12)",
            hovertemplate="Station %{x:.0f} m<br>Cumulative fill: %{y:,.0f} m³<extra></extra>",
        )
    )
    if abs(shrink_swell - 1.0) > 1e-6:
        fig.add_trace(
            go.Scatter(
                x=sub["station_m"],
                y=sub["cut_vol_cum_m3"],
                name="Cut in-situ (m³)",
                line=dict(color=_CUT_COLOR, width=1.5, dash="dot"),
                opacity=0.7,
                hovertemplate="Station %{x:.0f} m<br>In-situ cut: %{y:,.0f} m³<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=sub["station_m"],
            y=sub["mass_balance_m3"],
            name="Mass Balance (m³)",
            line=dict(color=_MASS_COLOR, width=2, dash="dash"),
            hovertemplate="Station %{x:.0f} m<br>Balance: %{y:,.0f} m³<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color=_ZERO_COLOR, annotation_text="Balance zero")

    end_x = float(sub["station_m"].iloc[-1])
    end_bal = float(sub["mass_balance_m3"].iloc[-1])
    if end_bal > 0:
        end_txt = f"Final balance: +{end_bal:,.0f} m³ (waste)"
        end_color = _CUT_COLOR
    elif end_bal < 0:
        end_txt = f"Final balance: {end_bal:,.0f} m³ (borrow)"
        end_color = _FILL_COLOR
    else:
        end_txt = "Final balance: 0 m³"
        end_color = _ZERO_COLOR
    fig.add_annotation(
        x=end_x,
        y=end_bal,
        text=end_txt,
        showarrow=True,
        arrowhead=2,
        ax=-120,
        ay=-25,
        font=dict(color=end_color, size=11),
        bgcolor="rgba(255,255,255,0.85)",
    )

    fig.update_layout(
        xaxis_title="Chainage (m)",
        yaxis_title="Volume (m³)",
        height=360,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    return fig


# ─── 5. CROSS-SECTION ─────────────────────────────────────────────────────────

def fig_cross_section(df: pd.DataFrame, station_m: float, access_id: Optional[str] = None) -> go.Figure:
    """
    Engineering cross-section at the given chainage.
    Shows natural ground line, road platform, cut zone (red) or fill zone (blue),
    slope ratios and key dimensions.
    """
    sub = df[df["access_id"] == access_id] if access_id else df
    if sub.empty:
        return go.Figure()

    # Guard: columns added in grade.py may be absent in cached results
    missing = [c for c in ("road_width_m", "cut_slope_hv", "fill_slope_hv") if c not in sub.columns]
    if missing:
        fig = go.Figure()
        fig.add_annotation(
            text="Re-run the analysis to generate cross-sections.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="#555"),
        )
        fig.update_layout(height=300, template="plotly_white")
        return fig

    # Closest station (idxmin returns the index label, not position)
    closest_idx = (sub["station_m"] - station_m).abs().idxmin()
    row = sub.loc[closest_idx]
    # Ensure scalar (guard against duplicate index labels)
    if not isinstance(row, pd.Series) or row.ndim != 1:
        row = sub.loc[closest_idx].iloc[0] if hasattr(sub.loc[closest_idx], "iloc") else row

    h_cut   = float(row["cut_height_m"])
    h_fill  = float(row["fill_height_m"])
    road_w  = float(row["road_width_m"])
    cut_hv  = float(row["cut_slope_hv"])
    fill_hv = float(row["fill_slope_hv"])
    sta     = float(row["station_m"])

    fig = go.Figure()

    if h_cut > 0.01:
        # ── CUT SECTION ──
        cut_half = road_w / 2 + cut_hv * h_cut   # horizontal reach of slope
        margin   = max(cut_half * 0.35, 1.5)
        x_max    = cut_half + margin

        # Natural ground (y = 0 reference)
        fig.add_trace(go.Scatter(
            x=[-x_max, x_max], y=[0, 0],
            mode="lines", name="Natural ground",
            line=dict(color=_TERRAIN_COLOR, width=2.5, dash="dot"),
        ))

        # Cut polygon: slope lines + subgrade
        cut_xs = [-cut_half, -road_w / 2, road_w / 2, cut_half, cut_half, -cut_half]
        cut_ys = [0,         -h_cut,       -h_cut,      0,        0,        0       ]
        fig.add_trace(go.Scatter(
            x=cut_xs, y=cut_ys,
            fill="toself",
            fillcolor="rgba(224,82,82,0.20)",
            line=dict(color=_CUT_COLOR, width=1.5),
            name=f"Cut zone  Hc = {h_cut:.2f} m",
        ))

        # Road platform (subgrade)
        fig.add_trace(go.Scatter(
            x=[-road_w / 2, road_w / 2], y=[-h_cut, -h_cut],
            mode="lines", name=f"Subgrade  W = {road_w:.1f} m",
            line=dict(color=_GRADE_COLOR, width=4),
        ))

        # Dimension annotations
        fig.add_annotation(x=0, y=-h_cut / 2, text=f"Hc = {h_cut:.2f} m",
                           showarrow=False, font=dict(color=_CUT_COLOR, size=12),
                           xref="x", yref="y")
        fig.add_annotation(x=-cut_half / 2, y=-h_cut * 0.15,
                           text=f"1 : {cut_hv:.2f}",
                           showarrow=False, font=dict(color=_CUT_COLOR, size=11),
                           xref="x", yref="y")
        fig.add_annotation(x=cut_half / 2, y=-h_cut * 0.15,
                           text=f"1 : {cut_hv:.2f}",
                           showarrow=False, font=dict(color=_CUT_COLOR, size=11),
                           xref="x", yref="y")
        y_range = [-h_cut * 1.4, h_cut * 0.6]

    elif h_fill > 0.01:
        # ── FILL SECTION ──
        fill_half = road_w / 2 + fill_hv * h_fill
        margin    = max(fill_half * 0.35, 1.5)
        x_max     = fill_half + margin

        # Natural ground
        fig.add_trace(go.Scatter(
            x=[-x_max, x_max], y=[0, 0],
            mode="lines", name="Natural ground",
            line=dict(color=_TERRAIN_COLOR, width=2.5, dash="dot"),
        ))

        # Fill polygon
        fill_xs = [-fill_half, -road_w / 2, road_w / 2, fill_half, fill_half, -fill_half]
        fill_ys = [0,           h_fill,      h_fill,      0,         0,         0        ]
        fig.add_trace(go.Scatter(
            x=fill_xs, y=fill_ys,
            fill="toself",
            fillcolor="rgba(74,144,217,0.20)",
            line=dict(color=_FILL_COLOR, width=1.5),
            name=f"Fill zone  Hf = {h_fill:.2f} m",
        ))

        # Road platform
        fig.add_trace(go.Scatter(
            x=[-road_w / 2, road_w / 2], y=[h_fill, h_fill],
            mode="lines", name=f"Subgrade  W = {road_w:.1f} m",
            line=dict(color=_GRADE_COLOR, width=4),
        ))

        # Dimension annotations
        fig.add_annotation(x=0, y=h_fill / 2, text=f"Hf = {h_fill:.2f} m",
                           showarrow=False, font=dict(color=_FILL_COLOR, size=12),
                           xref="x", yref="y")
        fig.add_annotation(x=-fill_half / 2, y=h_fill * 0.15,
                           text=f"1 : {fill_hv:.2f}",
                           showarrow=False, font=dict(color=_FILL_COLOR, size=11),
                           xref="x", yref="y")
        fig.add_annotation(x=fill_half / 2, y=h_fill * 0.15,
                           text=f"1 : {fill_hv:.2f}",
                           showarrow=False, font=dict(color=_FILL_COLOR, size=11),
                           xref="x", yref="y")
        y_range = [-h_fill * 0.5, h_fill * 1.5]

    else:
        # ── ZERO HEIGHT ── (flat / on grade)
        x_max = road_w / 2 + 3.0
        fig.add_trace(go.Scatter(
            x=[-x_max, x_max], y=[0, 0],
            mode="lines", name="Natural ground / Subgrade",
            line=dict(color=_TERRAIN_COLOR, width=2.5),
        ))
        fig.add_trace(go.Scatter(
            x=[-road_w / 2, road_w / 2], y=[0, 0],
            mode="lines", name=f"Road platform  W = {road_w:.1f} m",
            line=dict(color=_GRADE_COLOR, width=5),
        ))
        y_range = [-2, 2]

    # Centreline marker
    fig.add_vline(x=0, line_dash="dash", line_color="#AAAAAA", line_width=1,
                  annotation_text="CL", annotation_position="top")

    fig.update_layout(
        title=dict(text=f"Cross-section  —  Station {sta:.0f} m", font=dict(size=14)),
        xaxis_title="Offset from centreline (m)",
        yaxis_title="Elevation relative to natural ground (m)",
        yaxis=dict(range=y_range, scaleanchor="x", scaleratio=1),
        height=380,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


# ─── 6. 3D VIEW ───────────────────────────────────────────────────────────────


def _perp_offset_deg(
    lon_arr: np.ndarray, lat_arr: np.ndarray, half_w_m_arr: np.ndarray
) -> tuple:
    """
    Return (d_lon, d_lat) arrays representing a perpendicular offset
    of half_w_m_arr metres to the right of the road direction.
    Fully vectorised with NumPy central-differences.
    """
    cos_lat = np.cos(np.radians(lat_arr))

    # Central-difference direction vectors in metres
    lat_next = np.roll(lat_arr, -1); lat_next[-1] = lat_arr[-1]
    lat_prev = np.roll(lat_arr,  1); lat_prev[ 0] = lat_arr[ 0]
    lon_next = np.roll(lon_arr, -1); lon_next[-1] = lon_arr[-1]
    lon_prev = np.roll(lon_arr,  1); lon_prev[ 0] = lon_arr[ 0]

    d_lat_m = (lat_next - lat_prev) * 111_000
    d_lon_m = (lon_next - lon_prev) * 111_000 * cos_lat

    mag = np.hypot(d_lat_m, d_lon_m)
    mag = np.where(mag < 1e-9, 1.0, mag)   # avoid division by zero

    # Rotate +90° → right-side perpendicular: (dy, -dx) / mag
    perp_lat_m =  d_lon_m / mag
    perp_lon_m = -d_lat_m / mag

    d_lat = perp_lat_m * half_w_m_arr / 111_000
    d_lon = perp_lon_m * half_w_m_arr / (111_000 * cos_lat)

    return d_lon, d_lat

def fig_3d(df: pd.DataFrame, access_id: Optional[str] = None) -> go.Figure:
    """
    3D view of terrain, grade line and earthworks footprint.
    Shows fill embankment toe and cut crest as ribbons offset
    perpendicularly from the centreline.
    """
    sub = df[df["access_id"] == access_id] if access_id else df
    access_ids = df["access_id"].unique().tolist()

    fig = go.Figure()

    for acc in (sub["access_id"].unique() if access_id is None else [access_id]):
        grp = sub[sub["access_id"] == acc].reset_index(drop=True)
        color = _access_color(acc, access_ids)

        lon_a = grp["lon"].values
        lat_a = grp["lat"].values
        z_ter = grp["z_terrain_m"].values
        z_grd = grp["z_grade_m"].values if "z_grade_m" in grp.columns else z_ter

        # Terrain centreline
        fig.add_trace(go.Scatter3d(
            x=lon_a, y=lat_a, z=z_ter,
            mode="lines", name=f"{acc} — Terrain",
            line=dict(color=_TERRAIN_COLOR, width=3),
        ))

        # Grade centreline
        fig.add_trace(go.Scatter3d(
            x=lon_a, y=lat_a, z=z_grd,
            mode="lines", name=f"{acc} — Grade",
            line=dict(color=color, width=5),
        ))

        if "road_width_m" in grp.columns:
            road_w  = grp["road_width_m"].values
            h_fill  = grp["fill_height_m"].values
            h_cut   = grp["cut_height_m"].values
            fill_hv = grp["fill_slope_hv"].values
            cut_hv  = grp["cut_slope_hv"].values

            # Half-widths of fill toe and cut crest
            fill_hw = road_w / 2 + fill_hv * h_fill
            cut_hw  = road_w / 2 + cut_hv  * h_cut

            # Perpendicular offsets (right and left)
            d_lon_f, d_lat_f = _perp_offset_deg(lon_a, lat_a, fill_hw)
            d_lon_c, d_lat_c = _perp_offset_deg(lon_a, lat_a, cut_hw)

            # Fill toe edges (at terrain z — base of embankment)
            for sign, side in [(1, "R"), (-1, "L")]:
                fig.add_trace(go.Scatter3d(
                    x=lon_a + sign * d_lon_f,
                    y=lat_a + sign * d_lat_f,
                    z=z_ter,
                    mode="lines",
                    name=f"{acc} — Fill toe ({side})",
                    line=dict(color=_FILL_COLOR, width=2),
                    opacity=0.7,
                ))

            # Cut crest edges (at terrain z — top of cut)
            for sign, side in [(1, "R"), (-1, "L")]:
                fig.add_trace(go.Scatter3d(
                    x=lon_a + sign * d_lon_c,
                    y=lat_a + sign * d_lat_c,
                    z=z_ter,
                    mode="lines",
                    name=f"{acc} — Cut crest ({side})",
                    line=dict(color=_CUT_COLOR, width=2),
                    opacity=0.7,
                ))

    fig.update_layout(
        scene=dict(
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            zaxis_title="Elevation (m)",
            aspectmode="auto",
        ),
        height=520,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig
