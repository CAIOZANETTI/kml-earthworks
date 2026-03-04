# KML Earthworks ⛏️

**Turn a Google Earth sketch into cut/fill volumes in seconds.**

Draw access roads in Google Earth → export KML → upload here → get terrain profiles, earthworks quantities and mass balance — no GIS software, no manual spreadsheets.

🔗 **[Try the live app →](https://kml-earthworks.streamlit.app)**

---

## What it does

Early-stage access roads and temporary haul roads are often sketched quickly in Google Earth. Turning those alignments into earthworks estimates usually means manual coordinate extraction, external elevation queries, and repetitive spreadsheet work.

This app automates the entire pipeline:

| Step | What happens |
|------|-------------|
| **Upload** | One or more `.kml` files (multiple LineStrings supported) |
| **Parse** | Extracts WGS84 coordinates from each alignment |
| **Station** | Builds chainage with stakes every 20 m |
| **Elevation** | Queries terrain elevation for every point via public API |
| **Grade** | Fits a constrained grade line respecting your max slope |
| **Volumes** | Computes cut/fill areas and volumes (prismatoid method) |
| **Mass balance** | Calculates borrow, waste, and net balance per segment |
| **Visualize** | Interactive plan, profile, cut/fill bars, mass diagram, 3D view |
| **Export** | Download detailed CSV or segment summary CSV |

---

## Tech stack

| Layer | Tool |
|-------|------|
| UI & deployment | [Streamlit](https://streamlit.io) |
| Charts | [Plotly](https://plotly.com/python/) |
| Data processing | [pandas](https://pandas.pydata.org) + [NumPy](https://numpy.org) |
| Elevation data | [Open-Elevation API](https://open-elevation.com) (free, no key needed) |
| KML parsing | Python `xml.etree.ElementTree` (stdlib, no GDAL required) |
| Exports | [openpyxl](https://openpyxl.readthedocs.io) / CSV |
| Lead capture | [gspread](https://gspread.readthedocs.io) + Google Sheets (optional) |

Zero desktop GIS dependencies. Runs entirely in the browser via Streamlit Cloud.

---

## How it was built

This project was built iteratively with **[Claude](https://claude.ai)** (Anthropic) as the primary development assistant — from architecture decisions to module implementation and UI layout.

The development flow:
1. Prototyped the core math in a Jupyter notebook (`acesso_provisorio.ipynb`)
2. Migrated to a proper `src/` package structure with Claude
3. Wired up the Streamlit UI, charts and export logic
4. Deployed to Streamlit Cloud

The entire codebase — KML parser, stationing, elevation enrichment, grade computation, earthworks volumes, Plotly figures — was written and refined through conversation-driven development with an AI assistant.

---

## Project structure

```
kml-earthworks/
├── app/
│   └── streamlit_app.py      # Streamlit UI
├── src/
│   ├── io_kml.py             # KML parsing, LineString extraction
│   ├── stationing.py         # chainage + 20 m stakes
│   ├── elevation.py          # elevation API enrichment
│   ├── grade.py              # constrained grade line
│   ├── earthworks.py         # cut/fill areas, volumes, mass balance
│   ├── plots.py              # Plotly figures
│   ├── exports.py            # CSV/Excel export helpers
│   └── leads.py              # optional Google Sheets lead capture
├── data/                     # sample KML files
├── requirements.txt
└── README.md
```

---

## Run locally

```bash
git clone https://github.com/CAIOZANETTI/kml-earthworks
cd kml-earthworks
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

---

## Accuracy & disclaimer

Designed for **early-stage estimation and fast iteration** — not for final design quantities.
Validate against approved survey surfaces / DTM before using in procurement or construction.

---

## Author

Built by **Caio Zanetti** — mining & earthworks engineer turned builder.
Questions or feedback? Open an issue or reach out on [LinkedIn](https://linkedin.com/in/caiozanetti).
