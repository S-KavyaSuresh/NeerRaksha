"""Phase 4 — in-process async jobs for generalized Ujjani scenario runs."""
from __future__ import annotations

import json
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

from simulation import scenario_run  # noqa: E402

_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(payload: dict) -> dict:
    payload = dict(payload or {})
    rec = {
        "id": "scn-" + uuid.uuid4().hex[:16],
        "status": "queued", "progress": 0, "message": "Queued",
        "engine": str(payload.get("engine", "delft3d")),
        "preset": str(payload.get("preset", "custom")),
        "payload": payload,
        "result": None, "error": None,
        "validation_status": "NOT PERFORMED",
        "data_class": "MODEL OUTPUT",
        "created_at": _now(), "updated_at": _now(),
    }
    with _LOCK:
        _JOBS[rec["id"]] = rec
    threading.Thread(target=_run, args=(rec["id"],), daemon=True).start()
    return dict(rec)


def get(job_id: str) -> dict | None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        return dict(rec) if rec else None


def _update(job_id: str, **f: Any) -> None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        if rec:
            rec.update(f)
            rec["updated_at"] = _now()


def results(job_id: str) -> dict | None:
    rec = get(job_id)
    if not rec or not rec.get("result"):
        return None
    return rec["result"]


def hydrograph(job_id: str) -> dict | None:
    rec = get(job_id)
    if not rec:
        return None
    res = rec.get("result") or {}
    hg = res.get("hydrograph")
    if hg and hg.get("files", {}).get("json"):
        p = Path(hg["files"]["json"])
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            data["files"] = hg["files"]
            return data
    # failure path still carries the hydrograph
    return res.get("hydrograph") or (rec.get("error") or {}).get("hydrograph")


def _run(job_id: str) -> None:
    _update(job_id, status="running", progress=2, message="Starting scenario run")

    def progress(pct: float, msg: str = "") -> None:
        _update(job_id, progress=max(2, min(99, int(pct))), message=msg or "running")

    try:
        payload = (get(job_id) or {}).get("payload", {})
        result = scenario_run.run_scenario(payload, progress=progress)
        if not result.get("ok"):
            _update(job_id, status="failed", progress=100,
                    message=result.get("reason", "scenario run failed"),
                    error={"stage": result.get("stage"), "detail": result.get("reason"),
                           "engine": result.get("engine"),
                           "extra": result.get("detail"),
                           "hydrograph": result.get("hydrograph")})
            return
        _update(job_id, status="completed", progress=100, message="Completed", result=result)
    except Exception as exc:  # noqa: BLE001
        _update(job_id, status="failed", progress=100,
                message=str(exc) or exc.__class__.__name__,
                error={"type": exc.__class__.__name__, "detail": str(exc),
                       "trace": traceback.format_exc()[-2000:]})
