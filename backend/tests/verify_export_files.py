import csv
import json
from pathlib import Path
from xml.etree import ElementTree

folder = Path(__file__).resolve().parents[2] / "data" / "exports" / "verification"
namespace = {"k": "http://www.opengis.net/kml/2.2"}
for minute in [0, 15, 30, 60]:
    stem = f"jaldrishti-prototype-T{minute:02}"
    summary = json.loads((folder / f"{stem}.json").read_text(encoding="utf-8"))
    assert summary["metadata"]["active_timeline_frame"] == minute
    assert summary["metadata"]["validation_status"] == "Not validated hydraulic output"
    geo = json.loads((folder / f"{stem}.geojson").read_text(encoding="utf-8"))
    assert len(geo["features"]) == int(minute > 0)
    with (folder / f"{stem}.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert all(row["scenario_name"] == 'Verification <A> & "B"' for row in rows)
    assert all(int(row["active_timeline_frame"]) == minute for row in rows)
    kml = ElementTree.parse(folder / f"{stem}.kml")
    polygons = kml.findall(".//k:Polygon", namespace)
    assert len(polygons) == int(minute > 0)
    if minute:
        text = kml.find(".//k:coordinates", namespace).text
        ring = [[float(value) for value in item.split(",")[:2]] for item in text.split()]
        assert ring == geo["features"][0]["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
print("Parsed and validated all 16 JSON, CSV, GeoJSON and KML files with Python standard-library parsers.")
