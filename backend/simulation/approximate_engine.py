"""Approximate 2D flood-routing engine adapter.

Wraps the existing ``ujjani_solver`` prototype behind a stable interface used by
the simulation job runner. If the live solver cannot run in this environment
(missing scientific deps or a cropped DEM), it serves the committed pre-computed
products so the demo always has a complete vertical slice.

All outputs are MODEL OUTPUT from an approximate, unvalidated prototype.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config

DISCLAIMER = "Automated approximate 2D flood-routing prototype — not validated hydraulic output."


def _load_summary(results_dir: Path) -> dict:
    path = results_dir / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"No summary.json under {results_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def _try_live_run(scenario: dict) -> Path | None:
    """Attempt the live prototype solver. Opt-in via NEERRAKSHA_RUN_LIVE_SOLVER=1."""
    if os.environ.get("NEERRAKSHA_RUN_LIVE_SOLVER", "").strip() not in {"1", "true", "yes"}:
        return None
    try:
        from .ujjani_solver import run as run_solver  # noqa: WPS433 (deps may be absent)
    except Exception:
        return None
    try:
        run_solver(
            duration_min=config.DEMO_DURATION_MIN,
            output_interval_min=config.DEMO_INTERVAL_MIN,
        )
    except Exception:
        return None
    return config.RESULTS_ROOT


def run(scenario: dict, progress=lambda pct, msg="": None) -> dict:
    """Produce (or locate) approximate flood products for ``scenario``.

    Returns a metadata dict describing where the frontend-friendly products live.
    """
    progress(5, "Resolving scenario and data sources")
    live_dir = _try_live_run(scenario)
    if live_dir is not None:
        results_dir = live_dir
        ran_live = True
        progress(70, "Live approximate solver completed")
    else:
        results_dir = config.results_dir_for(scenario)
        ran_live = False
        progress(45, "Loading pre-computed approximate products")

    summary = _load_summary(results_dir)
    frames = summary.get("available_frames") or [pt["minute"] for pt in summary.get("timeline", [])]
    progress(90, "Products ready")

    return {
        "engine": "approximate_2d_flood_routing_prototype",
        "engine_label": "Approximate 2D flood-routing prototype",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "disclaimer": DISCLAIMER,
        "ran_live": ran_live,
        "results_dir": str(results_dir),
        "available_frames": sorted(int(m) for m in frames),
        "summary": summary,
        "provenance": (
            "Live approximate solver run" if ran_live
            else "Pre-computed approximate solver output (committed fallback)"
        ),
    }
