"""Phase 4 generalized Ujjani dam-break scenario API.

    POST /api/scenarios/run              -> start a scenario run (returns scn-<id>)
    GET  /api/scenarios/presets          -> the DEMO/ASSUMED scenario variants
    GET  /api/scenarios/{id}             -> job status + common result
    GET  /api/scenarios/{id}/results     -> the common result (depth/velocity/arrival/extent + metadata)
    GET  /api/scenarios/{id}/hydrograph  -> the breach discharge hydrograph (formulation + series)

Own async job runner. The legacy database `GET /api/scenarios/{scenario_id}` is
pinned to the {uuid} path convertor, so it does not collide with these scn-<id>
routes. POST /api/simulations and the Phase 1-3 engine paths are untouched.
No silent fallback: a failed engine reports its own failure.
"""
from __future__ import annotations

from typing import Any

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.simulation import scenario_jobs
from simulation import scenario as scen

_LAYERS = {
    "flood_extent": "flood_extent.geojson",
    "max_depth": ("max_depth.tif", "max_depth_local.tif"),
    "max_velocity": ("max_velocity.tif", "max_velocity_local.tif"),
    "arrival_time": ("arrival_time.tif", "arrival_time_local.tif"),
}

router = APIRouter(prefix="/api/scenarios", tags=["phase4-scenarios"])


class ScenarioRun(BaseModel):
    engine: str = "delft3d"                       # delft3d | sph | approximate
    preset: str = "custom"
    params: dict[str, Any] = Field(default_factory=dict)   # overrides for the scenario schema


def _public(rec: dict) -> dict:
    r = rec.get("result") or {}
    return {
        "id": rec["id"],
        "status": rec["status"],
        "progress": rec["progress"],
        "message": rec["message"],
        "engine": rec["engine"],
        "preset": rec["preset"],
        "validation_status": rec["validation_status"],
        "run_class": r.get("run_class", "MODEL DEMONSTRATION / SCENARIO SIMULATION"),
        "data_class": rec["data_class"],
        "resolved_engine": r.get("engine"),
        "engine_label": r.get("engine_label"),
        "dam_location": r.get("dam_location"),
        "reservoir_level_m": r.get("reservoir_level_m"),
        "breach": r.get("breach"),
        "hydrograph_peak_m3s": (r.get("hydrograph") or {}).get("peak_discharge_m3s"),
        "available_frames": r.get("available_frames", []),
        "max_depth_m": r.get("max_depth_m"),
        "max_velocity_mps": r.get("max_velocity_mps"),
        "mesh": r.get("mesh"),
        "particle_count": r.get("particle_count"),
        "timesteps": r.get("timesteps"),
        "sph_status": r.get("sph_status"),
        "release_representation": r.get("release_representation"),
        "runtime_seconds": r.get("runtime_seconds"),
        "outputs": r.get("outputs", []),
        "assumptions": r.get("assumptions", []),
        "limitations": r.get("limitations", []),
        "error": rec.get("error"),
        "created_at": rec["created_at"],
        "updated_at": rec["updated_at"],
    }


def _require(job_id: str) -> dict:
    rec = scenario_jobs.get(job_id)
    if not rec:
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND", "message": "Unknown scenario id."})
    return rec


@router.get("/presets")
def presets():
    return {
        "presets": scen.SCENARIO_PRESETS,
        "note": "Numeric defaults are DEMO / ASSUMED — they are scenario assumptions, "
                "NOT observed historical Ujjani events. Reservoir level / head have no "
                "authoritative source and are labelled ASSUMPTION / DEMO.",
        "dam_location": {"lat": scen.DAM_LAT, "lon": scen.DAM_LON,
                         "class": "REAL DATA (project-supplied target coordinate)"},
        "terrain": {"dem": scen.UJJANI_DEM.name, "crs": scen.MODEL_CRS, "class": "REAL DATA"},
    }


@router.post("/run")
def run_scenario(body: ScenarioRun):
    payload = dict(body.params or {})
    payload["engine"] = body.engine
    payload["preset"] = body.preset
    return _public(scenario_jobs.create(payload))


