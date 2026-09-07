"""Lightweight background simulation jobs.

A ``POST /api/simulations`` returns immediately with an id; a daemon thread runs
the engine and updates progress. State lives in memory — fine for a single-process
demo. Results themselves are files on disk, so they survive a restart even though
job metadata does not.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import sys

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from simulation import approximate_engine, config  # noqa: E402
from simulation import delft3d_engine, sph_engine  # noqa: E402

STATUSES = ("queued", "running", "completed", "failed", "cancelled")

_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}

_ENGINES: dict[str, Callable[..., dict]] = {
    "approximate": approximate_engine.run,
    "delft3d": delft3d_engine.run,
    "sph": sph_engine.run,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_record(scenario: dict, engine: str) -> dict:
    return {
        "id": "sim-" + uuid.uuid4().hex[:16],
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "engine": engine,
        "resolved_engine": engine,
        "engine_label": None,
        "data_class": None,
        "validated_hydraulic_output": False,
        "disclaimer": None,
        "provenance": None,
        "scenario": scenario,
        "error": None,
        "results_dir": None,
        "available_frames": [],
        "summary": None,
        "fallback_used": False,
        "runtime_seconds": None,
        "mesh": None,
        "command": None,
        "map_frames": None,
        "max_depth_m": None,
        "max_velocity_mps": None,
        "particle_count": None,
        "timesteps": None,
        "max_density": None,
        "min_density": None,
        "max_displacement_m": None,
        "workdir": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def create(scenario: dict | None, engine: str = "approximate") -> dict:
    engine = (engine or "approximate").lower()
    if engine not in _ENGINES:
        engine = "approximate"
    record = _new_record(scenario or {}, engine)
    with _LOCK:
        _JOBS[record["id"]] = record
    thread = threading.Thread(target=_run, args=(record["id"],), daemon=True)
    thread.start()
    return dict(record)


def get(job_id: str) -> dict | None:
    with _LOCK:
        record = _JOBS.get(job_id)
        return dict(record) if record else None


def cancel(job_id: str) -> dict | None:
    with _LOCK:
        record = _JOBS.get(job_id)
        if record and record["status"] in ("queued", "running"):
            record["status"] = "cancelled"
            record["message"] = "Cancelled by user"
            record["updated_at"] = _now()
        return dict(record) if record else None


def _update(job_id: str, **fields: Any) -> None:
    with _LOCK:
        record = _JOBS.get(job_id)
        if not record:
            return
        record.update(fields)
        record["updated_at"] = _now()


def _cancelled(job_id: str) -> bool:
    with _LOCK:
        record = _JOBS.get(job_id)
        return bool(record and record["status"] == "cancelled")


def _run(job_id: str) -> None:
    record = get(job_id)
    if not record:
        return
    scenario = record["scenario"]
    engine_name = record["engine"]
    engine_fn = _ENGINES[engine_name]

    _update(job_id, status="running", progress=2, message="Starting engine")

    def progress(pct: float, msg: str = "") -> None:
        if _cancelled(job_id):
            raise _Cancelled()
        _update(job_id, progress=max(2, min(99, int(pct))), message=msg or record["message"])

    try:
        result = engine_fn(scenario, progress=progress)
        fallback_used = False

        if not result.get("ok", True):
            # An explicitly requested engine that fails must report a clear failure.
            # It is NEVER silently replaced with the approximate solver (that mode
            # stays available on its own, clearly labelled).
            if _cancelled(job_id):
                return
            _update(
                job_id,
                status="failed",
                progress=100,
                message=result.get("reason", f"{engine_name} engine failed"),
                engine_label=result.get("engine_label"),
                resolved_engine=result.get("engine", engine_name),
                error={
                    "type": "EngineFailure",
                    "engine": result.get("engine", engine_name),
                    "detail": result.get("reason", "engine reported ok=False"),
                    "returncode": result.get("returncode"),
                    "workdir": result.get("workdir"),
                    "stdout_tail": result.get("stdout_tail"),
                    "stderr_tail": result.get("stderr_tail"),
                    "hint": result.get("hint"),
                },
            )
            return

        if _cancelled(job_id):
            return

        _update(
            job_id,
            status="completed",
            progress=100,
            message="Completed",
            engine_label=result.get("engine_label"),
            data_class=result.get("data_class", "MODEL OUTPUT"),
            validated_hydraulic_output=bool(result.get("validated_hydraulic_output", False)),
            disclaimer=result.get("disclaimer"),
            provenance=result.get("provenance"),
            results_dir=result.get("results_dir"),
            available_frames=result.get("available_frames", []),
            summary=result.get("summary"),
            fallback_used=fallback_used or bool(result.get("fallback_used")),
            resolved_engine=result.get("engine", engine_name),
            runtime_seconds=result.get("runtime_seconds"),
            mesh=result.get("mesh"),
            command=result.get("command"),
            map_frames=result.get("map_frames"),
            max_depth_m=result.get("max_depth_m"),
            max_velocity_mps=result.get("max_velocity_mps"),
            particle_count=result.get("particle_count"),
            timesteps=result.get("timesteps"),
            max_density=result.get("max_density"),
            min_density=result.get("min_density"),
            max_displacement_m=result.get("max_displacement_m"),
            workdir=result.get("workdir"),
        )
    except _Cancelled:
        _update(job_id, status="cancelled", message="Cancelled by user")
    except Exception as exc:  # noqa: BLE001 — surface a clean error, keep server alive
        _update(
            job_id,
            status="failed",
            message=str(exc) or exc.__class__.__name__,
            error={"type": exc.__class__.__name__, "detail": str(exc), "trace": traceback.format_exc()[-2000:]},
        )


class _Cancelled(Exception):
    pass


# --- Result file access -----------------------------------------------------

def results_path(job_id: str) -> Path | None:
    record = get(job_id)
    if not record or not record.get("results_dir"):
        return None
    return Path(record["results_dir"])


def load_summary(job_id: str) -> dict | None:
    record = get(job_id)
    if not record:
        return None
    if record.get("summary"):
        return record["summary"]
    path = results_path(job_id)
    if path and (path / "summary.json").exists():
        return json.loads((path / "summary.json").read_text(encoding="utf-8"))
    return None


def load_frame(job_id: str, minute: int) -> dict | None:
    path = results_path(job_id)
    if not path:
        return None
    frame = path / "timeline" / f"t{int(minute):03d}.geojson"
    if not frame.exists():
        return None
    return json.loads(frame.read_text(encoding="utf-8"))


def layer_file(job_id: str, layer: str) -> Path | None:
    path = results_path(job_id)
    if not path:
        return None
    candidates = {
        "flood_extent": path / "flood_extent.geojson",
        "max_depth": path / "max_depth.tif",
        "max_velocity": path / "max_velocity.tif",
        "arrival_time": path / "arrival_time.tif",
    }
    target = candidates.get(layer)
    return target if target and target.exists() else None
