# CLAUDE.md - KML Earthworks Development Guide

**AI Assistant Development Guidelines for KML Earthworks**

This document guides Claude and other AI assistants in maintaining and extending this Streamlit-based earthworks calculation application.

---

## Project Overview

**Purpose:** Convert Google Earth KML sketches of access roads into terrain profiles, cut/fill volumes, and mass balance calculations.

**Core Value Proposition:** Replace manual GIS workflows with a browser-based tool requiring zero desktop software.

**Target Users:** Mining engineers, earthworks contractors, civil engineers doing early-stage road feasibility.

---

## Architecture & Structure

### Module Responsibilities

```
src/
├── io_kml.py         # KML parsing (LineString extraction from .kml files)
├── stationing.py     # Chainage calculation, 20m stake interpolation
├── elevation.py      # Terrain elevation via Open-Meteo API (with OpenTopoData fallback)
├── grade.py          # Grade line optimization (constraints: max slope, max height)
├── earthworks.py     # Cut/fill volume aggregation, mass balance per alignment
├── plots.py          # Plotly visualizations (profile, mass diagram, 3D view)
├── exports.py        # Excel/HTML report generation
├── leads.py          # Optional Google Sheets lead capture
├── db.py             # Optional Supabase session logging
└── logger.py         # Centralized logging configuration

app/
└── streamlit_app.py  # Main UI orchestration

tests/
├── test_stationing.py   # Haversine distance, interpolation tests
├── test_grade.py        # Grade constraints, volume calculation tests
└── test_earthworks.py   # Data aggregation, KPI tests
```

### Data Flow

1. **Upload** → `io_kml.parse_kml_file()` → List of alignments with WGS84 coordinates
2. **Elevation** → `elevation.enrich_elevation()` → Add `z_terrain_m` to each point
3. **Stationing** → `stationing.build_stationing()` → Interpolate 20m stakes, calculate terrain slope
4. **Grade** → `grade.compute_grade()` → Fit constrained grade line, calculate cut/fill
5. **Aggregation** → `earthworks.build_dataframe()` → Combine alignments into tidy DataFrame
6. **Visualization** → `plots.fig_*()` → Generate Plotly charts
7. **Export** → `exports.build_excel()` / `exports.build_html_report()`

---

## Code Standards

### Python Style

- **Python Version:** 3.9+ (use modern type hints: `list[Dict]`, `str | None`)
- **Formatting:** Follow PEP 8. Keep lines under 100 characters where reasonable.
- **Type Hints:** Use for function signatures. Required for public functions, optional for internal helpers.
- **Docstrings:** Google-style docstrings for all public functions. Include Args, Returns, and any important notes.

### Naming Conventions

- **Functions:** `snake_case` (e.g., `build_stationing`, `compute_grade`)
- **Classes:** `PascalCase` (rare in this codebase)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `_BATCH_SIZE`, `_API_URL`)
- **Private functions:** Leading underscore (e.g., `_fetch_batch`, `_haversine_dist`)

### Import Organization

```python
# Standard library
import os
from typing import Dict, List, Optional

# Third-party
import pandas as pd
import numpy as np
import requests

# Local modules
from src.logger import get_logger
```

---

## Critical Engineering Calculations

### DO NOT modify these without strong justification:

1. **Haversine Distance** (`stationing.py:_haversine_dist`)
   - Calculates great-circle distance between WGS84 coordinates
   - Used for chainage calculation
   - **Test coverage required** if modified

2. **Prismatoid Volume Formula** (`grade.py:_compute_volumes`)
   - Calculates cut/fill volumes between stations
   - Formula: `V = (A1 + A2 + 4*Am) * L / 6`
   - **Test coverage required** if modified

3. **Grade Constraint Solver** (`grade.py:_apply_grade_constraints`)
   - Enforces max slope and max height constraints
   - Uses forward/backward envelope tightening
   - **Complex logic - do not refactor without thorough testing**

4. **Mass Balance Calculation** (`earthworks.py`)
   - Applies shrink/swell factor to cut volume
   - Formula: `mass_balance = cut * shrink_swell - fill`
   - Must recalculate cumulatives per alignment (not across alignments)

---

## Testing Requirements

### When Tests Are Required

**Always write tests when:**
- Modifying any calculation in `stationing.py`, `grade.py`, or `earthworks.py`
- Adding new mathematical operations
- Changing API contract of a public function
- Fixing a bug (add regression test)

**Test files:** `tests/test_*.py`

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_grade.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Standards

- Use `pytest` framework
- Test edge cases: zero values, single point, very large numbers
- Use `pytest.approx()` for floating-point comparisons
- Mock external API calls (elevation APIs, Google Sheets)

---

## Security & Credentials

