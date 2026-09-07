"""Phase 3 benchmark API — dam-break verification + SPH vs Delft3D comparison.

    POST /api/benchmarks/run          -> start the benchmark job (returns bench-<id>)
    GET  /api/benchmarks/{id}         -> job status + summaries
    GET  /api/benchmarks/{id}/comparison  -> full comparison.json (metrics + status + limitations)

Uses its own in-memory job runner; POST /api/simulations and the simulation
lifecycle are untouched.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.simulation import benchmark_jobs

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


class BenchmarkRun(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)  # e.g. {"sph_dx": 0.0073}


def _public(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "status": rec["status"],
        "progress": rec["progress"],
        "message": rec["message"],
        "benchmark_id": rec["benchmark_id"],
        "reference_source": rec["reference_source"],
        "data_class": rec["data_class"],
        "validated_hydraulic_output": rec["validated_hydraulic_output"],
        "sph_summary": rec.get("sph_summary"),
        "delft3d_summary": rec.get("delft3d_summary"),
        "metrics": rec.get("metrics"),
        "status_block": rec.get("status_block"),
        "error": rec.get("error"),
        "created_at": rec["created_at"],
        "updated_at": rec["updated_at"],
    }


def _require(job_id: str) -> dict:
    rec = benchmark_jobs.get(job_id)
    if not rec:
        raise HTTPException(404, detail={"code": "BENCHMARK_NOT_FOUND", "message": "Unknown benchmark id."})
    return rec


@router.post("/run")
def run_benchmark(body: BenchmarkRun | None = None):
    return _public(benchmark_jobs.create((body.options if body else {}) or {}))


@router.get("/{job_id}")
def get_benchmark(job_id: str):
    return _public(_require(job_id))


@router.get("/{job_id}/comparison")
def get_comparison(job_id: str):
    rec = _require(job_id)
    if rec["status"] == "failed":
        raise HTTPException(409, detail={"code": "BENCHMARK_FAILED", "message": rec["message"],
                                         "error": rec.get("error")})
    data = benchmark_jobs.comparison(job_id)
    if data is None:
        raise HTTPException(409, detail={"code": "BENCHMARK_NOT_READY",
                                         "message": f"Benchmark is {rec['status']}."})
    return data
