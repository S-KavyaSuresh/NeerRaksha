"""Phase 5 — basic impact analysis: intersect a modelled flood extent with the
real Ujjani OSM infrastructure layers.

Datasets (data/cases/ujjani_real/):
    roads_osm.geojson        REAL DATA (OSM) — LineStrings, EPSG:4326.
                             Curated road-network-only extract: every feature
                             carries a `highway` tag and there is no
                             waterway / railway / barrier geometry in the file
                             (verified). Kept as-is; a `highway IS NOT NULL`
                             guard is still applied so a future non-road feature
                             cannot be miscounted as a road.
    facilities_osm.geojson   REAL DATA (OSM) — Points, EPSG:4326 (curated, has `amenity`)
    osm_ujjani.gpkg          REAL DATA (OSM) — full extract, EPSG:4326
        layer `multipolygons` (building=*)  -> buildings
        layer `points`        (place=*)     -> settlement centre nodes
    population/ujjani_population_2020.tif   REAL DATA (WorldPop 2020 constrained,
        UN-adjusted, ~100 m, EPSG:4326, persons/pixel) -> estimated population
        exposed within the modelled flood extent. If this file is absent the
        population result stays "unavailable" (never fabricated).

Counts are spatial intersections of MODEL OUTPUT (flood extent) with REAL DATA
infrastructure — they are DERIVED IMPACT, not observed / surveyed damage.

Semantics that must be preserved everywhere:
    status "ok",  affected_count 0  -> the modelled flood extent does not reach
                                       this asset class (analysis ran).
    status "unavailable"            -> the dataset / layer / attribute needed for
                                       this asset class is not available.
These two states are never collapsed.

Metric geometry: OSM is EPSG:4326; road flooded length and building flooded
footprint are computed after reprojection to EPSG:32643 (UTM 43N, metres).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import config

OSM = config.ROOT / "data" / "cases" / "ujjani_real"
ROADS = OSM / "roads_osm.geojson"
FACILITIES = OSM / "facilities_osm.geojson"
GPKG = OSM / "osm_ujjani.gpkg"
POPULATION = OSM / "population" / "ujjani_population_2020.tif"
POPULATION_META = OSM / "population" / "metadata.json"

WGS84 = "EPSG:4326"
METRIC = "EPSG:32643"  # UTM 43N — metric CRS for Ujjani (lengths / areas)


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


def _read_gpkg_layer(layer: str):
    """Return (GeoDataFrame in EPSG:4326, None) or (None, reason). No fallback."""
    if not GPKG.exists():
        return None, f"{GPKG.name} not found — real OSM extract not connected"
    try:
        import geopandas as gpd
    except Exception as exc:  # noqa: BLE001
        return None, f"geopandas unavailable: {exc}"
    try:
        gdf = gpd.read_file(GPKG, layer=layer)
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read layer '{layer}': {exc}"
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)
    elif str(gdf.crs).upper() not in ("EPSG:4326", "WGS84"):
        gdf = gdf.to_crs(WGS84)
    return gdf, None


def _flood_in_metric(flood):
    """Project the (WGS84) flood union geometry to EPSG:32643."""
    import geopandas as gpd

    return gpd.GeoSeries([flood], crs=WGS84).to_crs(METRIC).iloc[0]


def analyse(flood_geojson: str | Path, out_dir: str | Path,
            summary_area_km2: float | None = None,
            source: dict | None = None) -> dict:
    out_dir = Path(out_dir)
    flood = _flood_geometry(Path(flood_geojson))
    result = {
        "source": source or {"note": "impact provenance not supplied by caller"},
        "data_classification": {
            "flood_extent": "MODEL OUTPUT (Delft3D / SPH / approximate)",
            "roads / buildings / facilities / settlements": "REAL DATA (OpenStreetMap)",
            "counts": "DERIVED IMPACT (spatial intersection of MODEL OUTPUT with REAL DATA) — not observed damage",
            "population": "OBSERVATION / census — NOT CONNECTED",
        },
        "flooded_area_km2": summary_area_km2,
        "roads": {"status": "unavailable"},
        "buildings": {"status": "unavailable"},
        "facilities": {"status": "unavailable"},
        "settlements": {"status": "unavailable"},
        "population": {"status": "unavailable",
                       "reason": "no population dataset connected — exposure not computed"},
        "validation_status": "NOT PERFORMED",
        "note": "Counts are model-derived spatial intersections, not surveyed damage. "
                "status 'ok' with affected_count 0 means the modelled extent does not reach "
                "that asset class; status 'unavailable' means the dataset itself is missing.",
    }
    if flood is None:
        result["error"] = "flood extent has no polygon geometry"
        (out_dir / "impact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    result["flood_bounds_lonlat"] = [round(v, 6) for v in flood.bounds]

    result["roads"] = _roads_impact(flood)
    result["facilities"] = _facilities_impact(flood)
    result["buildings"] = _buildings_impact(flood)
    result["settlements"] = _settlements_impact(flood)
    result["population"] = _population_impact(flood)

    # fold population dataset provenance into the caller-supplied source block
    pop = result["population"]
    if pop.get("status") == "ok":
        prov = {k: pop[k] for k in ("dataset", "product", "year", "resolution",
                                    "crs", "doi", "source_url", "license") if pop.get(k) is not None}
        result["source"] = {**(source or {}), "population_dataset": prov}

    (out_dir / "impact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _roads_impact(flood) -> dict:
    feats, err = _load_features(ROADS)
    if feats is None:
        return {"status": "unavailable", "reason": err}
    try:
        import geopandas as gpd
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"geopandas unavailable: {exc}"}

    gdf = gpd.GeoDataFrame.from_features(feats, crs=WGS84)
    gdf = gdf[gdf.geometry.type.isin(["LineString", "MultiLineString"])]
    # Curated file is road-network-only (every feature carries `highway`); the
    # guard below only bites if a non-road feature is ever added to the source.
    if "highway" in gdf.columns:
        roads = gdf[gdf["highway"].notna()].copy()
        road_filter = "highway IS NOT NULL"
    else:
        roads = gdf.copy()
        road_filter = "geometry type LineString/MultiLineString (no `highway` attribute in source)"
    total = int(len(roads))
    if total == 0:
        return {"status": "unavailable", "reason": "no road features after filtering"}

    # --- metric length: reproject to EPSG:32643 before measuring ------------- #
    flood_m = _flood_in_metric(flood)
    roads_m = roads.to_crs(METRIC)
    hit_mask = roads_m.intersects(flood_m)
    affected_idx = roads_m.index[hit_mask]
    flooded_length_km = float(roads_m.loc[affected_idx].intersection(flood_m).length.sum()) / 1000.0

    if "highway" in roads.columns:
        by_type = (roads.loc[affected_idx, "highway"].fillna("road")
                   .value_counts().to_dict())
    else:
        by_type = {}
    return {
        "status": "ok",
        "source": "OpenStreetMap (roads_osm.geojson — curated road-network-only extract; "
                  f"{total}/{len(gdf)} line features carry a `highway` tag, no waterway/railway/barrier geometry)",
        "road_filter": road_filter,
        "length_crs": METRIC,
        "total_in_dataset": total,
        "affected_count": int(hit_mask.sum()),
        "approx_flooded_length_km": round(flooded_length_km, 2),
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
    }


def _facilities_impact(flood) -> dict:
    from shapely.geometry import shape

    feats, err = _load_features(FACILITIES)
    if feats is None:
        return {"status": "unavailable", "reason": err}

    points = [f for f in feats if f.get("geometry", {}).get("type") == "Point"]
    total_by_type = Counter(
        ((f.get("properties") or {}).get("amenity")
         or (f.get("properties") or {}).get("facility_type") or "unknown")
        for f in points
    )
    hit = []
    for f in points:
        try:
            pt = shape(f["geometry"])
        except Exception:  # noqa: BLE001
            continue
        if flood.covers(pt) or flood.distance(pt) < 1e-9:
            p = f.get("properties") or {}
            ftype = p.get("amenity") or p.get("facility_type") or "unknown"
            hit.append({"name": p.get("name") or ftype, "type": ftype})
    by_type = Counter(h["type"] for h in hit)
    return {
        "status": "ok",
        "source": "OpenStreetMap (facilities_osm.geojson)",
        "category_attribute": "amenity",
        "total_in_dataset": len(points),
        "total_by_type": dict(sorted(total_by_type.items(), key=lambda kv: -kv[1])),
        "affected_count": len(hit),
        "affected": hit,
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
    }


def _buildings_impact(flood) -> dict:
    gdf, reason = _read_gpkg_layer("multipolygons")
    if gdf is None:
        return {"status": "unavailable", "reason": reason}
    if "building" not in gdf.columns:
        return {"status": "unavailable", "reason": "no `building` attribute in multipolygons layer"}

    buildings = gdf[gdf["building"].notna()].copy()
    total = int(len(buildings))
    # dataset/layer present -> this is an "ok" result even when total or affected is 0
    hit_mask = buildings.geometry.intersects(flood) if total else []
    affected = buildings[hit_mask] if total else buildings.iloc[0:0]
    flooded_footprint_km2 = 0.0
    if len(affected):
        try:
            inter = affected.geometry.intersection(flood)
            if inter.crs is None:
                inter = inter.set_crs(WGS84)
            flooded_footprint_km2 = float(inter.to_crs(METRIC).area.sum()) / 1_000_000.0
        except Exception:  # noqa: BLE001
            flooded_footprint_km2 = 0.0
    return {
        "status": "ok",
        "source": "OpenStreetMap (osm_ujjani.gpkg, layer multipolygons, building IS NOT NULL)",
        "crs": WGS84,
        "footprint_crs": METRIC,
        "total_in_dataset": total,
        "affected_count": int(len(affected)),
        "approx_flooded_footprint_km2": round(flooded_footprint_km2, 5),
    }


def _population_impact(flood) -> dict:
    """Estimated residential population within the modelled flood extent.

    WorldPop 2020 constrained (UN-adjusted) counts raster, native EPSG:4326 grid.
    Method: mask the raster with the flood polygon, cell-centre inclusion
    (all_touched=False), NoData excluded, sum persons-per-pixel. The raster is
    NOT reprojected or resampled — only the polygon is transformed if needed.
    This is DERIVED IMPACT (an estimate of modelled exposure), never observed
    or surveyed population. No fabricated fallback: any failure -> "unavailable".
    """
    if not POPULATION.exists():
        return {"status": "unavailable",
                "reason": f"population raster not found ({POPULATION.name}); exposure not computed"}
    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask as rio_mask
        from shapely.geometry import mapping
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"raster stack unavailable: {exc}"}

    meta = {}
    if POPULATION_META.exists():
        try:
            meta = json.loads(POPULATION_META.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}

    def _meta_block(extra: dict) -> dict:
        res_arc = meta.get("native_resolution_arcsec")
        block = {
            "dataset": meta.get("dataset",
                                "WorldPop Global 2000-2020 Constrained, India 2020, UN-adjusted"),
            "product": meta.get("product"),
            "year": meta.get("year", 2020),
            "resolution": (f"{res_arc} arc-seconds (~100 m)" if res_arc else "~100 m"),
            "units": "estimated persons per pixel",
            "method": "flood-polygon raster mask, cell-centre inclusion (all_touched=False)",
            "nodata_handling": "NoData / non-finite cells excluded from the sum (contribute nothing)",
            "doi": meta.get("doi", "10.5258/SOTON/WP00684"),
            "source_url": meta.get("source_url"),
            "license": meta.get("license", "CC-BY-4.0"),
            "classification": "DERIVED IMPACT (estimate) — modelled exposure to the modelled "
                              "inundation extent; not people displaced / affected / casualties / surveyed",
            "temporal_caveat": "2020 population estimate overlaid on a modelled flood extent; not the "
                               "population present at the time of any specific past or future event",
            "validation_status": "NOT PERFORMED",
        }
        block.update(extra)
        return block

    try:
        with rasterio.open(POPULATION) as ds:
            if ds.crs is None:
                return {"status": "unavailable", "reason": "population raster has no CRS"}
            crs_str = str(ds.crs)
            geom = flood
            if crs_str.upper() not in ("EPSG:4326", "WGS84"):
                try:
                    import pyproj
                    from shapely.ops import transform as shp_transform
                    project = pyproj.Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform
                    geom = shp_transform(project, flood)
                except Exception as exc:  # noqa: BLE001
                    return {"status": "unavailable",
                            "reason": f"cannot align flood polygon to raster CRS {crs_str}: {exc}"}
            try:
                band, _ = rio_mask(ds, [mapping(geom)], crop=True, all_touched=False, filled=False)
            except ValueError as exc:
                if "do not overlap" in str(exc).lower():
                    return _meta_block({"status": "ok", "population_exposed_estimate": 0,
                                        "crs": crs_str, "valid_cells": 0,
                                        "note": "modelled flood extent does not overlap the population raster"})
                raise
            arr = np.ma.masked_invalid(band[0])
            if ds.nodata is not None:
                arr = np.ma.masked_equal(arr, ds.nodata)
            valid_cells = int(arr.count())
            total = 0.0 if valid_cells == 0 else float(arr.sum())
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"population overlay failed: {exc}"}

    if total < 0 or not (total == total):  # negative or NaN
        return {"status": "unavailable",
                "reason": "population overlay produced an invalid (negative / NaN) sum"}

    return _meta_block({
        "status": "ok",
        "population_exposed_estimate": int(round(total)),
        "crs": crs_str,
        "valid_cells": valid_cells,
        "note": ("modelled flood extent did not intersect any valid population cells"
                 if valid_cells == 0 or round(total) == 0 else None),
    })


def _settlements_impact(flood) -> dict:
    gdf, reason = _read_gpkg_layer("points")
    if gdf is None:
        return {"status": "unavailable", "reason": reason}
    if "place" not in gdf.columns:
        return {"status": "unavailable", "reason": "no `place` attribute in points layer"}

    places = gdf[gdf["place"].notna()].copy()
    total = int(len(places))
    if total:
        hit_mask = places.geometry.apply(lambda g: flood.covers(g) or flood.distance(g) < 1e-9)
        affected = places[hit_mask]
    else:
        affected = places.iloc[0:0]
    names = [{"name": (r.get("name") or "unnamed"), "place": r.get("place")}
             for _, r in affected.iterrows()]
    return {
        "status": "ok",
        "source": "OpenStreetMap (osm_ujjani.gpkg, layer points, place IS NOT NULL)",
        "crs": WGS84,
        "geometry_note": "OSM place nodes (settlement centres), not census/administrative boundaries; "
                         "a settlement counts as affected only when its representative point lies in the extent",
        "total_in_dataset": total,
        "affected_count": int(len(affected)),
        "affected": names,
    }
