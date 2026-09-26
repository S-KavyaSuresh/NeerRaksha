"""OBSERVATION branch API — Sentinel-1 SAR water/flood evidence via Google Earth Engine.

    GET  /api/remote-sensing/status                     -> is a live GEE observation possible?
    POST /api/remote-sensing/sentinel1/observe          -> start an observation job (obs-<id>)
    GET  /api/remote-sensing/jobs/{job_id}              -> job status + result metadata
    GET  /api/remote-sensing/jobs/{job_id}/result       -> full observation result
    GET  /api/remote-sensing/jobs/{job_id}/layers/{name}-> water_evidence GeoJSON / GeoTIFF
    GET  /api/remote-sensing/jobs/{job_id}/compare/{scenario_job_id}
                                                        -> spatial agreement indicator vs a Delft3D run

Satellite water/flood evidence is an OBSERVATION, never validated hydraulic output.
No credentials are ever accepted or returned by this API.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.simulation import observation_jobs
from remote_sensing.gee_client import gee_status
from remote_sensing.observation import UJJANI_AOI, compare_with_model

router = APIRouter(prefix="/api/remote-sensing", tags=["remote-sensing"])

_LAYERS = {"water_evidence": ("water_evidence.geojson", "water_evidence.tif")}


class ObserveRequest(BaseModel):
    observation_start: str = Field(..., description="YYYY-MM-DD (inclusive)")
    observation_end: str = Field(..., description="YYYY-MM-DD (exclusive)")
    reference_start: str | None = Field(None, description="optional baseline window start")
    reference_end: str | None = None
    polarization: str = "VV"
    threshold_db: float | None = Field(None, description="explicit, scene-dependent; default -3 dB change / -17 dB single")
    orbit_pass: str | None = Field(None, description="ASCENDING | DESCENDING | null (any)")
    scale_m: int = 30
    aoi: list[float] | None = Field(None, description="[w,s,e,n] EPSG:4326; defaults to the Ujjani AOI")


def _public(rec: dict) -> dict:
    r = rec.get("result") or {}
    return {
        "id": rec["id"], "status": rec["status"], "message": rec["message"],
        "progress": rec["progress"],
        "classification": r.get("classification"),
        "method": r.get("method"), "threshold_db": r.get("threshold_db"),
        "polarization": (r.get("source") or {}).get("polarization"),
        "collection": (r.get("source") or {}).get("collection"),
        "observation_period": r.get("observation_period"),
        "reference_period": r.get("reference_period"),
        "aoi_bbox_wgs84": r.get("aoi_bbox_wgs84"),
        "acquisitions": r.get("acquisitions"),
        "water_evidence_area_km2": r.get("water_evidence_area_km2"),
        "water_evidence_cells": r.get("water_evidence_cells"),
        "reason": r.get("reason"),
        "not_validated": r.get("not_validated", True),
        "created_at": rec["created_at"], "updated_at": rec["updated_at"],
    }


def _require(job_id: str) -> dict:
    rec = observation_jobs.get(job_id)
    if not rec:
        raise HTTPException(404, detail={"code": "OBSERVATION_NOT_FOUND", "message": "Unknown observation id."})
    return rec


@router.get("/status")
def status():
    s = gee_status()
    return {
        "observation_branch": "Sentinel-1 SAR water/flood evidence (Google Earth Engine)",
        "gee_available": s["available"],
        "reason": s["reason"],
        "ee_installed": s["ee_installed"],
        "ee_version": s["ee_version"],
        "project_configured": s["project_configured"],
        "default_aoi_bbox_wgs84": list(UJJANI_AOI),
        "note": "When gee_available is false, /observe still returns a truthful 'unavailable' "
                "result — it never fabricates satellite data.",
    }


@router.post("/sentinel1/observe")
def observe(body: ObserveRequest):
    payload = body.model_dump()
    if payload.get("aoi") is not None:
        payload["aoi"] = tuple(payload["aoi"])
    return _public(observation_jobs.create(payload))


@router.get("/jobs/{job_id}")
def job(job_id: str):
    return _public(_require(job_id))


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    rec = _require(job_id)
    if rec["result"] is None:
        raise HTTPException(409, detail={"code": "OBSERVATION_NOT_READY", "message": f"Observation is {rec['status']}."})
    return rec["result"]


@router.get("/jobs/{job_id}/layers/{name}")
def job_layer(job_id: str, name: str):
    _require(job_id)
    if name not in _LAYERS:
        raise HTTPException(400, detail={"code": "BAD_LAYER", "message": f"layer must be one of {list(_LAYERS)}"})
    d = observation_jobs.RESULTS_ROOT / job_id
    for fname in _LAYERS[name]:
        p = d / fname
        if p.exists():
            if p.suffix == ".geojson":
                return json.loads(p.read_text(encoding="utf-8"))
            return FileResponse(p, media_type="image/tiff", filename=p.name)
    raise HTTPException(404, detail={"code": "LAYER_UNAVAILABLE",
                                    "message": f"'{name}' not produced (observation unavailable/failed).",
                                    "status": "unavailable"})


@router.get("/jobs/{job_id}/compare/{scenario_job_id}")
def compare(job_id: str, scenario_job_id: str):
    _require(job_id)
    from app.simulation import scenario_jobs

    scn = scenario_jobs.results(scenario_job_id) or {}
    rd = scn.get("results_dir")
    if not rd:
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND",
                                         "message": "No completed scenario result for that id."})
    fe = Path(rd) / "flood_extent.geojson"
    out = compare_with_model(observation_jobs.RESULTS_ROOT / job_id, fe)
    out["model_scenario_id"] = scenario_job_id
    out["model_flood_extent_source"] = str(fe)
    return out
