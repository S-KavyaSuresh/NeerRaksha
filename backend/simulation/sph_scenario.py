"""Phase 4 SPH adapter — generalized Ujjani scenario -> genuine WCSPH.

The Phase-2 solver (`sph_solver.py`) is used unchanged. This adapter only
translates the generalized breach scenario into an SPH initial condition:

    reservoir column height  H0 = breach head (breach_depth_m)
    reservoir column width   a  = reduced modelling width (scenario-scaled)
    box                      long dry runout on a flat frictionless bed
    -> genuine WCSPH dam-break -> particle motion -> field reconstruction

STATUS (explicit, honest): this is a **reduced-resolution 2D prototype**, NOT a
full-scale georeferenced Ujjani SPH simulation. Full-scale SPH of the ~19 km
Ujjani domain at a meaningful resolution is computationally impractical here.
Particle count, spacing, smoothing length and runtime are recorded. GeoJSON is
written with a clearly-flagged DEMONSTRATION affine placement at the dam
(``georeferenced: false``); it must not be presented as a physical Ujjani
prediction.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from . import config, sph_solver
from . import scenario as scen

DEPTH_BANDS = ((0.05, 1.0, "0.05-1.0 m"), (1.0, 3.0, "1.0-3.0 m"),
               (3.0, 6.0, "3.0-6.0 m"), (6.0, None, "6.0+ m"))
GRID_NX, GRID_NY = 120, 60


MODEL_HEAD_M = 0.40   # fixed reduced-scale model head (keeps every preset ~15 s and stable)


def _config_from_scenario(sc: scen.UjjaniScenario) -> tuple[sph_solver.SPHConfig, dict]:
    """Reduced-resolution SPH config. The scenario sets the column ASPECT RATIO and
    the runout length; the absolute model head is fixed (MODEL_HEAD_M) so the
    genuine solver stays affordable. Absolute Ujjani scale is NOT represented."""
    # scenario shape -> column aspect ratio (height / width) and runout multiple
    aspect = float(np.clip((sc.breach_depth_m / max(sc.breach_width_m, 1.0)) * 12.0, 0.35, 3.0))
    runout_mult = float(np.clip(6.0 + sc.breach_width_m / 40.0, 6.0, 12.0))
    H0 = MODEL_HEAD_M
    a = H0 / aspect
    cfg = sph_solver.SPHConfig()
    cfg.reservoir = (a, H0)
    cfg.box = (a + runout_mult * a, max(1.6 * H0, 2.2 * a))
    cfg.dx = float(np.clip(a / 16.0, 0.010, 0.030))
    cfg.t_end = float(np.clip(9.0 * math.sqrt(a / 9.81), 0.5, 1.2))
    cfg.n_frames = 20
    scale = {
        "model_head_H0_m": H0,
        "model_column_width_a_m": round(a, 4),
        "column_aspect_ratio_H0_over_a": round(aspect, 3),
        "runout_multiple_of_a": round(runout_mult, 2),
        "box_m": [round(v, 3) for v in cfg.box],
        "dx_m": round(cfg.dx, 4),
        "physical_window_s": round(cfg.t_end, 3),
        "length_scale_note": "fixed reduced model head 0.40 m; scenario sets the column aspect "
                             "ratio (breach_depth_m / breach_width_m) and the runout length. "
                             "Absolute Ujjani dimensions are NOT represented.",
    }
    return cfg, scale


def _rasterise(frame, box, h, mass):
    x = frame["x"]
    v = frame["v"]
    rho = np.clip(frame["rho"], 0.3 * 1000.0, 3.0 * 1000.0)
    vol = mass / rho
    gx = np.linspace(0.0, box[0], GRID_NX)
    gy = np.linspace(0.0, box[1], GRID_NY)
    cx, cy = np.meshgrid(gx, gy)
    depth = np.zeros_like(cx)
    snum = np.zeros_like(cx)
    wsum = np.zeros_like(cx)
    speed = np.hypot(v[:, 0], v[:, 1])
    a_k = 7.0 / (4.0 * np.pi * h * h)
    reach = 2.0 * h
    for k in range(x.shape[0]):
        r = np.hypot(cx - x[k, 0], cy - x[k, 1])
        m = r < reach
        if not m.any():
            continue
        q = r[m] / h
        wk = a_k * (1.0 - 0.5 * q) ** 4 * (2.0 * q + 1.0)
        vk = vol[k] * wk
        depth[m] += vk
        snum[m] += vk * speed[k]
        wsum[m] += vk
    # 2D volume-fraction -> a demonstration depth in metres
    depth *= 6.0
    sp = np.zeros_like(cx)
    nz = wsum > 1e-9
    sp[nz] = snum[nz] / wsum[nz]
    depth[depth < 0.02] = 0.0
    sp[depth <= 0.0] = 0.0
    return gx, gy, depth, sp


# demonstration affine placement at the dam (NOT surveyed / NOT georeferenced)
_PLACE_DLON = 0.010   # ~1 km E over the model box
_PLACE_DLAT = -0.006


def _write_frame(path: Path, gx, gy, depth, minute, sc, box):
    from rasterio.features import shapes
    from rasterio.transform import from_bounds

    ny, nx = depth.shape
    tf = from_bounds(0.0, 0.0, box[0], box[1], nx, ny)
    sx = _PLACE_DLON / box[0]
    sy = _PLACE_DLAT / box[1]
    lon0, lat0 = sc.dam_lon, sc.dam_lat

    def ll(ring):
        return [[lon0 + px * sx, lat0 + py * sy] for px, py in ring]

    feats = []
    dflip = np.flipud(depth)
    for low, high, label in DEPTH_BANDS:
        hi = np.inf if high is None else high
        mask = (dflip >= low) & (dflip < hi)
        if not mask.any():
            continue
        for geom, val in shapes(mask.astype("uint8"), mask=mask, transform=tf):
            if not val:
                continue
            geom["coordinates"] = [ll(r) for r in geom["coordinates"]]
            feats.append({"type": "Feature", "properties": {
                "time_min": int(minute), "depth_min_m": low,
                "depth_max_m": None if high is None else high, "depth_class": label,
                "model_type": "sph_wcsph_prototype", "validated_hydraulic_output": False,
                "georeferenced": False, "placement": "DEMONSTRATION affine at dam — not surveyed",
                "scenario_id": sc.preset,
            }, "geometry": geom})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")


def run(sc: scen.UjjaniScenario, hydrograph: dict, out_dir: Path,
        progress=lambda p, m="": None) -> dict:
    cfg, scale = _config_from_scenario(sc)
    progress(8, f"SPH prototype: dam-break H0={scale['model_head_H0_m']:.1f} m, "
                f"a={scale['model_column_width_a_m']:.2f} m")
    started = time.perf_counter()
    try:
        res = sph_solver.run(cfg, progress=lambda p, m="": progress(8 + int(0.6 * p), m))
    except Exception as exc:  # noqa: BLE001 — genuine instability must surface as failure
        return {"ok": False, "engine": "sph_wcsph", "reason": f"SPH solver failed: {exc}"}
    runtime = time.perf_counter() - started
    m = res.metrics
    if not m.get("finite", False):
        return {"ok": False, "engine": "sph_wcsph", "reason": "SPH produced non-finite state"}
    if not (m["max_velocity_mps"] > 0 and m["max_displacement_m"] > 1e-3):
        return {"ok": False, "engine": "sph_wcsph", "reason": "SPH particles did not move"}

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in (out_dir / "timeline").glob("t*.geojson") if (out_dir / "timeline").exists() else []:
        stale.unlink()
    (out_dir / "timeline").mkdir(parents=True, exist_ok=True)

    box = cfg.box
    h = m["smoothing_length_m"]
    mass = m["particle_mass_kg"]
    times = np.array([f["t"] for f in res.frames])

    progress(72, "Reconstructing SPH fields")
    ny, nx = GRID_NY, GRID_NX
    max_depth = np.zeros((ny, nx))
    max_speed = np.zeros((ny, nx))
    arrival = np.full((ny, nx), -1.0)
    timeline = []
    gx = gy = None
    for idx, frame in enumerate(res.frames):
        gx, gy, depth, speed = _rasterise(frame, box, h, mass)
        minute = idx
        max_depth = np.maximum(max_depth, depth)
        max_speed = np.maximum(max_speed, speed)
        arrival[(arrival < 0) & (depth >= 0.05)] = minute
        _write_frame(out_dir / "timeline" / f"t{minute:03d}.geojson", gx, gy, depth, minute, sc, box)
        timeline.append({
            "minute": minute, "sph_time_s": round(float(frame["t"]), 4),
            "sph_step": int(frame["step"]),
            "max_depth_m": round(float(depth.max()), 4),
            "max_velocity_mps": round(float(speed.max()), 4),
            "wet_cells": int((depth >= 0.05).sum()),
        })
    _write_frame(out_dir / "flood_extent.geojson", gx, gy, max_depth, len(res.frames) - 1, sc, box)

    # GeoTIFF in LOCAL model metres (not georeferenced) + particle trajectories
    try:
        import rasterio
        from rasterio.transform import from_origin
        prof = dict(driver="GTiff", height=ny, width=nx, count=1, dtype="float32",
                    transform=from_origin(0.0, box[1], box[0] / nx, box[1] / ny),
                    crs=None, compress="deflate")
        for name, arr in (("max_depth_local.tif", max_depth), ("max_velocity_local.tif", max_speed),
                          ("arrival_time_local.tif", arrival)):
            with rasterio.open(out_dir / name, "w", nodata=(-1 if "arrival" in name else 0), **prof) as dst:
                dst.write(np.flipud(arr).astype("float32"), 1)
    except Exception:
        pass
    np.savez_compressed(out_dir / "particles.npz", times=times, positions0=res.positions0,
                        **{f"x_{k}": f["x"] for k, f in enumerate(res.frames)},
                        **{f"v_{k}": f["v"] for k, f in enumerate(res.frames)})

    # particle frames as lon/lat JSON for the frontend Particle View. The affine
    # placement is a DEMONSTRATION only (georeferenced = false).
    sx = _PLACE_DLON / box[0]
    sy = _PLACE_DLAT / box[1]
    lon0, lat0 = sc.dam_lon, sc.dam_lat
    footprint = {
        "corners_lonlat": [[lon0, lat0], [lon0 + _PLACE_DLON, lat0],
                           [lon0 + _PLACE_DLON, lat0 + _PLACE_DLAT], [lon0, lat0 + _PLACE_DLAT],
                           [lon0, lat0]],
        "box_m": list(box), "georeferenced": False,
        "label": "SPH DEMONSTRATION FOOTPRINT — visualization only; not georeferenced",
    }
    pframes = []
    for k, frame in enumerate(res.frames):
        px, py = frame["x"][:, 0], frame["x"][:, 1]
        spd = np.hypot(frame["v"][:, 0], frame["v"][:, 1])
        lon = lon0 + px * sx
        lat = lat0 + py * sy
        pts = [[round(float(lon[i]), 7), round(float(lat[i]), 7),
                round(float(spd[i]), 4), round(float(frame["rho"][i]), 1)]
               for i in range(px.shape[0])]
        pframes.append({"frame": k, "sph_time_s": round(float(frame["t"]), 4),
                        "sph_step": int(frame["step"]),
                        "max_speed_mps": round(float(spd.max()), 4),
                        "columns": ["lon", "lat", "speed_mps", "density"],
                        "points": pts})
    (out_dir / "particle_frames.json").write_text(json.dumps({
        "engine": "sph_wcsph", "georeferenced": False,
        "disclaimer": "SPH demonstration footprint — visualization only; not georeferenced or "
                      "operationally validated.",
        "particle_count": int(px.shape[0]), "frames": len(pframes),
        "physical_duration_s": round(float(times[-1]), 4),
        "footprint": footprint, "particle_frames": pframes,
    }), encoding="utf-8")

    summary = {
        "engine": "sph_wcsph",
        "engine_label": "SPH (genuine WCSPH, Phase-4 reduced-resolution prototype)",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "status": "reduced-resolution 2D prototype — genuine WCSPH solver; NOT full-scale "
                  "georeferenced Ujjani. GeoJSON uses a DEMONSTRATION affine placement at the dam.",
        "georeferenced": False,
        "footprint": footprint,
        "scale": scale,
        "particle_count": m["particle_count"],
        "smoothing_length_m": m["smoothing_length_m"],
        "dt_final_s": m["dt_final_s"],
        "timesteps": m["timesteps"],
        "physical_duration_s": m["simulation_time_s"],
        "frames": len(res.frames),
        "sound_speed_mps": m["sound_speed_mps"],
        "density_max": m["max_density"], "density_min": m["min_density"],
        "density_median": m["median_density"],
        "density_relative_error_pct": m["density_relative_error_pct"],
        "velocity_max_mps": m["max_velocity_mps"],
        "pressure_max_pa": m["max_pressure_pa"],
        "max_displacement_m": m["max_displacement_m"],
        "finite": m["finite"], "reproducible_seed": cfg.seed,
        "runtime_seconds": round(runtime, 2),
        "hydrograph_peak_m3s": hydrograph["peak_discharge_m3s"],
        "available_frames": [t["minute"] for t in timeline],
        "maximum_depth_m": round(float(max_depth.max()), 4),
        "maximum_velocity_mps": round(float(max_speed.max()), 4),
        "timeline": timeline,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "engine": "sph_wcsph",
        "engine_label": summary["engine_label"],
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "results_dir": str(out_dir),
        "available_frames": summary["available_frames"],
        "summary": summary,
        "runtime_seconds": round(runtime, 2),
        "particle_count": m["particle_count"],
        "timesteps": m["timesteps"],
        "physical_duration_s": m["simulation_time_s"],
        "max_depth_m": summary["maximum_depth_m"],
        "max_velocity_mps": summary["maximum_velocity_mps"],
        "max_density": m["max_density"], "min_density": m["min_density"],
        "frames": len(res.frames),
        "status": summary["status"],
        "footprint": footprint,
        "particle_frames_file": str(out_dir / "particle_frames.json"),
        "provenance": "Genuine 2D WCSPH (Phase-2 solver) on a scenario-derived reduced dam-break; "
                      "reduced-resolution prototype, NOT georeferenced Ujjani. MODEL DEMONSTRATION.",
    }
