"""Phase 5 — basic impact analysis: intersect a modelled flood extent with the
real Ujjani OSM infrastructure layers.

Datasets (data/cases/ujjani_real/):
    roads_osm.geojson        REAL DATA (OSM) — LineStrings, EPSG:4326
    facilities_osm.geojson   REAL DATA (OSM) — Points, EPSG:4326
    settlements_osm.geojson   REAL DATA (OSM) — currently EMPTY -> "unavailable"

No population raster is connected -> population exposure is "unavailable"
(never fabricated). Counts are spatial intersections of MODEL OUTPUT
(flood extent) with REAL DATA infrastructure — not observed impact.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

OSM = config.ROOT / "data" / "cases" / "ujjani_real"
ROADS = OSM / "roads_osm.geojson"
FACILITIES = OSM / "facilities_osm.geojson"
SETTLEMENTS = OSM / "settlements_osm.geojson"

DEG_TO_KM_LAT = 111.32  # rough, near 18 N


def _flood_geometry(flood_geojson: Path):
    from shapely.geometry import shape
    from shapely.ops import unary_union

    data = json.loads(Path(flood_geojson).read_text(encoding="utf-8"))
    polys = [shape(f["geometry"]) for f in data.get("features", [])
             if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")]
    if not polys:
        return None
    geom = unary_union([p.buffer(0) for p in polys])
    return geom if not geom.is_empty else None


def _load_features(path: Path):
    if not path.exists():
        return None, "dataset file not found"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read dataset: {exc}"
    feats = data.get("features", [])
    if not feats:
        return None, "dataset has no features"
    return feats, None


def analyse(flood_geojson: str | Path, out_dir: str | Path,
            summary_area_km2: float | None = None) -> dict:
    from shapely.geometry import shape

    out_dir = Path(out_dir)
    flood = _flood_geometry(Path(flood_geojson))
    result = {
        "data_classification": {
            "flood_extent": "MODEL OUTPUT (Delft3D / SPH / approximate)",
            "roads / facilities / settlements": "REAL DATA (OpenStreetMap)",
            "counts": "DERIVED (spatial intersection of MODEL OUTPUT with REAL DATA) — not observed impact",
            "population": "OBSERVATION / census — NOT CONNECTED",
        },
        "flooded_area_km2": summary_area_km2,
        "roads": {"status": "unavailable"},
        "facilities": {"status": "unavailable"},
        "settlements": {"status": "unavailable", "reason": "settlements_osm.geojson has no features"},
        "population": {"status": "unavailable",
                       "reason": "no population dataset connected — exposure not computed"},
        "validation_status": "NOT PERFORMED",
        "note": "Counts are model-derived spatial intersections, not surveyed damage.",
    }
    if flood is None:
        result["error"] = "flood extent has no polygon geometry"
        (out_dir / "impact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    b = flood.bounds
    result["flood_bounds_lonlat"] = [round(v, 6) for v in b]

    # --- roads (LineStrings) ---------------------------------------------- #
    feats, err = _load_features(ROADS)
    if feats is None:
        result["roads"] = {"status": "unavailable", "reason": err}
    else:
        n_hit, length_km, by_type = 0, 0.0, {}
        for f in feats:
            g = f.get("geometry", {})
            if g.get("type") not in ("LineString", "MultiLineString"):
                continue
            try:
                line = shape(g)
            except Exception:  # noqa: BLE001
                continue
            if not line.intersects(flood):
                continue
            n_hit += 1
            inter = line.intersection(flood)
            length_km += float(getattr(inter, "length", 0.0)) * DEG_TO_KM_LAT
            rt = (f.get("properties") or {}).get("highway") or (f.get("properties") or {}).get("road_type") or "road"
            by_type[rt] = by_type.get(rt, 0) + 1
        result["roads"] = {
            "status": "ok", "source": "OpenStreetMap (roads_osm.geojson)",
            "total_in_dataset": sum(1 for f in feats if f.get("geometry", {}).get("type", "").endswith("LineString")),
            "affected_count": n_hit,
            "approx_flooded_length_km": round(length_km, 2),
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        }

    # --- facilities (Points) -------------------------------------------- #
    feats, err = _load_features(FACILITIES)
    if feats is None:
        result["facilities"] = {"status": "unavailable", "reason": err}
    else:
        hit = []
        for f in feats:
            g = f.get("geometry", {})
            if g.get("type") != "Point":
                continue
            try:
                pt = shape(g)
            except Exception:  # noqa: BLE001
                continue
            if flood.covers(pt) or flood.distance(pt) < 1e-9:
                p = f.get("properties") or {}
                hit.append({"name": p.get("name") or p.get("amenity") or "facility",
                            "type": p.get("amenity") or p.get("facility_type") or "unknown"})
        result["facilities"] = {
            "status": "ok", "source": "OpenStreetMap (facilities_osm.geojson)",
            "total_in_dataset": sum(1 for f in feats if f.get("geometry", {}).get("type") == "Point"),
            "affected_count": len(hit), "affected": hit,
        }

    (out_dir / "impact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