### CRITICAL: Never commit credentials

**Forbidden:**
```python
# ❌ NEVER DO THIS
SUPABASE_URL = "https://xyz.supabase.co"
SUPABASE_KEY = "eyJhbG..."
```

**Required:**
```python
# ✅ Always use environment variables or Streamlit secrets
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# or
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
```

### Credential Sources (in order of precedence)

1. Environment variables (`os.environ`)
2. Streamlit secrets (`st.secrets`)
3. `.env` file (local development only, never committed)

### Sensitive Data

- Supabase credentials: `SUPABASE_URL`, `SUPABASE_KEY`
- Google service account JSON: `gcp_service_account`
- Any API keys: store in secrets, never hardcode

---

## External APIs

### Elevation APIs

**Primary:** Open-Meteo Elevation API
- Free, no key required
- Rate limited (cooldown handled in code)
- Endpoint: `https://api.open-meteo.com/v1/elevation`

**Fallback:** OpenTopoData (SRTM 30m)
- Slower but more reliable
- Used when Open-Meteo hits rate limit
- Endpoint: `https://api.opentopodata.org/v1/srtm30m`

**Handling:**
- Always pass `cooldown_state=st.session_state` to `enrich_elevation()`
- DO NOT use module-level globals for cooldown (causes cross-session interference)
- Return validation report to show users when data is missing

### Error Handling for APIs

```python
# ✅ Good: Structured logging, user feedback
try:
    response = requests.post(url, data=payload, timeout=5)
    if response.status_code != 200:
        logger.warning(f"API failed: {response.status_code}")
        # Return fallback value or raise with context
except requests.RequestException as e:
    logger.error(f"Request failed: {e}", exc_info=True)
    # Handle gracefully
```

```python
# ❌ Bad: Bare except, silent failures
try:
    response = requests.post(url, data=payload)
except Exception:
    pass  # ❌ Silent failure
```

---

## Logging Standards

### Use Structured Logging

```python
from src.logger import get_logger

logger = get_logger(__name__)

# ✅ Good examples:
logger.info(f"Processing {len(points)} points")
logger.warning(f"Elevation missing for {count} points")
logger.error(f"API request failed: {e}", exc_info=True)
```

### Log Levels

- **DEBUG:** Detailed diagnostic info (rarely used)
- **INFO:** Expected events (e.g., "Processing started")
- **WARNING:** Unexpected but handled (e.g., "API cooldown active")
- **ERROR:** Failures requiring attention (e.g., "Database write failed")

### Avoid

```python
# ❌ Don't use print()
print(f"Error: {e}")

# ❌ Don't use bare except without logging
except Exception:
    pass
```

---

## Streamlit Best Practices

### Caching

**Use `@st.cache_data` for expensive operations:**
```python
@st.cache_data
def _process_kml(input_sig):
    # Expensive: parsing, elevation API calls
    return result
```

**Cache invalidation:**
- Use input signatures (file hash + design params)
- Keep separate caches for:
  1. Base data (KML + elevation)
  2. Design results (grade + volumes)

### Session State

**Use for:**
- API cooldown state (`st.session_state` passed to `enrich_elevation()`)
- User input persistence
- Multi-step workflows

**Avoid:**
- Storing large DataFrames (use `@st.cache_data` instead)
- Module-level globals (breaks multi-session deployments)

### User Feedback

**Always show progress for slow operations:**
```python
progress_bar = st.progress(0)
for i, batch in enumerate(batches):
    # Process batch
    progress_bar.progress((i + 1) / len(batches))
progress_bar.empty()
```

**Show warnings for data issues:**
```python
if missing_count > 0:
    st.warning(f"Elevation data missing for {missing_count} points")
```

---

## Deployment (Streamlit Cloud)

### Configuration Files

- **requirements.txt:** Python dependencies (keep minimal, pinned versions)
- **pyproject.toml:** Package metadata (optional but recommended)
- **.streamlit/config.toml:** Streamlit settings (if needed)

### Secrets Management

Add to Streamlit Cloud dashboard:
```toml
# .streamlit/secrets.toml (NOT committed)
SUPABASE_URL = "https://..."
SUPABASE_KEY = "..."

[gcp_service_account]
type = "service_account"
project_id = "..."
# ... (full service account JSON)
```

### Performance Considerations

