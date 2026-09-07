"""In-process background jobs for the Phase 3 dam-break benchmark.

Same lightweight pattern as ``jobs.py`` (thread + in-memory registry). Kept
separate so the simulation lifecycle (POST /api/simulations) is untouched.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from simulation import benchmark  # noqa: E402

_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(options: dict | None = None) -> dict:
    options = options or {}
    record = {
        "id": "bench-" + uuid.uuid4().hex[:16],
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "benchmark_id": benchmark.BENCHMARK["id"],
        "reference_source": benchmark.BENCHMARK["reference"]["primary_source"],
        "options": options,
        "error": None,
        "results_dir": None,
        "sph_summary": None,
        "delft3d_summary": None,
        "metrics": None,
        "status_block": None,
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _LOCK:
        _JOBS[record["id"]] = record
    threading.Thread(target=_run, args=(record["id"],), daemon=True).start()
    return dict(record)


def get(job_id: str) -> dict | None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        return dict(rec) if rec else None


def comparison(job_id: str) -> dict | None:
    rec = get(job_id)
    if not rec:
        return None
    if rec.get("results_dir"):
        path = Path(rec["results_dir"]) / "comparison" / "comparison.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    if rec.get("metrics") is not None:
        return {"benchmark_id": rec["benchmark_id"], "metrics": rec["metrics"],
                "status": rec.get("status_block"), "sph_result": rec.get("sph_summary"),
                "delft3d_result": rec.get("delft3d_summary")}
    return None


def _update(job_id: str, **fields: Any) -> None:
    with _LOCK:
        rec = _JOBS.get(job_id)
        if rec:
            rec.update(fields)
            rec["updated_at"] = _now()


def _run(job_id: str) -> None:
    _update(job_id, status="running", progress=2, message="Starting benchmark")

    def progress(pct: float, msg: str = "") -> None:
        _update(job_id, progress=max(2, min(99, int(pct))), message=msg or "running")

    try:
        opts = (get(job_id) or {}).get("options", {})
        result = benchmark.run_benchmark(progress=progress, sph_dx=opts.get("sph_dx"))
        if not result.get("ok"):
            _update(job_id, status="failed", progress=100,
                    message=result.get("reason", "benchmark failed"),
                    error={"stage": result.get("stage"), "detail": result.get("reason"),
                           "extra": result.get("detail")},
                    sph_summary=result.get("sph_summary"))
            return
        _update(job_id, status="completed", progress=100, message="Completed",
                results_dir=result["results_dir"],
                sph_summary=result["sph_summary"],
                delft3d_summary=result["delft3d_summary"],
                metrics=result["metrics"],
                status_block=result["status"])
    except Exception as exc:  # noqa: BLE001
        _update(job_id, status="failed", progress=100,
                message=str(exc) or exc.__class__.__name__,
                error={"type": exc.__class__.__name__, "detail": str(exc),
                       "trace": traceback.format_exc()[-2000:]})
