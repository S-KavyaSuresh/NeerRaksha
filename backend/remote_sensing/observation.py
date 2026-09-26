"""OBSERVATION branch orchestrator — Sentinel-1 water/flood evidence for Ujjani.

    run_observation(...)  -> {status, ...}   (calls Google Earth Engine)
    process_arrays(...)   -> writes GeoTIFF + GeoJSON + metadata   (no GEE; unit tested)
    compare_with_model(...) -> spatial agreement indicator vs a Delft3D flood extent

Status contract (mirrors the MODEL branch's impact layers):
    status "ok"           -> a real Sentinel-1 observation was retrieved and processed
    status "unavailable"  -> GEE not configured / no scenes in window (explicit reason)
    status "error"        -> processing failed (explicit reason)
Never a fabricated satellite result.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from simulation import config
from . import sentinel1
from .gee_client import GEEClient, GEEUnavailable, gee_status

# --- Ujjani AOI ------------------------------------------------------------- #
# Reuses the authoritative Ujjani spatial context (the cropped DEM extent
# 75.00-75.18 E / 18.00-18.12 N) plus a small margin, matching the WorldPop
# population clip box. Override with NEERRAKSHA_UJJANI_AOI="w,s,e,n".
_DEFAULT_AOI = (74.98, 17.98, 75.20, 18.14)


def _aoi_from_env() -> tuple[float, float, float, float]:
    raw = os.environ.get("NEERRAKSHA_UJJANI_AOI", "").strip()
    if raw:
        parts = [float(x) for x in raw.split(",")]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]
    return _DEFAULT_AOI


UJJANI_AOI = _aoi_from_env()
OBS_RESULTS = config.ROOT / "results" / "ujjani_observation"
CLASSIFICATION = "SATELLITE OBSERVATION — WATER/FLOOD EVIDENCE"


def _skeleton(observation_start, observation_end, reference_start, reference_end,
              polarization, threshold_db, method, orbit_pass, scale_m, aoi) -> dict:
    return {
        "classification": CLASSIFICATION,
        "not_validated": True,
        "validated_hydraulic_output": False,
        "is_model_output": False,
        "note": "Satellite-derived water/flood evidence. NOT a hydraulic model result, NOT ground "
                "truth, NOT confirmed inundation. Sentinel-1 acquisitions are discrete passes "
                "(near-real-time / event-window), not a live flood sensor.",
        "source": {
            "provider": "Google Earth Engine",
            "sensor": "Sentinel-1 C-band SAR",
            "collection": sentinel1.S1_COLLECTION,
            "instrument_mode": sentinel1.S1_INSTRUMENT_MODE,
            "polarization": polarization,
            "backscatter_units": sentinel1.S1_UNITS,
            "native_pixel_spacing_m": sentinel1.S1_PIXEL_SPACING_M,
            "revisit_days": sentinel1.S1_REVISIT_DAYS,
            "attribution": sentinel1.S1_ATTRIBUTION,
        },
        "method": method,
        "threshold_db": threshold_db,
        "orbit_pass": (orbit_pass or "ANY"),
        "processing_scale_m": scale_m,
        "aoi_bbox_wgs84": list(aoi),
        "aoi_provenance": "Ujjani cropped-DEM extent + margin (EPSG:4326); "
                          "override via NEERRAKSHA_UJJANI_AOI",
        "crs": "EPSG:4326",
        "observation_period": {"start": str(observation_start), "end": str(observation_end)},
        "reference_period": ({"start": str(reference_start), "end": str(reference_end)}
                             if reference_start and reference_end else None),
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def process_arrays(post_db, transform, crs, out_dir,
                   pre_db=None, threshold_db=None, nodata=None,
                   meta: dict | None = None) -> dict:
    """Apply the SAR threshold, vectorise, compute stats, write outputs.

    This is the offline-testable core: it takes already-downloaded arrays.
    """
    import numpy as np
    import rasterio

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if pre_db is not None:
        thr = sentinel1.DEFAULT_CHANGE_THRESHOLD_DB if threshold_db is None else float(threshold_db)
        mask = sentinel1.water_mask_change(pre_db, post_db, thr, nodata=nodata)
        method = sentinel1.METHOD_CHANGE
    else:
        thr = sentinel1.DEFAULT_SINGLE_THRESHOLD_DB if threshold_db is None else float(threshold_db)
        mask = sentinel1.water_mask_single(post_db, thr, nodata=nodata)
        method = sentinel1.METHOD_SINGLE

    mask = np.asarray(mask, dtype=bool)
    stats = sentinel1.observation_statistics(mask, transform, crs)
    features = sentinel1.mask_to_features(mask, transform, crs)

    tif = out_dir / "water_evidence.tif"
    with rasterio.open(tif, "w", driver="GTiff", height=mask.shape[0], width=mask.shape[1],
                       count=1, dtype="uint8", crs=crs, transform=transform, nodata=0,
                       compress="deflate") as dst:
        dst.write(mask.astype("uint8"), 1)

    fc = {"type": "FeatureCollection", "features": features}
    geojson = out_dir / "water_evidence.geojson"
    geojson.write_text(json.dumps(fc), encoding="utf-8")

    result = {
        "status": "ok",
        "method": method,
        "threshold_db": thr,
        "crs": crs,
        **stats,
        "outputs": {"raster": tif.name, "footprint": geojson.name, "metadata": "observation.json"},
    }
    if meta:
        merged = {**meta, **result, "method": method, "threshold_db": thr}
        merged["source"] = meta.get("source", result.get("source"))
        result = merged
    (out_dir / "observation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run_observation(observation_start: str, observation_end: str,
                    reference_start: str | None = None, reference_end: str | None = None,
                    polarization: str = "VV", threshold_db: float | None = None,
                    orbit_pass: str | None = None, scale_m: int = 30,
                    aoi: tuple | None = None, out_dir: str | Path | None = None) -> dict:
    aoi = tuple(aoi) if aoi else UJJANI_AOI
    change = bool(reference_start and reference_end)
    method = sentinel1.METHOD_CHANGE if change else sentinel1.METHOD_SINGLE
    if threshold_db is None:
        threshold_db = (sentinel1.DEFAULT_CHANGE_THRESHOLD_DB if change
                        else sentinel1.DEFAULT_SINGLE_THRESHOLD_DB)
    out_dir = Path(out_dir) if out_dir else (OBS_RESULTS / "_adhoc")

    meta = _skeleton(observation_start, observation_end, reference_start, reference_end,
                     polarization, threshold_db, method, orbit_pass, scale_m, aoi)

    status = gee_status()
    if not status["available"]:
        return {**meta, "status": "unavailable", "reason": status["reason"]}

    try:
        client = GEEClient().initialize()
        post_img, post_info = client.s1_median(aoi, (observation_start, observation_end),
                                               polarization, orbit_pass, speckle_radius_m=scale_m)
        post_db, transform, crs = client.download_band(post_img, aoi, polarization, scale_m)
        pre_db = None
        pre_info = None
        if change:
            pre_img, pre_info = client.s1_median(aoi, (reference_start, reference_end),
                                                 polarization, orbit_pass, speckle_radius_m=scale_m)
            pre_db, _, _ = client.download_band(pre_img, aoi, polarization, scale_m)
    except GEEUnavailable as exc:
        return {**meta, "status": "unavailable", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {**meta, "status": "error", "reason": f"Sentinel-1 retrieval failed: {exc}"}

    meta["acquisitions"] = {"observation": post_info,
                            "reference": pre_info if change else None}
    try:
        return process_arrays(post_db, transform, crs, out_dir, pre_db=pre_db,
                              threshold_db=threshold_db, meta=meta)
    except Exception as exc:  # noqa: BLE001
        return {**meta, "status": "error", "reason": f"evidence processing failed: {exc}"}


def compare_with_model(observation_dir: str | Path, model_flood_geojson: str | Path) -> dict:
    """Spatial agreement indicator between a satellite evidence footprint and a
    MODELLED Delft3D flood extent. NOT hydraulic validation."""
    observation_dir = Path(observation_dir)
    fc_path = observation_dir / "water_evidence.geojson"
    if not fc_path.exists():
        return {"status": "unavailable", "reason": "no satellite water/flood evidence footprint on disk"}
    if not Path(model_flood_geojson).exists():
        return {"status": "unavailable", "reason": "modelled flood extent not found"}
    features = json.loads(fc_path.read_text(encoding="utf-8")).get("features", [])
    return sentinel1.spatial_agreement(str(model_flood_geojson), features)
