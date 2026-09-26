"""Sentinel-1 SAR water/flood evidence — transparent threshold / change methods.

Pure array/geometry helpers, no Earth Engine import, so the algorithm is unit
tested offline with deterministic fixtures.

Method background (official: Earth Engine COPERNICUS/S1_GRD catalogue):
    * S1 GRD backscatter is delivered in decibels (10*log10 of calibrated sigma0),
      10 m pixels, IW mode over land, polarisations ['VV'] or ['VV','VH'].
    * Open, calm water is a near-specular reflector -> very low backscatter.
    * New inundation therefore shows up as (a) low absolute VV, or (b) a strong
      DECREASE in VV between a reference acquisition and the observation
      acquisition (change detection).

Caveats that the method cannot remove and that the UI/API must keep visible:
    * backscatter varies with land cover; wet soil / smooth tarmac / sand can
      also read low; wind-roughened water reads higher.
    * vegetation canopy can hide standing water (double-bounce raises VV).
    * permanent water bodies and temporary inundation are not separated here.
    * radar shadow / layover on slopes mimics low backscatter.
    * the dB threshold is scene dependent — it is exposed and configurable,
      never presented as universally correct.
"""
from __future__ import annotations

import numpy as np

S1_COLLECTION = "COPERNICUS/S1_GRD"
S1_INSTRUMENT_MODE = "IW"
S1_POLARIZATIONS = ("VV", "VH")
S1_UNITS = "decibels (10*log10 sigma0)"
S1_PIXEL_SPACING_M = 10
S1_REVISIT_DAYS = "6-12 (Sentinel-1A; nominal 6 with 1A+1B)"
S1_ATTRIBUTION = "Contains modified Copernicus Sentinel data. Use governed by the Copernicus Sentinel Data Terms and Conditions. Produced by European Union / ESA / Copernicus; accessed via Google Earth Engine."

# Defaults — explicit, configurable, not universal truth.
DEFAULT_CHANGE_THRESHOLD_DB = -3.0    # VV drop (post - pre) at/below this -> new-water evidence
DEFAULT_SINGLE_THRESHOLD_DB = -17.0   # absolute VV at/below this -> open-water evidence

METHOD_CHANGE = "sar_change_detection"
METHOD_SINGLE = "sar_low_backscatter_single_scene"


def _valid(arr: np.ndarray, nodata) -> np.ndarray:
    v = np.isfinite(arr)
    if nodata is not None:
        v &= arr != nodata
    return v


def water_mask_change(pre_db: np.ndarray, post_db: np.ndarray,
                      threshold_db: float = DEFAULT_CHANGE_THRESHOLD_DB,
                      nodata=None) -> np.ndarray:
    """Boolean water/flood-evidence mask from a pre/post VV(dB) decrease.

    True where BOTH acquisitions are valid AND (post - pre) <= threshold_db.
    NoData / non-finite pixels are never water.
    """
    pre_db = np.asarray(pre_db, dtype="float64")
    post_db = np.asarray(post_db, dtype="float64")
    if pre_db.shape != post_db.shape:
        raise ValueError(f"pre/post shape mismatch: {pre_db.shape} vs {post_db.shape}")
    valid = _valid(pre_db, nodata) & _valid(post_db, nodata)
    diff = np.where(valid, post_db - pre_db, np.nan)
    return valid & (diff <= float(threshold_db))


def water_mask_single(post_db: np.ndarray,
                      threshold_db: float = DEFAULT_SINGLE_THRESHOLD_DB,
                      nodata=None) -> np.ndarray:
    """Boolean water-evidence mask from a single acquisition's low VV(dB).

    True where the pixel is valid AND post_db <= threshold_db.
    """
    post_db = np.asarray(post_db, dtype="float64")
    valid = _valid(post_db, nodata)
    return valid & (post_db <= float(threshold_db))


def mask_to_features(mask: np.ndarray, transform, crs: str = "EPSG:4326") -> list[dict]:
    """Vectorise a boolean mask to GeoJSON polygon features (water == 1)."""
    from rasterio import features

    mask = np.asarray(mask, dtype=bool)
    out = []
    for geom, val in features.shapes(mask.astype("uint8"), mask=mask, transform=transform):
        if int(val) != 1:
            continue
        out.append({
            "type": "Feature",
            "properties": {"class": "water_flood_evidence",
                           "source": "Sentinel-1 SAR (Google Earth Engine)"},
            "geometry": geom,
        })
    return out


def observation_statistics(mask: np.ndarray, transform, crs: str = "EPSG:4326",
                           metric_crs: str = "EPSG:32643") -> dict:
    """Cell counts + evidence area (m2 -> km2) computed in a metric CRS."""
    import geopandas as gpd
    from shapely.geometry import shape
    from shapely.ops import unary_union

    mask = np.asarray(mask, dtype=bool)
    total_cells = int(mask.size)
    water_cells = int(mask.sum())
    feats = mask_to_features(mask, transform, crs)
    area_km2 = 0.0
    if feats:
        geom = unary_union([shape(f["geometry"]).buffer(0) for f in feats])
        gm = gpd.GeoSeries([geom], crs=crs).to_crs(metric_crs).iloc[0]
        area_km2 = float(gm.area) / 1_000_000.0
    return {
        "water_evidence_cells": water_cells,
        "grid_cells_total": total_cells,
        "water_evidence_fraction": (water_cells / total_cells) if total_cells else 0.0,
        "water_evidence_area_km2": round(area_km2, 5),
        "area_crs": metric_crs,
        "polygon_count": len(feats),
    }


def spatial_agreement(model_geojson: str, evidence_features: list[dict],
                      metric_crs: str = "EPSG:32643") -> dict:
    """Spatial-consistency check between a MODELLED inundation footprint and
    SATELLITE water/flood evidence. NOT a validation score.
    """
    import json
    from pathlib import Path

    import geopandas as gpd
    from shapely.geometry import shape
    from shapely.ops import unary_union

    md = json.loads(Path(model_geojson).read_text(encoding="utf-8"))
    model_polys = [shape(f["geometry"]).buffer(0) for f in md.get("features", [])
                   if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")]
    if not model_polys:
        return {"status": "unavailable", "reason": "modelled flood extent has no polygon geometry"}
    if not evidence_features:
        return {"status": "unavailable", "reason": "no satellite water/flood evidence polygons to compare"}

    model_wgs = unary_union(model_polys)
    ev_wgs = unary_union([shape(f["geometry"]).buffer(0) for f in evidence_features])
    m = gpd.GeoSeries([model_wgs], crs="EPSG:4326").to_crs(metric_crs).iloc[0]
    e = gpd.GeoSeries([ev_wgs], crs="EPSG:4326").to_crs(metric_crs).iloc[0]

    inter = m.intersection(e).area
    union = m.union(e).area
    km2 = lambda a: round(a / 1_000_000.0, 5)
    return {
        "status": "ok",
        "indicator": "spatial_agreement_indicator",
        "disclaimer": "This is a spatial consistency check between a modelled inundation footprint and "
                      "satellite-derived water/flood evidence. It is NOT, by itself, formal hydraulic "
                      "model validation and IoU here is NOT a validation accuracy.",
        "intersection_area_km2": km2(inter),
        "model_only_area_km2": km2(m.area - inter),
        "satellite_only_area_km2": km2(e.area - inter),
        "model_area_km2": km2(m.area),
        "satellite_evidence_area_km2": km2(e.area),
        "iou": round(inter / union, 4) if union > 0 else 0.0,
        "area_crs": metric_crs,
    }
