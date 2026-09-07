"""Phase 4 orchestrator: one scenario -> {delft3d | sph | approximate} adapter -> common result.

    scenario JSON
         -> validate + resolve (DEM sample, domain check)
         -> deterministic breach hydrograph (written as CSV + JSON)
         -> engine adapter
         -> common result schema (depth / velocity / arrival / extent + metadata)

No silent fallback: if the requested engine fails, the run fails with that reason.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import config
from . import scenario as scen
from . import delft3d_scenario, sph_scenario, approximate_engine

RESULTS_ROOT = config.RESULTS_ROOT.parent / "ujjani_scenario"


def _approx_scenario_dict(sc: scen.UjjaniScenario) -> dict:
    """Map the generalized scenario onto the approximate engine's expected keys."""
    if sc.breach_width_m < 100:
        preset, breach_type = "partial_breach", "partial"
    elif sc.breach_width_m >= 200:
        preset, breach_type = "major_breach", "major"
    else:
        preset, breach_type = "baseline", "major"
    return {"preset": preset, "breach_type": breach_type,
            "breach_width_m": sc.breach_width_m, "breach_depth_m": sc.breach_depth_m}


def run_scenario(payload: dict, progress=lambda p, m="": None) -> dict:
    started = time.perf_counter()
    progress(3, "Building and validating scenario")
    try:
        sc = scen.from_request(payload).resolve()
    except scen.ScenarioError as exc:
        return {"ok": False, "stage": "scenario", "reason": str(exc)}

    engine = sc.engine
    out_root = RESULTS_ROOT / engine
    out_root.mkdir(parents=True, exist_ok=True)

    progress(10, "Generating breach discharge hydrograph")
    try:
        hg = scen.breach_hydrograph(sc)
    except scen.ScenarioError as exc:
        return {"ok": False, "stage": "hydrograph", "reason": str(exc)}
    hg_files = scen.write_hydrograph(hg, out_root)

    (RESULTS_ROOT / "scenario.json").parent.mkdir(parents=True, exist_ok=True)
    import json
    (out_root / "scenario.json").write_text(json.dumps(sc.to_dict(), indent=2), encoding="utf-8")

    progress(18, f"Running {engine} adapter")
    if engine == "delft3d":
        res = delft3d_scenario.run(sc, hg, out_root, progress=lambda p, m="": progress(18 + int(0.72 * p), m))
    elif engine == "sph":
        res = sph_scenario.run(sc, hg, out_root, progress=lambda p, m="": progress(18 + int(0.72 * p), m))
    elif engine == "approximate":
        res = approximate_engine.run(_approx_scenario_dict(sc),
                                     progress=lambda p, m="": progress(18 + int(0.72 * p), m))
        res.setdefault("ok", True)
    else:
        return {"ok": False, "stage": "dispatch", "reason": f"unknown engine '{engine}'"}

    if not res.get("ok", True):
        return {"ok": False, "stage": engine, "reason": res.get("reason", f"{engine} adapter failed"),
                "engine": engine, "detail": {k: res.get(k) for k in
                                             ("workdir", "warnings", "returncode", "stdout_tail", "stderr_tail")},
                "scenario": sc.to_dict(), "hydrograph": {k: v for k, v in hg.items() if not k.startswith("_")}}

    summary = res.get("summary", {})
    common = {
        "ok": True,
        "engine": res.get("engine", engine),
        "engine_label": res.get("engine_label"),
        "scenario_id": sc.case_id,
        "preset": sc.preset,
        "data_classification": "MODEL OUTPUT (this run) — see scenario.json for per-field REAL DATA / "
                               "MODEL INPUT / ASSUMPTION-DEMO classification",
        "terrain_source": sc.dem_path,
        "terrain_class": "REAL DATA (Ujjani 30 m DEM)",
        "crs": sc.crs,
        "dam_location": {"lat": sc.dam_lat, "lon": sc.dam_lon,
                         "x_m": sc.dam_x_m, "y_m": sc.dam_y_m,
                         "terrain_elev_m": sc.terrain_elev_at_dam_m, "in_domain": sc.in_domain},
        "reservoir_level_m": sc.reservoir_level_m,
        "reservoir_level_class": "ASSUMPTION / DEMO (no Ujjani storage curve)",
        "breach": {"width_m": sc.breach_width_m, "depth_m": sc.breach_depth_m,
                   "formation_time_s": sc.breach_formation_time_s,
                   "recession_time_s": sc.recession_time_s,
                   "growth_model": "linear width+depth over formation time; broad-crested weir discharge"},
        "hydrograph": {
            "formulation": hg["formulation"], "reference": hg["reference"],
            "provenance": hg["provenance"],
            "peak_discharge_m3s": hg["peak_discharge_m3s"],
            "time_of_peak_s": hg["time_of_peak_s"],
            "assumptions": hg["assumptions"],
            "files": hg_files,
        },
        "simulation_duration_s": sc.simulation_duration_s,
        "output_interval_s": sc.output_interval_s,
        "gravity_m_s2": sc.gravity_m_s2,
        "manning_n": sc.manning_n,
        "results_dir": res.get("results_dir", str(out_root)),
        "available_frames": res.get("available_frames", summary.get("available_frames", [])),
        "outputs": _list_outputs(Path(res.get("results_dir", out_root))),
        "max_depth_m": res.get("max_depth_m", summary.get("maximum_depth_m")),
        "max_velocity_mps": res.get("max_velocity_mps", summary.get("maximum_velocity_mps")),
        "arrival_available": "arrival_time.tif" in _list_outputs(Path(res.get("results_dir", out_root)))
        or "arrival_time_local.tif" in _list_outputs(Path(res.get("results_dir", out_root))),
        "mesh": res.get("mesh"),
        "particle_count": res.get("particle_count"),
        "timesteps": res.get("timesteps"),
        "physical_duration_s": res.get("physical_duration_s"),
        "sph_status": res.get("status") if engine == "sph" else None,
        "release_representation": res.get("release_representation"),
        "runtime_seconds": round(time.perf_counter() - started, 2),
        "engine_runtime_seconds": res.get("runtime_seconds"),
        "warnings": res.get("warnings", []),
        "assumptions": [
            "reservoir level / head are ASSUMED (no Ujjani storage curve)",
            "recession is an assumed exponential drawdown proxy",
            "30 m DEM does not resolve the dam wall or a sub-mesh breach opening",
            *( ["SPH is a reduced-resolution prototype, NOT georeferenced Ujjani"] if engine == "sph" else [] ),
            *( ["Delft3D breach is a point source; opening geometry not mesh-resolved"] if engine == "delft3d" else [] ),
            *( ["approximate engine serves pre-computed demo products; not a Phase-4 hydrodynamic run"] if engine == "approximate" else [] ),
        ],
        "limitations": _limitations(engine),
        "validation_status": "NOT PERFORMED",
        "run_class": "MODEL DEMONSTRATION / SCENARIO SIMULATION",
        "provenance": res.get("provenance"),
        "summary": summary,
        "scenario": sc.to_dict(),
    }
    return common