- **Cold start:** First user hit after inactivity takes ~10s
- **Elevation API:** Batch size = 100 points (don't increase, causes timeouts)
- **Large files:** KML with >1000 points may take 1-2 minutes
- **Concurrent users:** Cooldown is per-session (no cross-session blocking)

---

## Git Workflow

### Commit Messages

Follow conventional commits:
```
feat: add 3D terrain visualization
fix: correct prismatoid volume formula for edge case
docs: update README with API rate limits
test: add tests for mass balance calculation
refactor: extract elevation fallback logic
```

### Branch Strategy

- **main:** Production-ready code (deployed to Streamlit Cloud)
- **feature/*:** New features
- **fix/*:** Bug fixes

### Before Committing

1. Run tests: `pytest tests/ -v`
2. Check for secrets: `git diff | grep -i "key\|secret\|password"`
3. Update CHANGELOG.md if user-facing change

---

## Common Pitfalls & Solutions

### 1. Elevation Data Returns None

**Symptom:** TypeError when calculating volumes
**Cause:** `r.get("elevation", 0.0)` returns `None` when key exists but value is null
**Solution:**
```python
# ✅ Use 'or' operator
elevations = [r.get("elevation") or 0.0 for r in results]
```

### 2. Cumulative Volumes Wrong for Multiple Alignments

**Symptom:** Mass balance incorrect after first alignment
**Cause:** Cumulative volumes not reset between alignments
**Solution:**
```python
# ✅ Recalculate per alignment
df["cut_vol_cum_m3"] = df.groupby(["file_name", "access_id"])["cut_vol_m3"].cumsum()
```

### 3. Module Import Errors in Tests

**Symptom:** `ModuleNotFoundError: No module named 'src'`
**Cause:** Python path not set up correctly
**Solution:** Add `pyproject.toml` with `[tool.setuptools.packages.find]` or run from project root

### 4. Rate Limit Affects All Users

**Symptom:** One user's rate limit blocks everyone
**Cause:** Global cooldown variable shared across sessions
**Solution:**
```python
# ✅ Pass session state
enrich_elevation(points, cooldown_state=st.session_state)
```

---

## Performance Optimization

### DO optimize:
- Batch API calls (current: 100 points per batch)
- Cache expensive operations (`@st.cache_data`)
- Use NumPy vectorization for array operations

### DON'T optimize prematurely:
- Python loops < 1000 iterations are fine
- Don't sacrifice readability for marginal gains
- Profile before optimizing (use `cProfile` or `line_profiler`)

---

## Documentation Standards

### Code Comments

**When to comment:**
- Complex algorithms (e.g., grade constraint solver)
- Non-obvious workarounds (e.g., API quirks)
- Engineering formulas (e.g., prismatoid formula)

**When NOT to comment:**
- Self-explanatory code
- Obvious variable names
- Simple operations

```python
# ✅ Good comment
# Prismatoid formula: V = (A1 + A2 + 4*Am) * L / 6
# where Am is area at midpoint, L is segment length

# ❌ Bad comment
# Loop through points
for point in points:
```

### Function Docstrings

**Required for all public functions:**
```python
def enrich_elevation(
    points: List[Dict],
    progress_callback=None,
    cooldown_state: Optional[Dict] = None
) -> Tuple[List[Dict], Dict]:
    """
    Add terrain elevation to coordinate points via external API.

    Args:
        points: List of dicts with 'lat' and 'lon' keys
        progress_callback: Optional callable(done, total) for UI updates
        cooldown_state: Dict to store API cooldown state (use st.session_state)

    Returns:
        Tuple of (enriched points, validation dict with 'missing_count' and 'success_rate')

    Raises:
        RuntimeError: If all API attempts fail for a batch
    """
```

---

## Breaking Changes

### Before making breaking changes:

1. **Check downstream impact:**
   - Streamlit UI calls
   - Test files
   - Cached results (may need cache key update)

2. **Add deprecation warnings:**
```python
import warnings
warnings.warn("old_function() is deprecated, use new_function()", DeprecationWarning)
```

3. **Update tests first (TDD approach)**

4. **Document in commit message and CHANGELOG.md**

---

## Quick Reference Commands

```bash
# Development
streamlit run app/streamlit_app.py          # Run locally
pytest tests/ -v                             # Run tests
pytest tests/ --cov=src                      # Run with coverage

# Git
git log --oneline -10                        # Recent commits
git diff --stat                              # Changes summary
git blame src/grade.py                       # See who changed what

# Dependencies
pip install -r requirements.txt              # Install deps
pip freeze > requirements.txt                # Update deps (careful!)

# Debugging
python -m pdb app/streamlit_app.py          # Debug mode
python -m cProfile -s cumtime script.py      # Profile performance
```

---

## Contact & Support

- **Maintainer:** Caio Zanetti
- **Issues:** [GitHub Issues](https://github.com/CAIOZANETTI/kml-earthworks/issues)
- **Deployment:** [Streamlit Cloud](https://kml-earthworks.streamlit.app)

---

**Last Updated:** 2026-03-12
**Claude Version:** This guide is optimized for Claude Sonnet 4.5 and later
