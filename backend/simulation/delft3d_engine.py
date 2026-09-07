"""Delft3D D-Flow FM adapter — Phase 1: automatic discharge forcing.

Pipeline:
  scenario
    -> create work directory
    -> stage the proven UGRID mesh as grid_net.nc
    -> generate forcing:  dam_boundary.pli, dam_boundary_0001.tim, dam_break.ext
    -> generate flow.mdu  (references mesh + external forcing + duration)
    -> run  dflowfm-cli.exe --autostartstop flow.mdu
    -> detect failure (return code / no open boundary cells / no *_map.nc)
    -> verify non-zero water depth + velocity in the map file
    -> postprocess.process(map_nc, out_dir, scenario)  -> GeoTIFF + GeoJSON + summary
    -> return structured metadata

The forcing configuration mirrors the proven test in
``data/processed/simulations/delft3d_forcing_test`` (discharge boundary on the
left edge of the mesh, old-style external-forcing file, no BedLevType keyword).

This produces a Delft3D D-Flow FM DEMONSTRATION configuration. The boundary is an
integration boundary on the mesh edge, NOT the physical Ujjani dam, and the
result is NOT validated for operational prediction.

If Delft3D is explicitly requested and fails, this returns ``ok=False`` with a
clear reason. It never fabricates hydraulic results and never silently swaps in
the approximate solver.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config

DISCLAIMER = (
    "Delft3D D-Flow FM MODEL OUTPUT — demonstration configuration "
    "(integration boundary on the mesh edge, not the physical Ujjani dam). "
    "Not validated for operational prediction."
)

MDU_TEMPLATE = """# NeerRaksha Delft3D forcing run (auto-generated) — demonstration configuration
[model]
Program = D-Flow FM
Version = 1.2
MDUFormatVersion = 1.09

[geometry]
NetFile = {net_file}

[numerics]
CFLMax = 0.7

[physics]
UnifFrictCoef = 0.023
UnifFrictType = 1

[time]
RefDate = 20260101
Tunit = S
DtUser = {dt_user}
TStart = 0
TStop = {tstop}

[external forcing]
ExtForceFile = dam_break.ext

