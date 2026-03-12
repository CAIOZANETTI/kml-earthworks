"""
Unit tests for io_kml.py
Tests KML parsing, LineString extraction, and coordinate parsing.
"""

import pytest
from src.io_kml import parse_kml_file, parse_multiple_kml, _parse_coordinates


class TestKMLParsing:
    """Tests for KML file parsing"""

    def test_parse_simple_linestring(self):
        """Parse KML with single LineString"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Document>
                <Placemark>
                    <name>Test Road</name>
                    <LineString>
                        <coordinates>
                            -43.5,-22.5,0
                            -43.4,-22.4,0
                            -43.3,-22.3,0
                        </coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 1
        assert result[0]["file_name"] == "test.kml"
        assert result[0]["access_id"] == "Test Road"
        assert len(result[0]["points"]) == 3
        assert result[0]["points"][0] == {"lat": -22.5, "lon": -43.5}
        assert result[0]["points"][1] == {"lat": -22.4, "lon": -43.4}
        assert result[0]["points"][2] == {"lat": -22.3, "lon": -43.3}

    def test_parse_multiple_linestrings(self):
        """Parse KML with multiple LineStrings"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Document>
                <Placemark>
                    <name>Road 1</name>
                    <LineString>
                        <coordinates>-43.5,-22.5 -43.4,-22.4</coordinates>
                    </LineString>
                </Placemark>
                <Placemark>
                    <name>Road 2</name>
                    <LineString>
                        <coordinates>-43.3,-22.3 -43.2,-22.2</coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 2
        assert result[0]["access_id"] == "Road 1"
        assert result[1]["access_id"] == "Road 2"
        assert len(result[0]["points"]) == 2
        assert len(result[1]["points"]) == 2

    def test_parse_linestring_without_name(self):
        """Parse LineString without Placemark name generates default name"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Document>
                <Placemark>
                    <LineString>
                        <coordinates>-43.5,-22.5 -43.4,-22.4</coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 1
        assert result[0]["access_id"] == "access_01"  # Default name

    def test_parse_invalid_kml_raises_error(self):
        """Invalid XML should raise ValueError"""
        invalid_kml = b"<kml><not-closed>"

        with pytest.raises(ValueError, match="Invalid KML file"):
            parse_kml_file(invalid_kml, "bad.kml")

    def test_parse_kml_with_no_linestrings(self):
        """KML without LineStrings returns empty list"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Document>
                <Placemark>
                    <name>Point Only</name>
                    <Point>
                        <coordinates>-43.5,-22.5,0</coordinates>
                    </Point>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 0

    def test_parse_linestring_with_single_point(self):
        """LineString with < 2 points is skipped"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Document>
                <Placemark>
                    <LineString>
                        <coordinates>-43.5,-22.5</coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 0  # Single point is insufficient


class TestCoordinateParsing:
    """Tests for coordinate string parsing"""

    def test_parse_coordinates_space_separated(self):
        """Parse coordinates separated by spaces"""
        coord_text = "-43.5,-22.5,0 -43.4,-22.4,0 -43.3,-22.3,0"
        result = _parse_coordinates(coord_text)

        assert len(result) == 3
        assert result[0] == {"lat": -22.5, "lon": -43.5}

    def test_parse_coordinates_newline_separated(self):
        """Parse coordinates separated by newlines"""
        coord_text = """
            -43.5,-22.5,0
            -43.4,-22.4,0
            -43.3,-22.3,0
        """
        result = _parse_coordinates(coord_text)

        assert len(result) == 3

    def test_parse_coordinates_without_elevation(self):
        """Parse coordinates with only lon,lat (no elevation)"""
        coord_text = "-43.5,-22.5 -43.4,-22.4"
        result = _parse_coordinates(coord_text)

        assert len(result) == 2
        assert result[0] == {"lat": -22.5, "lon": -43.5}

    def test_parse_coordinates_skip_invalid(self):
        """Invalid coordinate tokens are skipped"""
        coord_text = "-43.5,-22.5 invalid,token -43.4,-22.4"
        result = _parse_coordinates(coord_text)

        assert len(result) == 2  # Invalid token skipped
        assert result[0] == {"lat": -22.5, "lon": -43.5}
        assert result[1] == {"lat": -22.4, "lon": -43.4}

    def test_parse_coordinates_empty_string(self):
        """Empty coordinate string returns empty list"""
        result = _parse_coordinates("")
        assert len(result) == 0

        result = _parse_coordinates("   \n  ")
        assert len(result) == 0


class TestMultipleKMLFiles:
    """Tests for parsing multiple KML files"""

    def test_parse_multiple_files(self):
        """Parse multiple KML files and combine alignments"""
        kml1 = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Placemark><name>Road A</name>
                <LineString><coordinates>-43.5,-22.5 -43.4,-22.4</coordinates></LineString>
            </Placemark>
        </kml>"""

        kml2 = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
            <Placemark><name>Road B</name>
                <LineString><coordinates>-43.3,-22.3 -43.2,-22.2</coordinates></LineString>
            </Placemark>
        </kml>"""

        files = [
            {"name": "file1.kml", "content": kml1},
            {"name": "file2.kml", "content": kml2},
        ]

        result = parse_multiple_kml(files)

        assert len(result) == 2
        assert result[0]["file_name"] == "file1.kml"
        assert result[0]["access_id"] == "Road A"
        assert result[1]["file_name"] == "file2.kml"
        assert result[1]["access_id"] == "Road B"

    def test_parse_empty_file_list(self):
        """Empty file list returns empty result"""
        result = parse_multiple_kml([])
        assert len(result) == 0


class TestKMLNamespaceHandling:
    """Tests for different KML namespace variants"""

    def test_parse_google_earth_namespace(self):
        """Parse KML with Google Earth namespace"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://earth.google.com/kml/2.2">
            <Document>
                <Placemark>
                    <name>Test</name>
                    <LineString>
                        <coordinates>-43.5,-22.5 -43.4,-22.4</coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 1
        assert result[0]["access_id"] == "Test"

    def test_parse_no_namespace(self):
        """Parse KML without namespace"""
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <kml>
            <Document>
                <Placemark>
                    <name>Test</name>
                    <LineString>
                        <coordinates>-43.5,-22.5 -43.4,-22.4</coordinates>
                    </LineString>
                </Placemark>
            </Document>
        </kml>"""

        result = parse_kml_file(kml_content, "test.kml")

        assert len(result) == 1
        assert result[0]["access_id"] == "Test"
