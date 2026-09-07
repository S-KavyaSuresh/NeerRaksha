"""Simulation lifecycle API — database-independent.

    POST   /api/simulations
    GET    /api/simulations/{id}
    GET    /api/simulations/{id}/summary
    GET    /api/simulations/{id}/timeline
    GET    /api/simulations/{id}/timeline/{minute}
    GET    /api/simulations/{id}/results/{layer}
    POST   /api/simulations/{id}/cancel
    GET    /api/simulations/{id}/validation   (satellite comparison — honest stub)

Job state is in memory; results are files on disk. No PostgreSQL required so the
vertical slice works even when the database is unavailable.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.simulation import jobs

# Job ids are NOT UUIDs ("sim-..."). The legacy database-backed sample-simulation
# routes in app.api.routes are pinned to the {uuid} path convertor, so the two
# route sets never collide.

router = APIRouter(prefix="/api/simulations", tags=["simulations"])

VALID_LAYERS = ("flood_extent", "max_depth", "max_velocity", "arrival_time")


class SimulationCreate(BaseModel):
    scenario: dict[str, Any] = Field(default_factory=dict)
    engine: str = "approximate"  # approximate | delft3d | sph


def _public(record: dict) -> dict:
    return {
        "id": record["id"],
        "status": record["status"],
        "progress": record["progress"],
        "message": record["message"],
        "engine": record["engine"],
        "resolved_engine": record.get("resolved_engine", record["engine"]),
        "engine_label": record.get("engine_label"),
        "data_class": record.get("data_class"),
        "validated_hydraulic_output": record.get("validated_hydraulic_output", False),
        "disclaimer": record.get("disclaimer"),
        "provenance": record.get("provenance"),
        "fallback_used": record.get("fallback_used", False),
        "available_frames": record.get("available_frames", []),
        "runtime_seconds": record.get("runtime_seconds"),
        "mesh": record.get("mesh"),
        "command": record.get("command"),
        "map_frames": record.get("map_frames"),
        "max_depth_m": record.get("max_depth_m"),
        "max_velocity_mps": record.get("max_velocity_mps"),
        "particle_count": record.get("particle_count"),
        "timesteps": record.get("timesteps"),
        "max_density": record.get("max_density"),
        "min_density": record.get("min_density"),
        "max_displacement_m": record.get("max_displacement_m"),
        "workdir": record.get("workdir"),
        "error": record.get("error"),
        "scenario": record.get("scenario"),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def _require(job_id: str) -> dict:
    record = jobs.get(job_id)
    if not record:
        raise HTTPException(404, detail={"code": "SIMULATION_NOT_FOUND", "message": "Unknown simulation id."})
    return record


@router.post("")
def create_simulation(body: SimulationCreate):
    record = jobs.create(body.scenario, body.engine)
    return _public(record)


@router.get("/{job_id}")
def get_simulation(job_id: str):
    return _public(_require(job_id))


@router.post("/{job_id}/cancel")
def cancel_simulation(job_id: str):
    _require(job_id)
    return _public(jobs.cancel(job_id))


@router.get("/{job_id}/summary")
def get_summary(job_id: str):
    record = _require(job_id)
    if record["status"] != "completed":
        raise HTTPException(409, detail={"code": "SIMULATION_NOT_READY", "message": f"Simulation is {record['status']}."})
    summary = jobs.load_summary(job_id)
    if summary is None:
        raise HTTPException(404, detail={"code": "SUMMARY_NOT_FOUND", "message": "No summary produced."})
    summary = dict(summary)
    summary.setdefault("data_class", record.get("data_class", "MODEL OUTPUT"))
    summary.setdefault("engine_label", record.get("engine_label"))
    summary["population_exposed"] = None
    summary["population_exposed_status"] = "unavailable — no population dataset wired for this study area"
    return summary


@router.get("/{job_id}/timeline")
def get_timeline(job_id: str):
    record = _require(job_id)
    summary = jobs.load_summary(job_id) or {}
    return {
        "simulation_id": job_id,
        "status": record["status"],
        "data_class": record.get("data_class", "MODEL OUTPUT"),
        "available_frames": record.get("available_frames", summary.get("available_frames", [])),
        "values": summary.get("timeline", []),
    }


@router.get("/{job_id}/timeline/{minute}")
def get_frame(job_id: str, minute: int):
    _require(job_id)
    frame = jobs.load_frame(job_id, minute)
    if frame is None:
        raise HTTPException(404, detail={"code": "FRAME_NOT_FOUND", "message": f"No flood frame at minute {minute}."})
    return frame


@router.get("/{job_id}/results/{layer}")
def get_result_layer(job_id: str, layer: str):
    _require(job_id)
    if layer not in VALID_LAYERS:
        raise HTTPException(400, detail={"code": "BAD_LAYER", "message": f"layer must be one of {VALID_LAYERS}."})
    path = jobs.layer_file(job_id, layer)
    if path is None:
        raise HTTPException(404, detail={
            "code": "LAYER_UNAVAILABLE",
            "message": f"'{layer}' was not produced by this engine run.",
            "status": "unavailable",
        })
    if path.suffix == ".geojson":
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    return FileResponse(path, media_type="image/tiff", filename=path.name)


@router.get("/{job_id}/validation")
def get_validation(job_id: str):
    """Satellite (Sentinel-1 / GEE) comparison — honest 'unavailable' until wired."""
    _require(job_id)
    return {
        "simulation_id": job_id,
        "observation_source": "Sentinel-1 via Google Earth Engine",
        "status": "unavailable",
        "message": "Satellite validation unavailable — no GEE credentials configured. "
                   "No accuracy percentage is fabricated.",
        "agreement": None,
        "observed_flood_extent": None,
    }
