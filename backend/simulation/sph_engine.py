"""SPH engine adapter for NeerRaksha.

Runs the genuine 2D weakly-compressible SPH solver (``sph_solver.py``) for a
small dam-break case, then converts the real particle state at each saved frame
into the demonstration-scale GIS products the rest of the pipeline consumes
(depth / velocity / arrival GeoTIFF, depth-banded GeoJSON per frame, flood
extent, summary.json). Particle output is also saved as an inspectable ``.npz``.

Nothing here is validated hydraulic postprocessing:
  * the SPH box is placed on a small demonstration footprint downstream of the
    dam — it is NOT a georeferenced Ujjani domain;
  * frame index is used as the timeline "minute" so the existing 0..N UI slider
    scrubs genuine distinct SPH states;
  * depth is an SPH volume-fraction interpolation scaled to a plausible band.

If the solver fails or produces non-finite state, ``run()`` returns
``{"ok": False, "reason": ...}`` and the job is marked ``failed`` — it is never
silently replaced by the approximate solver.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import config
from . import sph_solver

DISCLAIMER = (
    "SPH demonstration-scale model — genuine weakly-compressible SPH on a small "
    "dam-break test case, mapped to a demonstration footprint. Not georeferenced, "
    "not calibrated, not validated for operational prediction."
)
DEPTH_BANDS = ((0.05, 1.0, "0.05-1.0 m"), (1.0, 3.0, "1.0-3.0 m"),
               (3.0, 6.0, "3.0-6.0 m"), (6.0, None, "6.0+ m"))

# Demonstration footprint: a ~2.0 km x 1.2 km box just downstream of Ujjani Dam.
# The SPH box (metres) is affine-mapped onto this lon/lat rectangle. This is a
# placement for visualisation only, NOT a surveyed model domain.
FOOTPRINT_LON0, FOOTPRINT_LAT0 = 75.1215, 18.0735          # top-left (near dam)
FOOTPRINT_DLON, FOOTPRINT_DLAT = 0.0190, -0.0108           # +x -> E, +y -> S
DEPTH_SCALE_M = 7.0        # maps SPH volume-fraction ~[0,1] to a 0..~7 m band
GRID_NX, GRID_NY = 120, 78


def _sph_to_lonlat(px, py, box):
    """Affine map SPH box coords (m) -> (lon, lat) on the demo footprint."""
    fx = px / box[0]
    fy = py / box[1]
    lon = FOOTPRINT_LON0 + fx * FOOTPRINT_DLON
    lat = FOOTPRINT_LAT0 + fy * FOOTPRINT_DLAT
    return lon, lat


def _rasterise_frame(frame, box, h):
    """SPH particle state -> (depth grid, speed grid) via kernel interpolation.

    depth(cell)  = DEPTH_SCALE_M * Σ_p (m_p/ρ_p) W(|x_cell - x_p|, h)
    speed(cell)  = Σ_p (m_p/ρ_p) |v_p| W  /  Σ_p (m_p/ρ_p) W        (kernel mean)
    Both are genuine SPH field reconstructions of the particle data.
    """
    x = frame["x"]
    v = frame["v"]
    gx = np.linspace(0.0, box[0], GRID_NX)
    gy = np.linspace(0.0, box[1], GRID_NY)
    cx, cy = np.meshgrid(gx, gy)                     # (NY, NX)
    depth = np.zeros_like(cx)
    speed_num = np.zeros_like(cx)
    weight = np.zeros_like(cx)
    speed_p = np.sqrt(np.einsum("ij,ij->i", v, v))

    inv_h = 1.0 / h
    reach = 2.0 * h
    for k in range(x.shape[0]):
        dxg = cx - x[k, 0]
        dyg = cy - x[k, 1]
        r = np.hypot(dxg, dyg)
        near = r < reach
        if not near.any():
            continue
        q = r[near] * inv_h
        wk = (7.0 / (4.0 * np.pi * h * h)) * (1.0 - 0.5 * q) ** 4 * (2.0 * q + 1.0)
        vk = frame["vol"][k] * wk
        depth[near] += vk
        speed_num[near] += vk * speed_p[k]
        weight[near] += vk

    depth *= DEPTH_SCALE_M
    speed = np.zeros_like(cx)
    nz = weight > 1e-9
    speed[nz] = speed_num[nz] / weight[nz]
    speed[~nz] = 0.0
    depth[depth < 0.02] = 0.0
    speed[depth <= 0.0] = 0.0
    return gx, gy, depth, speed


def _write_frame(path: Path, gx, gy, depth, minute, scenario, box):
    """Merge same-band cells into polygons (rasterio.features.shapes), map the
    SPH box to the demo footprint, and write EPSG:4326 GeoJSON."""
    from rasterio.features import shapes
    from rasterio.transform import from_bounds

    ny, nx = depth.shape
    tf = from_bounds(0.0, 0.0, box[0], box[1], nx, ny)  # SPH-box metres
    sx = FOOTPRINT_DLON / box[0]
    sy = FOOTPRINT_DLAT / box[1]

    def to_lonlat(ring):
        return [[FOOTPRINT_LON0 + px * sx, FOOTPRINT_LAT0 + py * sy] for px, py in ring]

    feats = []
    depth_flip = np.flipud(depth)  # row 0 = top; transform expects that
    for low, high, label in DEPTH_BANDS:
        hi = np.inf if high is None else high
        mask = (depth_flip >= low) & (depth_flip < hi)
        if not mask.any():
            continue
        for geom, val in shapes(mask.astype("uint8"), mask=mask, transform=tf):
            if not val:
                continue
            geom["coordinates"] = [to_lonlat(ring) for ring in geom["coordinates"]]
            feats.append({
                "type": "Feature",
                "properties": {
                    "time_min": int(minute), "depth_min_m": low,
                    "depth_max_m": None if high is None else high,
                    "depth_class": label, "model_type": "sph_demo",
                    "validated_hydraulic_output": False,
                    "scenario_id": (scenario or {}).get("preset"),
                },
                "geometry": geom,
            })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")


def _write_geotiffs(out_dir: Path, gx, gy, max_depth, max_speed, arrival, box):
    try:
        import rasterio
        from rasterio.transform import from_bounds
    except Exception:
        return []
    ny, nx = max_depth.shape
    w, s = _sph_to_lonlat(gx[0], gy[0], box)
    e, n = _sph_to_lonlat(gx[-1], gy[-1], box)
    west, east = min(w, e), max(w, e)
    south, north = min(s, n), max(s, n)
    transform = from_bounds(west, south, east, north, nx, ny)
    prof = dict(driver="GTiff", height=ny, width=nx, count=1, dtype="float32",
                crs="EPSG:4326", transform=transform, compress="deflate")
    written = []
    for name, arr, nodata in (("max_depth.tif", max_depth, 0.0),
                              ("max_velocity.tif", max_speed, 0.0),
                              ("arrival_time.tif", arrival, -1.0)):
        with rasterio.open(out_dir / name, "w", nodata=nodata, **prof) as dst:
            dst.write(np.flipud(arr).astype("float32"), 1)
        written.append(name)
    return written


def run(scenario: dict, progress=lambda pct, msg="": None) -> dict:
    scenario = scenario or {}
    progress(3, "Initialising SPH dam-break")

    cfg = sph_solver.SPHConfig()
    # let a scenario nudge the demo size (kept small + stable)
    if scenario.get("sph_particles_target"):
        target = float(scenario["sph_particles_target"])
        area = cfg.reservoir[0] * cfg.reservoir[1]
        cfg.dx = float(np.clip(np.sqrt(area / max(target, 50.0)), 0.022, 0.06))
    if scenario.get("sph_duration_s"):
        cfg.t_end = float(np.clip(scenario["sph_duration_s"], 0.3, 3.0))

    started = time.perf_counter()
    try:
        res = sph_solver.run(cfg, progress=lambda p, m="": progress(3 + int(0.55 * p), m))
    except Exception as exc:  # noqa: BLE001 — genuine instability must surface as failure
        return {"ok": False, "engine": "sph_demo",
                "reason": f"SPH solver failed: {exc}"}

    m = res.metrics
    if not m.get("finite", False):
        return {"ok": False, "engine": "sph_demo",
                "reason": "SPH produced non-finite density/pressure/velocity"}
    if not (m["max_velocity_mps"] > 0 and m["max_displacement_m"] > 1e-3):
        return {"ok": False, "engine": "sph_demo",
                "reason": "SPH particles did not move (no velocity / displacement)"}

    box = res.config.box
    h = m["smoothing_length_m"]
    # particle 2D "volume" (area) for the field reconstruction
    mass = m["particle_mass_kg"]
    for f in res.frames:
        f["vol"] = mass / np.clip(f["rho"], 0.3 * res.config.rho0, 3.0 * res.config.rho0)

    out_dir = config.RESULTS_ROOT.parent / "ujjani_sph"
    (out_dir / "timeline").mkdir(parents=True, exist_ok=True)
    for stale in (out_dir / "timeline").glob("t*.geojson"):
        stale.unlink()

    progress(62, "Reconstructing SPH fields on a grid")
    ny, nx = GRID_NY, GRID_NX
    max_depth = np.zeros((ny, nx))
    max_speed = np.zeros((ny, nx))
    arrival = np.full((ny, nx), -1.0)
    timeline = []
    gx = gy = None

    n_frames = len(res.frames)
    for idx, frame in enumerate(res.frames):
        gx, gy, depth, speed = _rasterise_frame(frame, box, h)
        minute = idx  # frame index -> UI timeline minute (genuine distinct state)
        max_depth = np.maximum(max_depth, depth)
        max_speed = np.maximum(max_speed, speed)
        newly = (arrival < 0) & (depth >= 0.05)
        arrival[newly] = minute
        _write_frame(out_dir / "timeline" / f"t{minute:03d}.geojson",
                     gx, gy, depth, minute, scenario, box)
        timeline.append({
            "minute": minute,
            "sph_time_s": round(float(frame["t"]), 4),
            "sph_step": int(frame["step"]),
            "flooded_cells": int((depth >= 0.05).sum()),
            "flooded_area_km2": round(float((depth >= 0.05).sum())
                                      * abs(FOOTPRINT_DLON / nx * 111000)
                                      * abs(FOOTPRINT_DLAT / ny * 111000) / 1e6, 6),
            "max_depth_m": round(float(depth.max()), 4),
            "max_velocity_mps": round(float(speed.max()), 4),
            "particle_max_speed_mps": round(float(frame["max_speed"]), 4),
        })
        if idx % 5 == 0:
            progress(62 + int(28 * idx / max(n_frames - 1, 1)), f"SPH frame {idx}/{n_frames - 1}")

    progress(92, "Writing GIS products")
    _write_frame(out_dir / "flood_extent.geojson", gx, gy, max_depth,
                 n_frames - 1, scenario, box)
    tif_written = _write_geotiffs(out_dir, gx, gy, max_depth, max_speed, arrival, box)

    # save the genuine particle trajectories for inspection
    np.savez_compressed(
        out_dir / "particles.npz",
        positions0=res.positions0,
        times=np.array([f["t"] for f in res.frames]),
        steps=np.array([f["step"] for f in res.frames]),
        **{f"x_{k}": f["x"] for k, f in enumerate(res.frames)},
        **{f"v_{k}": f["v"] for k, f in enumerate(res.frames)},
        **{f"rho_{k}": f["rho"] for k, f in enumerate(res.frames)},
        **{f"p_{k}": f["p"] for k, f in enumerate(res.frames)},
    )

    runtime = time.perf_counter() - started
    summary = {
        "case_id": "ujjani",
        "model_type": "sph_demo",
        "engine_label": "SPH (demonstration)",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "disclaimer": DISCLAIMER,
        "sph": {
            "formulation": "weakly-compressible SPH (Monaghan/Becker-Teschner)",
            "kernel": "Wendland C2 (2D), support 2h",
            "eos": "Tait, gamma=7",
            "viscosity": "Monaghan artificial viscosity",
            "boundary": "closed box: soft penalty within h + hard containment",
            "integration": "symplectic Euler + XSPH, CFL-limited dt",
            "particle_count": m["particle_count"],
            "timesteps": m["timesteps"],
            "simulation_time_s": m["simulation_time_s"],
            "dt_final_s": m["dt_final_s"],
            "smoothing_length_m": m["smoothing_length_m"],
            "sound_speed_mps": m["sound_speed_mps"],
            "particle_mass_kg": m["particle_mass_kg"],
            "max_density": m["max_density"],
            "min_density": m["min_density"],
            "median_density": m["median_density"],
            "density_relative_error_pct": m["density_relative_error_pct"],
            "max_pressure_pa": m["max_pressure_pa"],
            "max_displacement_m": m["max_displacement_m"],
            "isolated_particles_final": m["isolated_particles_final"],
            "reproducible_seed": res.config.seed,
        },
        "grid": {"nx": nx, "ny": ny, "depth_scale_m": DEPTH_SCALE_M},
        "footprint": {
            "note": "demonstration placement downstream of Ujjani Dam; not georeferenced",
            "lon0": FOOTPRINT_LON0, "lat0": FOOTPRINT_LAT0,
            "dlon": FOOTPRINT_DLON, "dlat": FOOTPRINT_DLAT,
        },
        "available_frames": [pt["minute"] for pt in timeline],
        "flooded_area_km2": timeline[-1]["flooded_area_km2"] if timeline else 0.0,
        "maximum_depth_m": round(float(max_depth.max()), 4),
        "maximum_velocity_mps": round(float(max_speed.max()), 4),
        "runtime_seconds": round(runtime, 2),
        "timeline": timeline,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "engine": "sph_demo",
        "engine_label": "SPH (demonstration)",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "disclaimer": DISCLAIMER,
        "results_dir": str(out_dir),
        "available_frames": summary["available_frames"],
        "summary": summary,
        "runtime_seconds": round(runtime, 2),
        "particle_count": m["particle_count"],
        "timesteps": m["timesteps"],
        "map_frames": len(res.frames),
        "max_depth_m": summary["maximum_depth_m"],
        "max_velocity_mps": summary["maximum_velocity_mps"],
        "max_density": m["max_density"],
        "min_density": m["min_density"],
        "max_displacement_m": m["max_displacement_m"],
        "workdir": str(out_dir),
        "provenance": (
            "Genuine 2D weakly-compressible SPH dam-break (Wendland C2 kernel, Tait "
            "EOS, Monaghan viscosity, CFL-limited symplectic integration) reconstructed "
            "onto a demonstration footprint downstream of Ujjani Dam. Not georeferenced "
            "or validated."
        ),
    }
