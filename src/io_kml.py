"""
io_kml.py
Parse KML files and extract LineString alignments.
Each LineString becomes one Access alignment.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict

from src.types import Point, PointList, Alignment, AlignmentList


# KML namespace variants
_NS = [
    "{http://www.opengis.net/kml/2.2}",
    "{http://earth.google.com/kml/2.2}",
    "{http://earth.google.com/kml/2.1}",
    "",
]


def _find(element, tag):
    """Try all known KML namespaces."""
    for ns in _NS:
        found = element.find(f".//{ns}{tag}")
        if found is not None:
            return found
    return None


def _findall(element, tag):
    """Try all known KML namespaces, return first non-empty list."""
    for ns in _NS:
        found = element.findall(f".//{ns}{tag}")
        if found:
            return found
    return []


def _parse_coordinates(coord_text: str) -> PointList:
    """Parse a <coordinates> text block into list of {lon, lat} dicts."""
    points = []
    for token in coord_text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                points.append({"lat": lat, "lon": lon})
            except ValueError:
                continue
    return points


def _get_placemark_name(placemark, index: int) -> str:
    """Extract name from Placemark or generate default."""
    for ns in _NS:
        name_el = placemark.find(f"{ns}name")
        if name_el is not None and name_el.text:
            return name_el.text.strip()
    return f"access_{index + 1:02d}"


def parse_kml_file(file_content: bytes, file_name: str) -> AlignmentList:
    """
    Parse a KML file content and return a list of alignments.

    Each alignment is a dict:
        {
            "file_name": str,
            "access_id": str,
            "points": [{"lat": float, "lon": float}, ...]
        }
    """
    try:
        root = ET.fromstring(file_content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid KML file '{file_name}': {e}")

    alignments = []
    placemarks = _findall(root, "Placemark")

    ls_index = 0
    for placemark in placemarks:
        line_strings = _findall(placemark, "LineString")
        for ls in line_strings:
            coord_el = _find(ls, "coordinates")
            if coord_el is None or not coord_el.text:
                continue
            points = _parse_coordinates(coord_el.text)
            if len(points) < 2:
                continue

            name = _get_placemark_name(placemark, ls_index)
            alignments.append(
                {
                    "file_name": file_name,
                    "access_id": name,
                    "points": points,
                }
            )
            ls_index += 1

    return alignments


def parse_multiple_kml(files: List[Dict]) -> AlignmentList:
    """
    Parse multiple KML files.

    Args:
        files: list of {"name": str, "content": bytes}

    Returns:
        list of alignment dicts (file_name, access_id, points)
    """
    all_alignments = []
    for f in files:
        aligns = parse_kml_file(f["content"], f["name"])
        all_alignments.extend(aligns)
    return all_alignments