@router.get("/{job_id}")
def get_scenario(job_id: str):
    return _public(_require(job_id))


@router.get("/{job_id}/results")
def get_results(job_id: str):
    rec = _require(job_id)
    if rec["status"] == "failed":
        raise HTTPException(409, detail={"code": "SCENARIO_FAILED", "message": rec["message"],
                                         "error": rec.get("error")})
    data = scenario_jobs.results(job_id)
    if data is None:
        raise HTTPException(409, detail={"code": "SCENARIO_NOT_READY", "message": f"Scenario is {rec['status']}."})
    return data


@router.get("/{job_id}/hydrograph")
def get_hydrograph(job_id: str):
    _require(job_id)
    hg = scenario_jobs.hydrograph(job_id)
    if hg is None:
        raise HTTPException(409, detail={"code": "HYDROGRAPH_NOT_READY", "message": "Hydrograph not available yet."})
    return hg


def _results_dir(job_id: str) -> Path:
    r = scenario_jobs.results(job_id) or {}
    d = r.get("results_dir")
    if not d:
        raise HTTPException(409, detail={"code": "SCENARIO_NOT_READY", "message": "No results yet."})
    return Path(d)


@router.get("/{job_id}/timeline/{minute}")
def get_frame(job_id: str, minute: int):
    _require(job_id)
    frame = _results_dir(job_id) / "timeline" / f"t{int(minute):03d}.geojson"
    if not frame.exists():
        raise HTTPException(404, detail={"code": "FRAME_NOT_FOUND", "message": f"No frame at minute {minute}."})
    return json.loads(frame.read_text(encoding="utf-8"))


@router.get("/{job_id}/layers/{layer}")
def get_layer(job_id: str, layer: str):
    _require(job_id)
    if layer not in _LAYERS:
        raise HTTPException(400, detail={"code": "BAD_LAYER", "message": f"layer must be one of {list(_LAYERS)}"})
    d = _results_dir(job_id)
    names = _LAYERS[layer]
    for name in ((names,) if isinstance(names, str) else names):
        p = d / name
        if p.exists():
            if p.suffix == ".geojson":
                return json.loads(p.read_text(encoding="utf-8"))
            return FileResponse(p, media_type="image/tiff", filename=p.name)
    raise HTTPException(404, detail={"code": "LAYER_UNAVAILABLE",
                                    "message": f"'{layer}' not produced by this engine run.", "status": "unavailable"})


@router.get("/{job_id}/impact")
def get_impact(job_id: str):
    _require(job_id)
    d = _results_dir(job_id)
    fe = d / "flood_extent.geojson"
    if not fe.exists():
        raise HTTPException(404, detail={"code": "NO_FLOOD_EXTENT", "message": "flood_extent.geojson not produced."})
    from simulation import impact
    r = scenario_jobs.results(job_id) or {}
    return impact.analyse(fe, d, summary_area_km2=(r.get("summary") or {}).get("flooded_area_km2"))


@router.get("/{job_id}/export/{fmt}")
def get_export(job_id: str, fmt: str):
    _require(job_id)
    from simulation import gis_export
    if fmt.lower() not in gis_export.VALID_FORMATS:
        raise HTTPException(400, detail={"code": "BAD_FORMAT", "message": f"format must be one of {gis_export.VALID_FORMATS}"})
    d = _results_dir(job_id)
    fe = d / "flood_extent.geojson"
    if not fe.exists():
        raise HTTPException(404, detail={"code": "NO_FLOOD_EXTENT", "message": "flood_extent.geojson not produced."})
    try:
        path = gis_export.export(fe, d, fmt)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail={"code": "EXPORT_FAILED", "message": str(exc)})
    return FileResponse(path, media_type=gis_export.media_type(fmt), filename=path.name)


@router.get("/{job_id}/particles")
def get_particles(job_id: str):
    _require(job_id)
    d = _results_dir(job_id)
    pf = d / "particle_frames.json"
    if pf.exists():
        return json.loads(pf.read_text(encoding="utf-8"))
    raise HTTPException(404, detail={"code": "NO_PARTICLES",
                                    "message": "particle_frames.json not available (SPH engine only)."})
