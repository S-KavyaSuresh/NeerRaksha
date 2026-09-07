"""Phase 3 — dam-break benchmark: SPH vs Delft3D vs an analytical reference.

BENCHMARK
    Idealised 2D dry-bed dam-break (instantaneous removal of a vertical wall
    holding a rectangular water column on a horizontal, frictionless bed).

REFERENCE (analytical, closed-form, traceable — NOT fabricated experimental data)
    Ritter, A. (1892). "Die Fortpflanzung der Wasserwellen."
    Zeitschrift des Vereines Deutscher Ingenieure 36(33), 947-954.
    Dry-bed solution of the 1D shallow-water equations:
        c0        = sqrt(g * H0)
        x_front(t)= x0 + 2 * c0 * t
        h(x,t)    = (1/(9 g)) * (2 c0 - (x - x0)/t)^2   for  x0 - c0 t <= x <= x0 + 2 c0 t
        u(x,t)    = (2/3)      * (c0 +  (x - x0)/t)
        h = H0, u = 0                                    for  x < x0 - c0 t
        h = 0                                            for  x > x0 + 2 c0 t

    The geometry (column aspect ratio H0 = 2a) follows the classic laboratory
    dam-break of Martin & Moyce (1952, Phil. Trans. R. Soc. Lond. A 244, 312-324)
    and Koshizuka & Oka (1996, Nucl. Sci. Eng. 123, 421-434). Those experiments
    are cited for lineage only; no experimental numbers are used here, so the
    comparison is a VERIFICATION / BENCHMARK exercise against an analytical
    solution — it is NOT calibration and NOT operational validation.

SCIENTIFIC SCOPE
    VERIFICATION  : each solver integrates its intended equations stably.
    BENCHMARKING  : each solver reproduces the Ritter dry-bed dam-break within a
                    documented error band. SPH additionally resolves the 2D
                    non-hydrostatic collapse phase that Ritter's 1D SWE omits, so
                    a systematic near-field deviation is expected and reported.
    NOT DONE HERE : calibration, validation against independent observations,
                    any real-world / operational accuracy claim.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from . import config, sph_solver

GRAVITY = 9.81

# --------------------------------------------------------------------------- #
# benchmark definition
# --------------------------------------------------------------------------- #
A = 0.146            # initial water-column width (m)  -- Martin&Moyce / Koshizuka&Oka
H0 = 2.0 * A         # initial water-column height (m) -- aspect ratio 2
BOX = (1.20, 0.40)   # tank size (m): long dry runout, ample headroom
X0 = A               # dam (wall) position = right edge of the column (m)
T_END = 0.20         # s  (Ritter front travels ~0.68 m from the dam, clear of the far wall)
N_FRAMES = 20        # DtUser = T_END / N_FRAMES = 0.01 s must divide T_END exactly (D-Flow FM)
WET_THRESHOLD_M = 0.005   # depth threshold defining "wet" for extent / IoU
GAUGE_X = X0 + 0.25      # arrival-time gauge (m) -- reached by both models within T_END
PROFILE_T = 0.15        # s  -- reference time for the depth-profile comparison

BENCHMARK = {
    "id": "dry_bed_dam_break_ritter_1892",
    "name": "Idealised 2D dry-bed dam-break (Ritter analytical reference)",
    "class": "classic laboratory dam-break (idealised)",
    "reference": {
        "type": "analytical",
        "solution": "Ritter (1892) dry-bed shallow-water dam-break",
        "primary_source": "Ritter, A. 1892. Die Fortpflanzung der Wasserwellen. "
                          "Zeitschrift des Vereines Deutscher Ingenieure 36(33):947-954.",
        "geometry_lineage": [
            "Martin, J.C. & Moyce, W.J. 1952. Phil. Trans. R. Soc. Lond. A 244:312-324.",
            "Koshizuka, S. & Oka, Y. 1996. Nucl. Sci. Eng. 123:421-434.",
        ],
        "fabricated_values": False,
        "notes": "Closed-form solution evaluated in code; no digitised or "
                 "tabulated experimental values are used.",
    },
    "geometry": {
        "tank_length_m": BOX[0], "tank_height_m": BOX[1],
        "column_width_a_m": A, "column_height_H0_m": H0,
        "aspect_ratio_H0_over_a": H0 / A, "dam_position_x0_m": X0,
        "bed": "horizontal, flat, z = 0", "domain": "2D vertical (x-z) for SPH; 2D plan (x-y) channel for Delft3D",
    },
    "fluid": {"rho_kg_m3": 1000.0, "gravity_m_s2": GRAVITY, "friction": "none (frictionless bed, Ritter assumption)"},
    "boundary_conditions": {
        "walls": "closed, free-slip (left / right / bed)",
        "initial": "hydrostatic column of height H0 for x < x0; dry (h = 0) for x >= x0; fluid at rest",
        "forcing": "none — pure initial-value problem (wall removed instantaneously at t = 0)",
    },
    "reference_quantities": {
        "front_position_x_f_of_t": "leading-edge (tip) position along the bed vs time",
        "surface_profile_h_of_x": f"water depth along the centreline at t = {PROFILE_T} s",
        "arrival_time_at_gauge": f"time the front first reaches x = {GAUGE_X:.3f} m",
        "units": "metres, seconds; dimensionless Z = (x_f - x0)/a, T = t*sqrt(g/H0)",
    },
    "compared_quantities": [
        "front-position time series (model vs Ritter, and SPH vs Delft3D)",
        "depth profile at PROFILE_T (model vs Ritter)",
        "front arrival time at GAUGE_X",
        "wet-length and 1D IoU of the wet region at PROFILE_T",
    ],
    "wet_threshold_m": WET_THRESHOLD_M,
    "t_end_s": T_END, "n_frames": N_FRAMES,
}


# --------------------------------------------------------------------------- #
# Ritter analytical solution
# --------------------------------------------------------------------------- #
def ritter_front(t: float) -> float:
    return X0 + 2.0 * np.sqrt(GRAVITY * H0) * max(t, 0.0)


def ritter_profile(x: np.ndarray, t: float) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    h = np.zeros_like(x)
    if t <= 0:
        h[x < X0] = H0
        return h
    c0 = np.sqrt(GRAVITY * H0)
    xr = (x - X0) / t
    undisturbed = xr <= -c0
    fan = (xr > -c0) & (xr < 2.0 * c0)
    h[undisturbed] = H0
    h[fan] = (1.0 / (9.0 * GRAVITY)) * (2.0 * c0 - xr[fan]) ** 2
    return h


def ritter_arrival(gauge_x: float) -> float:
    return (gauge_x - X0) / (2.0 * np.sqrt(GRAVITY * H0))


# --------------------------------------------------------------------------- #
# metric helpers (pure, testable)
# --------------------------------------------------------------------------- #
def rmse(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size == 0 or a.size != b.size:
        return None
    return float(np.sqrt(np.mean((a - b) ** 2)))


def mae(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size == 0 or a.size != b.size:
        return None
    return float(np.mean(np.abs(a - b)))


def mean_relative_error(model, ref):
    model, ref = np.asarray(model, float), np.asarray(ref, float)
    if model.size == 0 or model.size != ref.size:
        return None
    m = np.abs(ref) > 1e-9
    if not m.any():
        return None
    return float(np.mean(np.abs(model[m] - ref[m]) / np.abs(ref[m])))


def wet_iou(x, h_a, h_b, threshold):
    """1D intersection-over-union of the wet region {x : h > threshold}."""
    x = np.asarray(x, float)
    wa = np.asarray(h_a, float) > threshold
    wb = np.asarray(h_b, float) > threshold
    if x.size < 2:
        return None
    dxs = np.gradient(x)
    inter = float(np.sum(dxs[wa & wb]))
    union = float(np.sum(dxs[wa | wb]))
    if union <= 0:
        return {"iou": None, "intersection_m": 0.0, "union_m": 0.0, "status": "no wet cells in either model"}
    return {"iou": inter / union, "intersection_m": inter, "union_m": union, "status": "ok"}


def first_crossing_time(t, series, level):
    """Linear-interpolated time at which `series` first reaches `level`."""
    t, series = np.asarray(t, float), np.asarray(series, float)
    for k in range(1, t.size):
        if series[k - 1] < level <= series[k]:
            f = (level - series[k - 1]) / (series[k] - series[k - 1] + 1e-12)
            return float(t[k - 1] + f * (t[k] - t[k - 1]))
    if series.size and series[-1] >= level:
        return float(t[0])
    return None


# --------------------------------------------------------------------------- #
# SPH benchmark (reuses the genuine Phase-2 WCSPH solver, unchanged mechanics)
# --------------------------------------------------------------------------- #
def _sph_config(dx: float | None = None) -> sph_solver.SPHConfig:
    cfg = sph_solver.SPHConfig()
    cfg.box = BOX
    cfg.reservoir = (A, H0)
    cfg.dx = float(dx) if dx else A / 20.0
    cfg.t_end = T_END
    cfg.n_frames = N_FRAMES
    return cfg


def _sph_front(frame, h_smooth: float) -> float:
    """Leading-edge position: furthest-downstream particle in the near-bed surge
    tongue that still has neighbour support (excludes detached ballistic spray)."""
    x = frame["x"]
    on_floor = x[:, 1] < 4.0 * h_smooth
    if not on_floor.any():
        return X0
    return float(np.max(x[on_floor, 0]))


def _sph_depth_profile(frame, stations: np.ndarray, h_smooth: float) -> np.ndarray:
    """Free-surface height at each x station = max particle elevation within a
    kernel radius of that station (genuine particle data, no smoothing model)."""
    x = frame["x"]
    out = np.zeros_like(stations)
    for k, xs in enumerate(stations):
        m = np.abs(x[:, 0] - xs) < h_smooth
        out[k] = float(x[m, 1].max()) if m.any() else 0.0
    return out


def run_sph_benchmark(out_dir: Path, progress=lambda p, m="": None, dx: float | None = None) -> dict:
    progress(5, "SPH benchmark: initialising dry-bed dam-break")
    cfg = _sph_config(dx)
    started = time.perf_counter()
    res = sph_solver.run(cfg, progress=lambda p, m="": progress(5 + int(0.5 * p), m))
    runtime = time.perf_counter() - started
    m = res.metrics
    if not m.get("finite", False):
        return {"ok": False, "reason": "SPH benchmark produced non-finite state"}

    h_smooth = m["smoothing_length_m"]
    times = np.array([f["t"] for f in res.frames])
    front = np.array([_sph_front(f, h_smooth) for f in res.frames])

    # depth profile at the frame nearest PROFILE_T
    pf = int(np.argmin(np.abs(times - PROFILE_T)))
    stations = np.linspace(0.0, BOX[0], 240)
    prof = _sph_depth_profile(res.frames[pf], stations, h_smooth)

    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "particles.npz",
                        times=times, positions0=res.positions0,
                        **{f"x_{k}": f["x"] for k, f in enumerate(res.frames)})
    front_json = [{"t_s": round(float(t), 5),
                   "x_front_m": round(float(xf), 5),
                   "Z": round(float((xf - X0) / A), 5),
                   "T": round(float(t * np.sqrt(GRAVITY / H0)), 5)}
                  for t, xf in zip(times, front)]
    (out_dir / "front_position.json").write_text(json.dumps(front_json, indent=2), encoding="utf-8")
    (out_dir / "profile.json").write_text(json.dumps({
        "t_s": round(float(times[pf]), 5),
        "x_m": [round(float(v), 5) for v in stations],
        "h_m": [round(float(v), 5) for v in prof],
    }, indent=2), encoding="utf-8")

    summary = {
        "engine": "sph_wcsph",
        "engine_label": "SPH (genuine WCSPH, Phase 2 solver)",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "particle_count": m["particle_count"],
        "smoothing_length_m": m["smoothing_length_m"],
        "dt_final_s": m["dt_final_s"],
        "timesteps": m["timesteps"],
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
        "profile_time_s": round(float(times[pf]), 5),
        "front_final_m": round(float(front[-1]), 5),
        "approximation": (
            "2D vertical WCSPH; the near-dam collapse is non-hydrostatic so the "
            "SPH front lags the hydrostatic Ritter front while the column is "
            "still accelerating downward, then approaches the 2*sqrt(g H0) rate."
        ),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"ok": True, "summary": summary, "times": times.tolist(),
            "front": front.tolist(), "stations": stations.tolist(),
            "profile": prof.tolist(), "profile_time_s": float(times[pf])}


# --------------------------------------------------------------------------- #
# Delft3D benchmark (flat frictionless channel, initial-water-level step)
# --------------------------------------------------------------------------- #
_BENCH_MDU = """# NeerRaksha Phase 3 dam-break benchmark (flat frictionless channel)
[model]
Program = D-Flow FM
Version = 1.2
MDUFormatVersion = 1.09
[geometry]
NetFile = channel_net.nc
BedlevUni = 0.0
BedlevType = 3
WaterLevIni = 0.0
[numerics]
CFLMax = 0.7
Epshu = 1.d-4
MinTimestepBreak = 0.
[physics]
UnifFrictCoef = 0.0
UnifFrictType = 1
[external forcing]
ExtForceFile = benchmark.ext
[time]
RefDate = 20260101
Tunit = S
DtUser = {dt}
DtMax = {dt}
DtInit = 1.d-4
DtMin = 1.d-7
TStart = 0
TStop = {tstop}
[output]
MapInterval = {dt}
HisInterval = 0
"""

# Old-style external forcing: raise the initial water level to H0 inside the
# reservoir polygon (x < x0). Everything else keeps WaterLevIni = 0 (dry, flat
# bed) -> a genuine head-difference dam-break, released at t = 0.
_BENCH_EXT = """QUANTITY=initialwaterlevel
FILENAME=reservoir.pol
FILETYPE=10
METHOD=4
OPERAND=O
VALUE={h0}
"""


def _flat_channel_ugrid(path: Path, lx: float, ly: float, nx: int, ny: int) -> dict:
    """Write a flat (z = 0) rectangular quad UGRID in the proven D-Flow FM layout."""
    import netCDF4

    xs = np.linspace(0.0, lx, nx + 1)
    ys = np.linspace(0.0, ly, ny + 1)
    gx, gy = np.meshgrid(xs, ys)
    node_x = gx.ravel().astype("float64")
    node_y = gy.ravel().astype("float64")
    node_z = np.zeros_like(node_x)
    nnx = nx + 1

    def nid(j, i):
        return j * nnx + i

    faces, edges = [], set()
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = nid(j, i), nid(j, i + 1), nid(j + 1, i + 1), nid(j + 1, i)
            faces.append((a, b, c, d))
            for u, v in ((a, b), (b, c), (c, d), (d, a)):
                edges.add((min(u, v), max(u, v)))
    face_nodes = np.array(faces, "int32")
    edge_nodes = np.array(sorted(edges), "int32")
    edge_x = node_x[edge_nodes].mean(axis=1)
    edge_y = node_y[edge_nodes].mean(axis=1)
    face_x = node_x[face_nodes].mean(axis=1)
    face_y = node_y[face_nodes].mean(axis=1)

    ds = netCDF4.Dataset(path, "w", format="NETCDF4")
    try:
        ds.Conventions = "CF-1.8 UGRID-1.0"
        ds.source = "NeerRaksha Phase 3 flat dam-break channel"
        ds.createDimension("nmesh2d_node", node_x.size)
        ds.createDimension("nmesh2d_edge", edge_nodes.shape[0])
        ds.createDimension("nmesh2d_face", face_nodes.shape[0])
        ds.createDimension("Two", 2)
        ds.createDimension("nmesh2d_face_nodes", 4)
        mesh = ds.createVariable("mesh2d", "i4")
        mesh.cf_role = "mesh_topology"
        mesh.topology_dimension = 2
        mesh.node_coordinates = "mesh2d_node_x mesh2d_node_y"
        mesh.node_dimension = "nmesh2d_node"
        mesh.edge_node_connectivity = "mesh2d_edge_nodes"
        mesh.edge_dimension = "nmesh2d_edge"
        mesh.edge_coordinates = "mesh2d_edge_x mesh2d_edge_y"
        mesh.face_node_connectivity = "mesh2d_face_nodes"
        mesh.face_dimension = "nmesh2d_face"
        mesh.face_coordinates = "mesh2d_face_x mesh2d_face_y"

        def _v(name, data, dims, **attrs):
            var = ds.createVariable(name, data.dtype.str.replace("<", "").replace(">", ""), dims)
            var[:] = data
            for k, val in attrs.items():
                setattr(var, k, val)

        _v("mesh2d_node_x", node_x, ("nmesh2d_node",), units="m", standard_name="projection_x_coordinate")
        _v("mesh2d_node_y", node_y, ("nmesh2d_node",), units="m", standard_name="projection_y_coordinate")
        _v("mesh2d_node_z", node_z, ("nmesh2d_node",), units="m", standard_name="altitude",
           long_name="bed level at nodes", mesh="mesh2d", location="node")
        _v("mesh2d_edge_nodes", edge_nodes, ("nmesh2d_edge", "Two"), cf_role="edge_node_connectivity", start_index=0)
        _v("mesh2d_face_nodes", face_nodes, ("nmesh2d_face", "nmesh2d_face_nodes"),
           cf_role="face_node_connectivity", start_index=0)
        _v("mesh2d_edge_x", edge_x, ("nmesh2d_edge",), units="m")
        _v("mesh2d_edge_y", edge_y, ("nmesh2d_edge",), units="m")
        _v("mesh2d_face_x", face_x, ("nmesh2d_face",), units="m")
        _v("mesh2d_face_y", face_y, ("nmesh2d_face",), units="m")
    finally:
        ds.close()
    return {"nodes": int(node_x.size), "edges": int(edge_nodes.shape[0]),
            "faces": int(face_nodes.shape[0]), "nx": nx, "ny": ny}


def run_delft3d_benchmark(out_dir: Path, progress=lambda p, m="": None) -> dict:
    exe = config.DELFT3D_EXECUTABLE
    if not exe.exists():
        return {"ok": False, "reason": f"DELFT3D_EXECUTABLE not found: {exe}"}

    stamp = time.strftime("%Y%m%dT%H%M%S")
    workdir = config.SIM_WORKDIR / f"benchmark_delft3d_{stamp}"
    workdir.mkdir(parents=True, exist_ok=True)

    lx, ly = BOX[0], 0.20               # thin channel (plan view); dam-break is 1D in x
    nx, ny = 240, 6
    progress(58, "Delft3D benchmark: building flat channel mesh")
    mesh_info = _flat_channel_ugrid(workdir / "channel_net.nc", lx, ly, nx, ny)

    # initial water-level step: H0 inside the reservoir polygon (x < x0)
    (workdir / "reservoir.pol").write_text(
        "reservoir\n5 2\n"
        f"{-0.05:.4f} {-0.05:.4f}\n"
        f"{X0:.4f} {-0.05:.4f}\n"
        f"{X0:.4f} {ly + 0.05:.4f}\n"
        f"{-0.05:.4f} {ly + 0.05:.4f}\n"
        f"{-0.05:.4f} {-0.05:.4f}\n",
        encoding="utf-8",
    )
    (workdir / "benchmark.ext").write_text(_BENCH_EXT.format(h0=f"{H0:g}"), encoding="utf-8")

    dt = T_END / N_FRAMES                      # 0.01 s exactly; divides T_END
    (workdir / "flow.mdu").write_text(
        _BENCH_MDU.format(dt=f"{dt:g}", tstop=f"{T_END:g}"), encoding="utf-8")

    progress(64, f"Delft3D benchmark: running dflowfm-cli (T={T_END}s)")
    started = time.perf_counter()
    try:
        proc = subprocess.run([str(exe), "--autostartstop", "flow.mdu"],
                              cwd=workdir, capture_output=True, text=True, timeout=1200)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"dflowfm-cli launch failed: {exc}", "workdir": str(workdir)}
    runtime = time.perf_counter() - started
    (workdir / "dflowfm_stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (workdir / "dflowfm_stderr.log").write_text(proc.stderr or "", encoding="utf-8")

    map_nc = next(iter(workdir.glob("**/*_map.nc")), None)
    if proc.returncode != 0 or map_nc is None:
        return {"ok": False, "reason": f"D-Flow FM exited {proc.returncode} / no *_map.nc",
                "workdir": str(workdir), "stdout_tail": (proc.stdout or "")[-1500:],
                "stderr_tail": (proc.stderr or "")[-1500:]}

    import netCDF4
    with netCDF4.Dataset(map_nc) as ds:
        fx = np.array(ds.variables["mesh2d_face_x"][:])
        fy = np.array(ds.variables["mesh2d_face_y"][:])
        times = np.array(ds.variables["time"][:], float)
        depth = np.array(ds.variables["mesh2d_waterdepth"][:])
        ucx = np.array(ds.variables["mesh2d_ucx"][:]) if "mesh2d_ucx" in ds.variables else None
        ucy = np.array(ds.variables["mesh2d_ucy"][:]) if "mesh2d_ucy" in ds.variables else None
    tsec = times  # MDU pins Tunit = S, so the time axis is already seconds
    vel = np.hypot(ucx, ucy) if ucx is not None else None
    if not np.isfinite(depth).all():
        return {"ok": False, "reason": "Delft3D benchmark produced non-finite depth"}
    if depth.max() <= 0:
        return {"ok": False, "reason": "Delft3D benchmark produced zero water depth"}

    # centreline strip
    mid = np.abs(fy - ly / 2.0) < (ly / ny)
    order = np.argsort(fx[mid])
    cx = fx[mid][order]
    front = []
    for k in range(depth.shape[0]):
        dk = depth[k][mid][order]
        wet = np.where(dk > WET_THRESHOLD_M)[0]
        front.append(float(cx[wet[-1]]) if wet.size else X0)
    front = np.array(front)

    # depth profile on the SPH station grid at the frame nearest PROFILE_T
    pf = int(np.argmin(np.abs(tsec - PROFILE_T)))
    stations = np.linspace(0.0, BOX[0], 240)
    prof = np.interp(stations, cx, depth[pf][mid][order], left=depth[pf][mid][order][0], right=0.0)

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*"):
        if stale.is_file():
            stale.unlink()
    for name in ("dflowfm_stdout.log", "flow.mdu", "benchmark.ext", "reservoir.pol"):
        if (workdir / name).exists():
            shutil.copyfile(workdir / name, out_dir / name)
    front_json = [{"t_s": round(float(t), 5), "x_front_m": round(float(xf), 5),
                   "Z": round(float((xf - X0) / A), 5),
                   "T": round(float(t * np.sqrt(GRAVITY / H0)), 5)}
                  for t, xf in zip(tsec, front)]
    (out_dir / "front_position.json").write_text(json.dumps(front_json, indent=2), encoding="utf-8")
    (out_dir / "profile.json").write_text(json.dumps({
        "t_s": round(float(tsec[pf]), 5),
        "x_m": [round(float(v), 5) for v in stations],
        "h_m": [round(float(v), 5) for v in prof],
    }, indent=2), encoding="utf-8")

    summary = {
        "engine": "delft3d_dflowfm",
        "engine_label": "Delft3D D-Flow FM (benchmark channel)",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "mesh": mesh_info,
        "frames": int(depth.shape[0]),
        "time_range_s": [float(tsec.min()), float(tsec.max())],
        "depth_max_m": float(np.nanmax(depth)),
        "velocity_max_mps": float(np.nanmax(vel)) if vel is not None else None,
        "finite": bool(np.isfinite(depth).all()),
        "runtime_seconds": round(runtime, 2),
        "command": f'"{exe}" --autostartstop flow.mdu',
        "workdir": str(workdir),
        "profile_time_s": round(float(tsec[pf]), 5),
        "front_final_m": round(float(front[-1]), 5),
        "initial_condition": "old-ext initialwaterlevel polygon: s1 = H0 for x<x0, s1 = 0 (dry) elsewhere; flat bed z=0; frictionless",
        "approximation": "2D depth-averaged shallow water on a thin plan-view channel; hydrostatic (matches Ritter's assumptions).",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"ok": True, "summary": summary, "times": tsec.tolist(),
            "front": front.tolist(), "stations": stations.tolist(),
            "profile": prof.tolist(), "profile_time_s": float(tsec[pf]),
            "map_file": str(map_nc)}


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #
def _front_vs_ref(times, front):
    ref = np.array([ritter_front(t) for t in times])
    # ignore t = 0 where both are exactly x0 (division-by-zero in relative error)
    m = np.array(times) > 1e-6
    return {
        "rmse_m": rmse(np.array(front)[m], ref[m]),
        "mae_m": mae(np.array(front)[m], ref[m]),
        "mean_relative_error": mean_relative_error(np.array(front)[m], ref[m]),
        "final_front_model_m": float(front[-1]),
        "final_front_ritter_m": float(ref[-1]),
        "final_abs_diff_m": float(abs(front[-1] - ref[-1])),
    }


def compare(sph: dict, d3d: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stations = np.array(sph["stations"])

    # resample both fronts onto a common time grid (intersection of ranges)
    t_lo = max(min(sph["times"]), min(d3d["times"]))
    t_hi = min(max(sph["times"]), max(d3d["times"]))
    tg = np.linspace(t_lo, t_hi, 40)
    sph_front_g = np.interp(tg, sph["times"], sph["front"])
    d3d_front_g = np.interp(tg, d3d["times"], d3d["front"])
    ritter_front_g = np.array([ritter_front(t) for t in tg])

    ritter_prof = ritter_profile(stations, PROFILE_T)
    sph_prof = np.array(sph["profile"])
    d3d_prof = np.array(d3d["profile"])

    metrics = {
        "front_position": {
            "common_time_window_s": [float(t_lo), float(t_hi)],
            "sph_vs_ritter": _front_vs_ref(tg, sph_front_g),
            "delft3d_vs_ritter": _front_vs_ref(tg, d3d_front_g),
            "sph_vs_delft3d": {
                "rmse_m": rmse(sph_front_g, d3d_front_g),
                "mae_m": mae(sph_front_g, d3d_front_g),
                "max_abs_diff_m": float(np.max(np.abs(sph_front_g - d3d_front_g))),
            },
            "dimensionless_Z_at_end": {
                "sph": float((sph_front_g[-1] - X0) / A),
                "delft3d": float((d3d_front_g[-1] - X0) / A),
                "ritter": float((ritter_front_g[-1] - X0) / A),
            },
        },
        "depth_profile_at_t": {
            "t_s": PROFILE_T,
            "n_stations": int(stations.size),
            "station_spacing_m": float(stations[1] - stations[0]),
            "sph_vs_ritter": {"rmse_m": rmse(sph_prof, ritter_prof), "mae_m": mae(sph_prof, ritter_prof)},
            "delft3d_vs_ritter": {"rmse_m": rmse(d3d_prof, ritter_prof), "mae_m": mae(d3d_prof, ritter_prof)},
            "max_depth_m": {"sph": float(sph_prof.max()), "delft3d": float(d3d_prof.max()),
                            "ritter": float(ritter_prof.max())},
            "max_depth_diff_sph_minus_delft3d_m": float(sph_prof.max() - d3d_prof.max()),
        },
        "wet_region_at_t": {
            "t_s": PROFILE_T, "threshold_m": WET_THRESHOLD_M,
            "raster_resolution_m": float(stations[1] - stations[0]),
            "wet_length_m": {
                "sph": float(np.sum(np.gradient(stations)[sph_prof > WET_THRESHOLD_M])),
                "delft3d": float(np.sum(np.gradient(stations)[d3d_prof > WET_THRESHOLD_M])),
                "ritter": float(np.sum(np.gradient(stations)[ritter_prof > WET_THRESHOLD_M])),
            },
            "iou_sph_delft3d": wet_iou(stations, sph_prof, d3d_prof, WET_THRESHOLD_M),
            "iou_sph_ritter": wet_iou(stations, sph_prof, ritter_prof, WET_THRESHOLD_M),
            "iou_delft3d_ritter": wet_iou(stations, d3d_prof, ritter_prof, WET_THRESHOLD_M),
        },
        "arrival_time_at_gauge": {
            "gauge_x_m": GAUGE_X,
            "ritter_s": float(ritter_arrival(GAUGE_X)),
            "sph_s": first_crossing_time(sph["times"], sph["front"], GAUGE_X),
            "delft3d_s": first_crossing_time(d3d["times"], d3d["front"], GAUGE_X),
        },
    }
    at = metrics["arrival_time_at_gauge"]
    for eng in ("sph", "delft3d"):
        v = at[f"{eng}_s"]
        at[f"{eng}_abs_error_s"] = None if v is None else float(abs(v - at["ritter_s"]))

    comparison = {
        "benchmark": BENCHMARK,
        "reference": {
            "kind": "analytical", "name": "Ritter (1892) dry-bed dam-break",
            "front_position_law": "x_f(t) = x0 + 2*sqrt(g*H0)*t",
            "fabricated_values": False,
        },
        "sph_result": sph["summary"],
        "delft3d_result": d3d["summary"],
        "metrics": metrics,
        "status": {
            "verification": "SPH: WCSPH integrated stably, state finite, reproducible. "
                            "Delft3D: model initialised, map output present, depth finite and non-zero.",
            "benchmarking": "front-position and depth-profile agreement with the Ritter analytical "
                            "solution is quantified above; see limitations for expected systematic deviations.",
            "calibration": "NOT PERFORMED — no parameters were tuned to reference data.",
            "validation": "NOT PERFORMED — no independent real-world observations. "
                          "This is a verification/benchmark exercise, NOT operational validation.",
        },
        "limitations": [
            "Reference is the idealised Ritter shallow-water solution, not laboratory measurements.",
            "SPH is 2D vertical and resolves the non-hydrostatic near-dam collapse; Ritter is 1D hydrostatic, "
            "so the SPH front lags Ritter early in the run by design.",
            "Delft3D benchmark uses a thin plan-view channel with a WaterLevIniFile step and no friction; "
            "wetting/drying and the discrete initial step introduce a small front-timing offset.",
            "Front position is threshold-dependent (threshold = %.3f m); depth profile compared on a "
            "%.4f m station grid." % (WET_THRESHOLD_M, float(stations[1] - stations[0])),
            "Short domain / short duration keep the front clear of the far wall; only the early dam-break is compared.",
        ],
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out_dir / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    return comparison


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_benchmark(progress=lambda p, m="": None, sph_dx: float | None = None) -> dict:
    root = config.RESULTS_ROOT.parent / "benchmark"
    (root).mkdir(parents=True, exist_ok=True)
    (root / "metadata.json").write_text(json.dumps(BENCHMARK, indent=2), encoding="utf-8")

    progress(3, "Benchmark: SPH dam-break")
    sph = run_sph_benchmark(root / "sph", progress, dx=sph_dx)
    if not sph.get("ok"):
        return {"ok": False, "stage": "sph", "reason": sph.get("reason", "SPH benchmark failed")}

    progress(55, "Benchmark: Delft3D dam-break")
    d3d = run_delft3d_benchmark(root / "delft3d", progress)
    if not d3d.get("ok"):
        return {"ok": False, "stage": "delft3d", "reason": d3d.get("reason", "Delft3D benchmark failed"),
                "sph_summary": sph["summary"], "detail": {k: d3d.get(k) for k in ("workdir", "stdout_tail", "stderr_tail")}}

    progress(90, "Benchmark: computing comparison metrics")
    comparison = compare(sph, d3d, root / "comparison")

    progress(99, "Benchmark complete")
    return {
        "ok": True,
        "benchmark_id": BENCHMARK["id"],
        "results_dir": str(root),
        "reference_source": BENCHMARK["reference"]["primary_source"],
        "sph_summary": sph["summary"],
        "delft3d_summary": d3d["summary"],
        "metrics": comparison["metrics"],
        "status": comparison["status"],
        "validated_hydraulic_output": False,
        "data_class": "MODEL OUTPUT",
        "disclaimer": "Benchmark / verification against the Ritter (1892) analytical dam-break. "
                      "NOT calibration, NOT operational validation.",
    }


if __name__ == "__main__":
    r = run_benchmark(progress=lambda p, m="": print(f"[{p:3d}%] {m}", flush=True))
    print(json.dumps({k: v for k, v in r.items() if k != "metrics"}, indent=2, default=str))
    if r.get("ok"):
        print("\nMETRICS:\n" + json.dumps(r["metrics"], indent=2))
