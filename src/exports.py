"""
exports.py
Generate downloadable outputs:
  - Excel (.xlsx) with two sheets: detailed + summary
  - HTML report (Bootstrap 5 + embedded Plotly)
"""

import io
import datetime
import pandas as pd
import plotly.io as pio


# ─── EXCEL ────────────────────────────────────────────────────────────────────

def to_excel_bytes(detail_df: pd.DataFrame, summary_df: pd.DataFrame) -> bytes:
    """
    Returns bytes of an .xlsx file with:
      Sheet 1 'Stations'  — full per-station table
      Sheet 2 'Summary'   — per-segment summary
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # ── Stations sheet ──
        station_cols = [
            "file_name", "access_id", "station_m", "stake_20m",
            "lat", "lon",
            "z_terrain_m", "z_grade_m",
            "terrain_slope_pct", "grade_slope_pct",
            "cut_height_m", "fill_height_m",
            "cut_area_m2", "fill_area_m2",
            "cut_vol_m3", "fill_vol_m3",
            "cut_vol_cum_m3", "fill_vol_cum_m3",
            "mass_balance_m3",
        ]
        cols = [c for c in station_cols if c in detail_df.columns]
        detail_df[cols].to_excel(writer, sheet_name="Stations", index=False)

        ws = writer.sheets["Stations"]
        ws.freeze_panes = "A2"
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 28)

        # ── Summary sheet ──
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        ws2 = writer.sheets["Summary"]
        ws2.freeze_panes = "A2"
        for col in ws2.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws2.column_dimensions[col[0].column_letter].width = min(max_len + 4, 28)

    buf.seek(0)
    return buf.read()


# ─── HTML REPORT ──────────────────────────────────────────────────────────────

def _kpi_card(label: str, value: str, color: str = "primary") -> str:
    return f"""
    <div class="col-md-3 col-6">
      <div class="card text-white bg-{color} shadow-sm h-100">
        <div class="card-body py-3">
          <p class="card-text small mb-1 opacity-75">{label}</p>
          <h4 class="card-title fw-bold mb-0">{value}</h4>
        </div>
      </div>
    </div>"""


def _fmt(val: float, decimals: int = 0) -> str:
    return f"{val:,.{decimals}f}"


def to_html_report(
    detail_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    kpis: dict,
    figures: dict,  # {"plan": fig, "profile_<id>": fig, ...}
    params: dict,
) -> str:
    """
    Build a self-contained HTML report with Bootstrap 5 + embedded Plotly charts.

    Args:
        detail_df:  per-station DataFrame
        summary_df: per-segment summary DataFrame
        kpis:       dict from earthworks.overall_kpis()
        figures:    dict of plotly Figure objects keyed by section name
        params:     dict of parameters used (road_width_m, max_slope_pct, etc.)
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bal_type = "Waste (surplus cut)" if kpis["net_m3"] >= 0 else "Borrow needed"
    bal_color = "success" if kpis["net_m3"] >= 0 else "danger"

    # ── KPI cards ──
    kpi_html = "".join([
        _kpi_card("Total length", f"{_fmt(kpis['total_length_m'])} m", "secondary"),
        _kpi_card("Total cut", f"{_fmt(kpis['cut_total_m3'])} m³", "danger"),
        _kpi_card("Total fill", f"{_fmt(kpis['fill_total_m3'])} m³", "primary"),
        _kpi_card(bal_type, f"{_fmt(abs(kpis['net_m3']))} m³", bal_color),
    ])

    # ── Parameters table ──
    params_rows = "".join(
        f"<tr><td>{k}</td><td class='text-end fw-semibold'>{v}</td></tr>"
        for k, v in params.items()
    )

    # ── Summary table ──
    summary_html = summary_df.to_html(
        classes="table table-hover table-sm text-end align-middle",
        index=False,
        border=0,
        float_format=lambda x: f"{x:,.0f}",
    )

    # ── Embedded Plotly charts ──
    charts_html = ""
    for section, fig in figures.items():
        chart = pio.to_html(fig, full_html=False, include_plotlyjs=False)
        charts_html += f"""
        <div class="card shadow-sm mb-4">
          <div class="card-header fw-semibold text-capitalize">{section.replace('_', ' ')}</div>
          <div class="card-body p-2">{chart}</div>
        </div>"""

    # ── Detailed table (collapsed) ──
    detail_cols = [
        "access_id", "station_m", "z_terrain_m", "z_grade_m",
        "terrain_slope_pct", "cut_height_m", "fill_height_m",
        "cut_vol_m3", "fill_vol_m3", "cut_vol_cum_m3", "fill_vol_cum_m3",
    ]
    dcols = [c for c in detail_cols if c in detail_df.columns]
    detail_html = detail_df[dcols].to_html(
        classes="table table-sm table-striped text-end align-middle",
        index=False,
        border=0,
        float_format=lambda x: f"{x:,.2f}",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KML Earthworks Report</title>
  <link rel="stylesheet"
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
  <style>
    body {{ background: #F4F6F9; font-family: 'Segoe UI', sans-serif; }}
    .hero {{ background: linear-gradient(135deg, #1A1A2E 0%, #16213E 60%, #0F3460 100%);
             color: white; padding: 2.5rem 2rem 2rem; border-radius: 0 0 1rem 1rem; }}
    .hero small {{ opacity: 0.65; }}
    .section-title {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em;
                      text-transform: uppercase; color: #6C757D; margin-bottom: 0.75rem; }}
    table {{ font-size: 0.85rem; }}
    details summary {{ cursor: pointer; font-weight: 600; padding: 0.5rem 0; }}
  </style>
</head>
<body>

<div class="hero mb-4">
  <div class="container-xl">
    <h1 class="fw-bold mb-1">KML Earthworks Report</h1>
    <small>Generated: {now}</small>
  </div>
</div>

<div class="container-xl pb-5">

  <!-- KPIs -->
  <p class="section-title">Overview</p>
  <div class="row g-3 mb-4">{kpi_html}</div>

  <!-- Parameters -->
  <div class="card shadow-sm mb-4">
    <div class="card-header fw-semibold">Analysis Parameters</div>
    <div class="card-body p-0">
      <table class="table table-sm mb-0">
        <tbody>{params_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Summary -->
  <div class="card shadow-sm mb-4">
    <div class="card-header fw-semibold">Segment Summary</div>
    <div class="card-body p-0 table-responsive">
      {summary_html}
    </div>
  </div>

  <!-- Charts -->
  <p class="section-title">Charts</p>
  {charts_html}

  <!-- Detailed table -->
  <div class="card shadow-sm mb-4">
    <div class="card-header">
      <details>
        <summary>Detailed Station Table ({len(detail_df):,} rows)</summary>
        <div class="table-responsive mt-3">{detail_html}</div>
      </details>
    </div>
  </div>

  <footer class="text-center text-muted small mt-4 pb-3">
    Generated by <strong>kml-earthworks</strong> &mdash; early-stage estimation tool.
    Validate against approved survey surfaces before use in final design.
  </footer>

</div>
</body>
</html>"""
