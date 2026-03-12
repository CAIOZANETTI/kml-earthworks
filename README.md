# KML Earthworks ⛏️

[![Tests](https://img.shields.io/badge/tests-58%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![Type Safety](https://img.shields.io/badge/types-TypedDict-blue)](src/types.py)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

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
| **Station** | Builds chainage with stakes every 20 m using Haversine distance |
| **Elevation** | Queries terrain elevation via Open-Meteo API with OpenTopoData fallback |
| **Validate** | Fail-fast if >10% elevation data missing (prevents bad calculations) |
| **Grade** | Fits constrained grade line respecting max slope & max height |
| **Volumes** | Computes cut/fill using **prismatoid formula** (5-15% more accurate) |
| **Mass balance** | Applies shrink/swell factor, calculates borrow/waste per segment |
| **Visualize** | Interactive plan, profile, cut/fill bars, mass diagram, 3D view |
| **Export** | Download detailed Excel report or segment summary CSV |

---

## Tech stack

| Layer | Tool |
|-------|------|
| UI & deployment | [Streamlit](https://streamlit.io) |
| Charts | [Plotly](https://plotly.com/python/) |
| Data processing | [pandas](https://pandas.pydata.org) + [NumPy](https://numpy.org) + [SciPy](https://scipy.org) |
| Elevation data | [Open-Meteo Elevation API](https://open-meteo.com) (primary) + [OpenTopoData](https://opentopodata.org) (fallback) |
| KML parsing | Python `xml.etree.ElementTree` (stdlib, no GDAL required) |
| Optimization | SciPy `minimize_scalar` for grade line optimization |
| Exports | [openpyxl](https://openpyxl.readthedocs.io) for Excel / CSV |
| Type safety | TypedDict for structured data validation |
| Testing | [pytest](https://pytest.org) with 58 tests covering all core modules |
| Logging | Structured logging with Python `logging` module |

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

## Code Quality & Testing

**Comprehensive test coverage across all critical modules:**

```bash
# Run all tests
pytest tests/ -v

# Test results
✅ 58/58 tests passing (100%)
  - test_earthworks.py    (10 tests) - Data aggregation, mass balance
  - test_elevation.py     (15 tests) - API calls (mocked), error handling
  - test_grade.py         (9 tests)  - Grade constraints, prismatoid formula
  - test_io_kml.py        (15 tests) - KML parsing, coordinate extraction
  - test_stationing.py    (9 tests)  - Haversine distance, interpolation
```

**Engineering accuracy:**
- ✅ **Prismatoid volume formula** - More accurate than average-end-area for irregular terrain
- ✅ **Fail-fast validation** - Stops execution if >10% elevation data missing
- ✅ **Type safety** - TypedDict structures for IDE autocomplete and type checking
- ✅ **Structured logging** - All modules use consistent logging for debugging

**Documented in `CLAUDE.md`:**
- Engineering formulas with references
- API rate limit handling
- Security best practices
- Development guidelines

---

## Project structure

```
kml-earthworks/
├── app/
│   └── streamlit_app.py      # Streamlit UI orchestration
├── src/
│   ├── io_kml.py             # KML parsing, LineString extraction
│   ├── stationing.py         # Chainage calculation (Haversine distance)
│   ├── elevation.py          # Elevation API enrichment with fallback
│   ├── grade.py              # Constrained grade line optimization
│   ├── earthworks.py         # Cut/fill volumes, mass balance
│   ├── plots.py              # Plotly visualizations (6 chart types)
│   ├── exports.py            # Excel/HTML export generation
│   ├── types.py              # TypedDict definitions for type safety
│   ├── logger.py             # Centralized logging configuration
│   ├── leads.py              # Google Sheets lead capture (optional)
│   └── db.py                 # Supabase session logging (optional)
├── tests/
│   ├── test_earthworks.py    # Data aggregation tests
│   ├── test_elevation.py     # API tests (mocked)
│   ├── test_grade.py         # Grade + volume formula tests
│   ├── test_io_kml.py        # KML parsing tests
│   └── test_stationing.py    # Distance calculation tests
├── .claude/
│   └── CLAUDE.md             # AI development guidelines
├── data/                     # Sample KML files
├── requirements.txt
├── pytest.ini
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

## Accuracy & Disclaimer

**Engineering accuracy:**
- **Volume calculations**: Prismatoid formula (5-15% more accurate than average-end-area for irregular terrain)
- **Elevation data**: Open-Meteo API (30m resolution) with OpenTopoData SRTM fallback
- **Distance calculation**: Haversine formula for WGS84 great-circle distances
- **Grade optimization**: SciPy constrained optimization with slope and height limits

**Designed for early-stage estimation and fast iteration** — not for final design quantities.

⚠️ **Important limitations:**
- Elevation data resolution: 30m (SRTM) - not suitable for final design
- No consideration for: drainage, geotechnical conditions, traffic loads
- Shrink/swell factor is user-defined - verify for local soil types
- Cross-sections assume trapezoidal geometry

**Always validate against approved survey surfaces/DTM before using in procurement or construction.**

---

## Recent Improvements (2026-03)

**Major quality and accuracy enhancements:**

✅ **Volume Formula Upgrade**
- Migrated from average-end-area to prismatoid formula
- 5-15% more accurate for irregular terrain
- Full test coverage with validation against known values

✅ **Data Validation & Reliability**
- Fail-fast if >10% elevation data missing (prevents bad calculations)
- Sea level (0.0m) now correctly treated as valid data (not missing)
- Elevation API cooldown mechanism prevents rate limit issues

✅ **Type Safety & Code Quality**
- TypedDict structures for all data types (Point, Station, Alignment)
- Complete type hints on all public functions
- 100% CLAUDE.md compliance (development guidelines)

✅ **Test Coverage**
- 58 comprehensive tests covering all core modules
- New test suites for KML parsing and elevation APIs
- Mocked external API calls for reliable testing

✅ **Mass Balance Accuracy**
- Fixed aggregation bug in mass diagram for multiple alignments
- Detailed comments explaining shrink/swell engineering convention
- Per-alignment cumulative volume recalculation

✅ **Logging & Debugging**
- Structured logging replacing all print() statements
- Consistent error handling with exception logging
- Better diagnostics for troubleshooting issues

---

## Author

Built by **Caio Zanetti** — mining & earthworks engineer turned builder.
Questions or feedback? Open an issue or reach out on [LinkedIn](https://linkedin.com/in/caiozanetti).
