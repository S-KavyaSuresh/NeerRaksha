"""In-process async jobs for the Sentinel-1 OBSERVATION workflow.

Same shape as scenario_jobs / benchmark_jobs: a GEE observation (network +
Earth Engine export) must not block the request thread.
"""
from __future__ import annotations

import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from remote_sensing import observation as obs  # noqa: E402

_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
RESULTS_ROOT = obs.OBS_RESULTS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(payload: dict) -> dict:
    payload = dict(payload or {})
    job_id = "obs-" + uuid.uuid4().hex[:16]
    rec = {
        "id": job_id, "status": "queued", "message": "Queued", "progress": 0,
        "payload": payload, "result": None, "error": None,
        "created_at": _now(), "updated_at": _now(),
    }
    with _LOCK:
        _JOBS[job_id] = rec
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return dict(rec)


def get(job_id: str) -> dict | None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        return dict(rec) if rec else None


def results(job_id: str) -> dict | None:
    rec = get(job_id)
    return rec.get("result") if rec else None


def _update(job_id: str, **f: Any) -> None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        if rec:
            rec.update(f)
            rec["updated_at"] = _now()


def _run(job_id: str) -> None:
    _update(job_id, status="running", progress=5, message="Contacting Google Earth Engine")
    try:
        p = (get(job_id) or {}).get("payload", {})
        out_dir = RESULTS_ROOT / job_id
        result = obs.run_observation(
            observation_start=p["observation_start"], observation_end=p["observation_end"],
            reference_start=p.get("reference_start"), reference_end=p.get("reference_end"),
            polarization=p.get("polarization", "VV"),
            threshold_db=p.get("threshold_db"),
            orbit_pass=p.get("orbit_pass"),
            scale_m=int(p.get("scale_m", 30)),
            aoi=p.get("aoi"),
            out_dir=out_dir,
        )
        status = result.get("status", "error")
        msg = {"ok": "Sentinel-1 observation ready",
               "unavailable": result.get("reason", "Earth Engine unavailable"),
               "error": result.get("reason", "processing error")}.get(status, status)
        _update(job_id, status=("completed" if status == "ok" else status),
                progress=100, message=msg, result=result)
    except Exception as exc:  # noqa: BLE001
        _update(job_id, status="error", progress=100,
                message=str(exc) or exc.__class__.__name__,
                error={"type": exc.__class__.__name__, "detail": str(exc),
                       "trace": traceback.format_exc()[-2000:]})
