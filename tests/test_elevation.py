"""
Unit tests for elevation.py
Tests external API calls (mocked), error handling, and validation logic.
"""

import pytest
from unittest.mock import Mock, patch
from src.elevation import enrich_elevation, _fetch_batch, _guess_meteo_wait_seconds


class TestElevationEnrichment:
    """Tests for enrich_elevation function"""

    @patch('src.elevation.requests.Session')
    def test_enrich_elevation_success(self, mock_session_class):
        """Successfully enrich points with elevation data"""
        # Mock successful API response
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": [100.0, 150.0, 200.0]}
        mock_session.get.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [
            {"lat": -22.5, "lon": -43.5},
            {"lat": -22.4, "lon": -43.4},
            {"lat": -22.3, "lon": -43.3},
        ]

        result_points, validation = enrich_elevation(points)

        assert len(result_points) == 3
        assert result_points[0]["z_terrain_m"] == 100.0
        assert result_points[1]["z_terrain_m"] == 150.0
        assert result_points[2]["z_terrain_m"] == 200.0
        assert validation["missing_count"] == 0
        assert validation["success_rate"] == 100.0

    @patch('src.elevation.requests.Session')
    def test_enrich_elevation_with_missing_data(self, mock_session_class):
        """Handle missing elevation data (None) correctly with <= 10% failure"""
        # Mock API returning None for 1 out of 20 points (5% failure rate)
        mock_session = Mock()
        mock_response = Mock()
        elevations = [100.0 + i * 10.0 for i in range(20)]
        elevations[5] = None  # One missing point
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": elevations}
        mock_session.get.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [{"lat": -22.5 + i * 0.01, "lon": -43.5 + i * 0.01} for i in range(20)]

        result_points, validation = enrich_elevation(points)

        assert len(result_points) == 20
        assert result_points[5]["z_terrain_m"] == 0.0  # None → 0.0 fallback
        assert validation["missing_count"] == 1
        assert validation["success_rate"] == pytest.approx(95.0, abs=0.1)

    @patch('src.elevation.requests.Session')
    def test_enrich_elevation_sea_level_valid(self, mock_session_class):
        """Sea level (0.0) should be treated as valid data, not missing"""
        # Mock API returning 0.0 (sea level)
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": [0.0, 100.0, 0.0]}
        mock_session.get.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [
            {"lat": -22.5, "lon": -43.5},  # Sea level
            {"lat": -22.4, "lon": -43.4},
            {"lat": -22.3, "lon": -43.3},  # Sea level
        ]

        result_points, validation = enrich_elevation(points)

        assert result_points[0]["z_terrain_m"] == 0.0
        assert result_points[2]["z_terrain_m"] == 0.0
        # CRITICAL: 0.0 should NOT be counted as missing
        assert validation["missing_count"] == 0
        assert validation["success_rate"] == 100.0

    @patch('src.elevation.requests.Session')
    def test_enrich_elevation_high_failure_rate_raises(self, mock_session_class):
        """High failure rate (> 10%) should raise RuntimeError"""
        # Mock API failing for entire batch
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [{"lat": -22.5, "lon": -43.5} for _ in range(20)]

        with pytest.raises(RuntimeError, match="Elevation data failed for"):
            enrich_elevation(points)

    @patch('src.elevation.requests.Session')
    def test_enrich_elevation_progress_callback(self, mock_session_class):
        """Progress callback is called during enrichment"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": [100.0, 150.0]}
        mock_session.get.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [
            {"lat": -22.5, "lon": -43.5},
            {"lat": -22.4, "lon": -43.4},
        ]

        progress_calls = []
        def progress_cb(done, total):
            progress_calls.append((done, total))

        enrich_elevation(points, progress_callback=progress_cb)

        assert len(progress_calls) > 0
        assert progress_calls[-1] == (2, 2)  # Final call


class TestFetchBatch:
    """Tests for _fetch_batch function"""

    @patch('src.elevation.requests')
    def test_fetch_batch_open_meteo_success(self, mock_requests):
        """Successful fetch from Open-Meteo API"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": [100.0, 150.0, 200.0]}
        mock_requests.get.return_value = mock_response

        lats = [-22.5, -22.4, -22.3]
        lons = [-43.5, -43.4, -43.3]

        result = _fetch_batch(lats, lons)

        assert result == [100.0, 150.0, 200.0]
        assert mock_requests.get.called

    @patch('src.elevation.requests')
    def test_fetch_batch_fallback_to_opentopo(self, mock_requests):
        """Fallback to OpenTopoData when Open-Meteo fails"""
        # Open-Meteo fails
        meteo_response = Mock()
        meteo_response.status_code = 429  # Rate limit
        meteo_response.json.return_value = {"reason": "Rate limit exceeded"}

        # OpenTopoData succeeds
        topo_response = Mock()
        topo_response.status_code = 200
        topo_response.json.return_value = {
            "results": [
                {"elevation": 100.0},
                {"elevation": 150.0},
            ]
        }

        mock_requests.get.return_value = meteo_response
        mock_requests.post.return_value = topo_response

        lats = [-22.5, -22.4]
        lons = [-43.5, -43.4]

        result = _fetch_batch(lats, lons)

        assert result == [100.0, 150.0]
        assert mock_requests.post.called  # Fallback was used

    @patch('src.elevation.requests')
    def test_fetch_batch_both_apis_fail(self, mock_requests):
        """Raise RuntimeError when both APIs fail"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_requests.get.return_value = mock_response
        mock_requests.post.return_value = mock_response

        lats = [-22.5, -22.4]
        lons = [-43.5, -43.4]

        with pytest.raises(RuntimeError, match="Elevation API failed"):
            _fetch_batch(lats, lons)

    @patch('src.elevation.requests')
    def test_fetch_batch_cooldown_active(self, mock_requests):
        """Cooldown prevents Open-Meteo calls and uses fallback"""
        import time

        # Set cooldown in future
        cooldown_state = {'meteo_cooldown_until': time.time() + 100}

        # OpenTopoData succeeds
        topo_response = Mock()
        topo_response.status_code = 200
        topo_response.json.return_value = {
            "results": [{"elevation": 100.0}]
        }
        mock_requests.post.return_value = topo_response

        lats = [-22.5]
        lons = [-43.5]

        result = _fetch_batch(lats, lons, cooldown_state=cooldown_state)

        assert result == [100.0]
        # Open-Meteo should NOT be called due to cooldown
        assert not mock_requests.get.called
        assert mock_requests.post.called


class TestCooldownParsing:
    """Tests for _guess_meteo_wait_seconds"""

    def test_parse_minute_from_text(self):
        """Parse 'X minute' from rate limit message"""
        result = _guess_meteo_wait_seconds("Try again in 2 minutes")
        assert result == 120

    def test_parse_second_from_text(self):
        """Parse 'X second' from rate limit message"""
        result = _guess_meteo_wait_seconds("Try again in 30 seconds")
        assert result == 30

    def test_parse_one_minute(self):
        """Parse 'one minute' text"""
        result = _guess_meteo_wait_seconds("Try again in one minute")
        assert result == 60

    def test_default_cooldown_no_match(self):
        """Return default cooldown when no pattern matches"""
        result = _guess_meteo_wait_seconds("Rate limit exceeded")
        assert result == 60  # Default

    def test_empty_reason_returns_default(self):
        """Empty or None reason returns default"""
        assert _guess_meteo_wait_seconds("") == 60
        assert _guess_meteo_wait_seconds(None) == 60


class TestValidationReport:
    """Tests for validation report structure"""

    @patch('src.elevation.requests.Session')
    def test_validation_report_structure(self, mock_session_class):
        """Validation report has correct structure"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        # Use 10 points with 1 missing (10% failure - at threshold)
        elevations = [100.0 + i * 10.0 for i in range(10)]
        elevations[5] = None  # One missing
        mock_response.json.return_value = {"elevation": elevations}
        mock_session.get.return_value = mock_response
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session_class.return_value = mock_session

        points = [{"lat": -22.5 + i * 0.01, "lon": -43.5 + i * 0.01} for i in range(10)]

        _, validation = enrich_elevation(points)

        assert "missing_count" in validation
        assert "total_count" in validation
        assert "success_rate" in validation
        assert "failed_batches" in validation
        assert validation["total_count"] == 10
        assert isinstance(validation["success_rate"], float)