def _list_outputs(d: Path) -> list[str]:
    if not d.exists():
        return []
    out = sorted(p.name for p in d.glob("*") if p.is_file())
    tl = d / "timeline"
    if tl.exists():
        out.append(f"timeline/ ({len(list(tl.glob('t*.geojson')))} frames)")
    return out


def _limitations(engine: str) -> list[str]:
    common = [
        "No independent observations — verification/benchmark only in Phase 3; Phase 4 is a scenario demonstration.",
        "Reservoir level, head and recession are assumptions (no authoritative Ujjani storage/breach data).",
        "Ujjani 30 m DEM does not resolve the dam structure.",
    ]
    if engine == "delft3d":
        common += [
            "Breach is an internal point discharge source at the dam coordinate; the breach opening "
            "geometry is not resolved by the ~180 m demonstration mesh.",
            "A locally refined Phase-4 modelling mesh would be needed for a resolved internal breach.",
        ]
    elif engine == "sph":
        common += [
            "SPH is a reduced-resolution 2D prototype (fixed 0.40 m model head) — NOT full-scale, "
            "NOT georeferenced; GeoJSON uses a flagged demonstration affine placement at the dam.",
            "Full-scale SPH of the ~19 km Ujjani domain at meaningful resolution is impractical here.",
        ]
    elif engine == "approximate":
        common += ["Approximate engine returns pre-computed demonstration products; it is not a "
                   "Phase-4 hydrodynamic solution and is labelled approximate/demo."]
    return common