[output]
MapInterval = {map_interval}
HisInterval = 0
"""

EXT_TEMPLATE = """QUANTITY = dischargebnd
FILENAME = dam_boundary.pli
FILETYPE = 9
METHOD   = 3
OPERAND  = O
"""


# --------------------------------------------------------------------------- #
# forcing generation
# --------------------------------------------------------------------------- #
def _hydrograph(scenario: dict, duration_min: float) -> list[tuple[float, float]]:
    """Return [(time_minutes, discharge_m3s), ...] spanning 0..duration_min."""
    custom = scenario.get("hydrograph")
    if isinstance(custom, (list, tuple)) and len(custom) >= 2:
        pts = []
        for row in custom:
            if isinstance(row, dict):
                t = float(row.get("t_min", row.get("time_min", row.get("minute"))))
                q = float(row.get("q_m3s", row.get("discharge_m3s", row.get("q"))))
            else:
                t, q = float(row[0]), float(row[1])
            pts.append((t, max(0.0, q)))
        pts.sort()
        return pts

    peak = float(scenario.get("peak_discharge_m3s", 3000.0))
    shape = config.DELFT3D_DEMO_HYDROGRAPH  # fractions of duration, absolute q
    base_peak = max(q for _, q in shape) or 1.0
    return [(round(frac * duration_min, 4), round(q * peak / base_peak, 3))
            for frac, q in shape]


def _write_forcing(workdir: Path, hydrograph: list[tuple[float, float]]) -> dict:
    pts = config.DELFT3D_BOUNDARY_POINTS
    pli = workdir / "dam_boundary.pli"
    pli.write_text(
        f"{config.DELFT3D_BOUNDARY_NAME}\n{len(pts)} 2\n"
        + "\n".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "\n",
        encoding="utf-8",
    )
    tim = workdir / "dam_boundary_0001.tim"
    tim.write_text(
        "\n".join(f"{t:g}\t{q:g}" for t, q in hydrograph) + "\n",
        encoding="utf-8",
    )
    (workdir / "dam_break.ext").write_text(EXT_TEMPLATE, encoding="utf-8")
    return {"pli": str(pli), "tim": str(tim), "ext": str(workdir / "dam_break.ext")}


def _stage_mesh(workdir: Path) -> tuple[Path, dict]:
    """Copy the proven UGRID mesh into the work directory as grid_net.nc."""
    src = config.DELFT3D_UGRID
    if not src.exists():
        raise FileNotFoundError(
            f"Proven Delft3D UGRID mesh not found: {src}. "
            "Set DELFT3D_UGRID to the generated *_net.nc."
        )
    dst = workdir / "grid_net.nc"
    shutil.copyfile(src, dst)

    import netCDF4

    with netCDF4.Dataset(dst) as ds:
        nodes = int(ds.dimensions["nmesh2d_node"].size) if "nmesh2d_node" in ds.dimensions \
            else int(ds.variables["mesh2d_node_x"].shape[0])
        faces = int(ds.dimensions["nmesh2d_face"].size) if "nmesh2d_face" in ds.dimensions \
            else int(ds.variables["mesh2d_face_x"].shape[0])
        edges = int(ds.dimensions["nmesh2d_edge"].size) if "nmesh2d_edge" in ds.dimensions else None
        fx = np.array(ds.variables["mesh2d_face_x"][:])
        fy = np.array(ds.variables["mesh2d_face_y"][:])
    return dst, {
        "source": str(src), "nodes": nodes, "edges": edges, "faces": faces,
        "x_range": [float(fx.min()), float(fx.max())],
        "y_range": [float(fy.min()), float(fy.max())],
    }


# --------------------------------------------------------------------------- #
# failure detection / verification
# --------------------------------------------------------------------------- #
def _log_text(workdir: Path, proc_stdout: str) -> str:
    parts = [proc_stdout or ""]
    for candidate in ("dflowfm_stdout.log", "DFM_OUTPUT_flow/flow.dia", "unstruc.dia"):
        p = workdir / candidate
        if p.exists():
            try:
                parts.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(parts)


def _init_failed(log: str) -> str | None:
    low = log.lower()
    if "0 nr of open bndcells" in low:
        return "Delft3D opened 0 boundary cells — discharge forcing was not applied."
    if "model initialization was successful" not in low and "modelinit finished" not in low:
        return "Delft3D did not report successful model initialization."
    return None


def _verify_map(map_nc: Path) -> dict:
    import netCDF4

    with netCDF4.Dataset(map_nc) as ds:
        missing = [v for v in ("mesh2d_waterdepth", "mesh2d_ucx", "mesh2d_ucy")
                   if v not in ds.variables]
        if missing:
            return {"ok": False, "reason": f"map file missing variables: {missing}"}
        depth = np.array(ds.variables["mesh2d_waterdepth"][:])
        ucx = np.array(ds.variables["mesh2d_ucx"][:])
        ucy = np.array(ds.variables["mesh2d_ucy"][:])
        times = np.array(ds.variables["time"][:]) if "time" in ds.variables else np.array([0.0])
    vel = np.hypot(ucx, ucy)
    dmax = float(np.nanmax(depth)) if depth.size else 0.0
    vmax = float(np.nanmax(vel)) if vel.size else 0.0
    if not (dmax > 0.0):
        return {"ok": False, "reason": f"Delft3D produced zero water depth (max={dmax}).",
                "max_depth_m": dmax, "max_velocity_mps": vmax}
    if not (vmax > 0.0):
        return {"ok": False, "reason": f"Delft3D produced zero velocity (max={vmax}).",
                "max_depth_m": dmax, "max_velocity_mps": vmax}
    return {"ok": True, "frames": int(depth.shape[0]),
            "max_depth_m": dmax, "max_velocity_mps": vmax,
            "time_range_s": [float(times.min()), float(times.max())]}


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def run(scenario: dict, progress=lambda pct, msg="": None) -> dict:
    scenario = scenario or {}

    exe = config.DELFT3D_EXECUTABLE
    if not exe.exists():
        progress(5, "Delft3D executable not found")
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"DELFT3D_EXECUTABLE not found: {exe}",
                "hint": "Set the DELFT3D_EXECUTABLE environment variable."}

    duration_min = float(scenario.get("simulation_duration_minutes", config.DELFT3D_DURATION_MIN))
    duration_min = max(1.0, min(duration_min, 180.0))
    tstop_s = int(round(duration_min * 60))
    map_interval_s = int(scenario.get("map_interval_s", config.DELFT3D_MAP_INTERVAL_S))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    workdir = config.SIM_WORKDIR / f"delft3d_{stamp}"
    workdir.mkdir(parents=True, exist_ok=True)

    progress(15, "Staging proven UGRID mesh")
    try:
        net_file, mesh_info = _stage_mesh(workdir)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"mesh staging failed: {exc}", "workdir": str(workdir)}

    progress(25, "Generating Delft3D discharge forcing")
    hydrograph = _hydrograph(scenario, duration_min)
    forcing = _write_forcing(workdir, hydrograph)

    (workdir / "flow.mdu").write_text(
        MDU_TEMPLATE.format(
            net_file=net_file.name, dt_user=config.DELFT3D_DT_USER_S,
            tstop=tstop_s, map_interval=map_interval_s,
        ),
        encoding="utf-8",
    )

    progress(40, f"Running dflowfm-cli.exe (T={tstop_s}s)")
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(exe), "--autostartstop", "flow.mdu"],
            cwd=workdir, capture_output=True, text=True, timeout=3600,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"dflowfm-cli launch failed: {exc}", "workdir": str(workdir)}
    runtime_s = time.perf_counter() - started

    (workdir / "dflowfm_stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (workdir / "dflowfm_stderr.log").write_text(proc.stderr or "", encoding="utf-8")
    log = _log_text(workdir, proc.stdout or "")

    init_problem = _init_failed(log)
    map_nc = next(iter(workdir.glob("**/*_map.nc")), None)

    if proc.returncode != 0 or map_nc is None or init_problem:
        return {
            "ok": False,
            "engine": "delft3d_dflowfm",
            "reason": init_problem or f"D-Flow FM exited {proc.returncode} or produced no *_map.nc",
            "returncode": proc.returncode,
            "workdir": str(workdir),
            "runtime_seconds": runtime_s,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }

    progress(70, "Verifying hydraulic fields")
    check = _verify_map(map_nc)
    if not check["ok"]:
        return {
            "ok": False, "engine": "delft3d_dflowfm",
            "reason": check["reason"], "workdir": str(workdir),
            "map_file": str(map_nc), "runtime_seconds": runtime_s,
        }

    progress(80, "Post-processing D-Flow FM map output")
    from . import postprocess

    out_dir = config.DELFT3D_RESULTS
    try:
        summary = postprocess.process(map_nc, out_dir, scenario)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"postprocessing failed: {exc}", "workdir": str(workdir),
                "map_file": str(map_nc)}

    progress(97, "Delft3D run complete")
    return {
        "ok": True,
        "engine": "delft3d_dflowfm",
        "engine_label": "Delft3D D-Flow FM",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "disclaimer": DISCLAIMER,
        "results_dir": str(out_dir),
        "available_frames": summary.get("available_frames", []),
        "summary": summary,
        "runtime_seconds": runtime_s,
        "mesh": mesh_info,
        "workdir": str(workdir),
        "map_file": str(map_nc),
        "hydrograph": hydrograph,
        "forcing_files": forcing,
        "command": f'"{exe}" --autostartstop flow.mdu',
        "map_frames": check["frames"],
        "max_depth_m": check["max_depth_m"],
        "max_velocity_mps": check["max_velocity_mps"],
        "provenance": (
            "Delft3D D-Flow FM run on the proven Ujjani demonstration mesh with an "
            "auto-generated discharge boundary (mesh-edge integration boundary, "
            "not the physical dam)."
        ),
    }
