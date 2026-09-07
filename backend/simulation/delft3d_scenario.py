"""Phase 4 Delft3D adapter — physically-located breach release at the Ujjani dam.

Difference from the Phase-1 engine (which is FROZEN and untouched): the release is
an **internal discharge source point at the actual dam coordinate**
(18.0739 N, 75.1200 E -> EPSG:32643), on the real Ujjani terrain mesh, driven by
the parameterised breach hydrograph — not an artificial mesh-edge boundary.

D-Flow FM source-sink mechanism (old external forcing):
    QUANTITY = discharge_salinity_temperature_sorsin
    FILENAME = breach_source.pli   (2 points: sink end placed far OUTSIDE the mesh,
                                    source end at the dam -> inflow only)
    <stem>.tim : minutes  discharge_m3s     (the breach hydrograph)

Honest limitation, documented in the result: the Ujjani demonstration mesh is
~180 m resolution, so the breach is represented as a point release whose
magnitude carries the breach width/depth (via the hydrograph) — the breach
opening geometry is NOT resolved by the mesh. A true resolved internal breach
needs a locally refined Phase-4 mesh.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config
from . import scenario as scen

MDU = """# NeerRaksha Phase 4 — Ujjani dam-break: internal breach source at the dam
[model]
Program = D-Flow FM
Version = 1.2
MDUFormatVersion = 1.09
[geometry]
NetFile = ujjani_net.nc
BedlevUni = {bedlevuni:g}
BedlevType = 3
WaterLevIni = {waterlevini:g}
[numerics]
CFLMax = 0.7
Epshu = 1.d-3
MinTimestepBreak = 0.
[physics]
UnifFrictCoef = {manning:g}
UnifFrictType = 1
[external forcing]
ExtForceFile = breach.ext
[time]
RefDate = 20260101
Tunit = S
DtUser = {dt:g}
DtMax = {dt:g}
DtInit = 1.
TStart = 0
TStop = {tstop:g}
[output]
MapInterval = {dt:g}
HisInterval = 0
"""

EXT = """QUANTITY=discharge_salinity_temperature_sorsin
FILENAME=breach_source.pli
FILETYPE=9
METHOD=1
OPERAND=O
AREA=0.0
"""


def _mesh_info(net: Path) -> dict:
    import netCDF4

    with netCDF4.Dataset(net) as ds:
        nz = np.array(ds.variables["mesh2d_node_z"][:])
        fx = np.array(ds.variables["mesh2d_face_x"][:])
        fy = np.array(ds.variables["mesh2d_face_y"][:])
        nodes = int(ds.dimensions["nmesh2d_node"].size) if "nmesh2d_node" in ds.dimensions \
            else int(ds.variables["mesh2d_node_x"].shape[0])
        faces = int(ds.dimensions["nmesh2d_face"].size) if "nmesh2d_face" in ds.dimensions \
            else int(fx.shape[0])
        edges = int(ds.dimensions["nmesh2d_edge"].size) if "nmesh2d_edge" in ds.dimensions else None
    return {
        "source": str(scen.UJJANI_UGRID), "nodes": nodes, "edges": edges, "faces": faces,
        "bed_level_min_m": float(np.nanmin(nz)), "bed_level_max_m": float(np.nanmax(nz)),
        "x_range_m": [float(fx.min()), float(fx.max())],
        "y_range_m": [float(fy.min()), float(fy.max())],
        "approx_cell_size_m": float(np.sqrt(((fx.max() - fx.min()) * (fy.max() - fy.min())) / max(faces, 1))),
        "note": "Phase-1 Ujjani demonstration mesh (real DEM bed levels); ~180 m cells do not resolve the breach opening.",
    }


def run(sc: scen.UjjaniScenario, hydrograph: dict, out_dir: Path,
        progress=lambda p, m="": None) -> dict:
    exe = config.DELFT3D_EXECUTABLE
    if not exe.exists():
        return {"ok": False, "engine": "delft3d_dflowfm", "reason": f"DELFT3D_EXECUTABLE not found: {exe}"}
    if not scen.UJJANI_UGRID.exists():
        return {"ok": False, "engine": "delft3d_dflowfm", "reason": f"Ujjani UGRID not found: {scen.UJJANI_UGRID}"}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    workdir = config.SIM_WORKDIR / f"ujjani_scenario_delft3d_{stamp}"
    workdir.mkdir(parents=True, exist_ok=True)

    net = workdir / "ujjani_net.nc"
    shutil.copyfile(scen.UJJANI_UGRID, net)
    mesh_info = _mesh_info(net)

    # source-sink polyline: sink end far outside the mesh -> inflow-only at the dam
    x0, y0 = mesh_info["x_range_m"][0], mesh_info["y_range_m"][0]
    sink_x, sink_y = x0 - 100000.0, y0 - 100000.0
    (workdir / "breach_source.pli").write_text(
        "breach_source\n2 2\n"
        f"{sink_x:.2f} {sink_y:.2f}\n"
        f"{sc.dam_x_m:.2f} {sc.dam_y_m:.2f}\n",
        encoding="utf-8",
    )
    # hydrograph .tim  (minutes  discharge_m3s)  from the fine grid
    tmin = np.array(hydrograph["_t_fine_s"]) / 60.0
    q = np.array(hydrograph["_q_fine_m3s"])
    (workdir / "breach_source.tim").write_text(
        "\n".join(f"{t:.6f}\t{max(qq, 0.0):.4f}" for t, qq in zip(tmin, q)) + "\n",
        encoding="utf-8",
    )
    (workdir / "breach.ext").write_text(EXT, encoding="utf-8")

    (workdir / "flow.mdu").write_text(MDU.format(
        bedlevuni=mesh_info["bed_level_min_m"],
        waterlevini=min(0.0, mesh_info["bed_level_min_m"] - 5.0),  # dry downstream
        manning=sc.manning_n,
        dt=sc.output_interval_s,
        tstop=sc.simulation_duration_s,
    ), encoding="utf-8")

    progress(35, f"Running dflowfm-cli (Ujjani terrain, T={sc.simulation_duration_s:g}s)")
    started = time.perf_counter()
    try:
        proc = subprocess.run([str(exe), "--autostartstop", "flow.mdu"],
                              cwd=workdir, capture_output=True, text=True, timeout=3600)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "engine": "delft3d_dflowfm", "reason": f"dflowfm-cli launch failed: {exc}",
                "workdir": str(workdir)}
    runtime = time.perf_counter() - started
    (workdir / "dflowfm_stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (workdir / "dflowfm_stderr.log").write_text(proc.stderr or "", encoding="utf-8")

    log = (proc.stdout or "")
    for dia in ("DFM_OUTPUT_flow/flow.dia", "unstruc.dia"):
        p = workdir / dia
        if p.exists():
            log += "\n" + p.read_text(encoding="utf-8", errors="ignore")

    map_nc = next(iter(workdir.glob("**/*_map.nc")), None)
    warns = [ln.strip() for ln in log.splitlines() if "sorsin" in ln.lower() or "source" in ln.lower()
             or "bndcell" in ln.lower() or "not found" in ln.lower()][:8]
    if proc.returncode != 0 or map_nc is None:
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"D-Flow FM exited {proc.returncode} / no *_map.nc",
                "returncode": proc.returncode, "workdir": str(workdir),
                "warnings": warns, "stdout_tail": (proc.stdout or "")[-2000:],
                "stderr_tail": (proc.stderr or "")[-2000:]}

    import netCDF4
    with netCDF4.Dataset(map_nc) as ds:
        depth = np.array(ds.variables["mesh2d_waterdepth"][:])
        ucx = np.array(ds.variables["mesh2d_ucx"][:]) if "mesh2d_ucx" in ds.variables else None
        ucy = np.array(ds.variables["mesh2d_ucy"][:]) if "mesh2d_ucy" in ds.variables else None
        tt = np.array(ds.variables["time"][:], float)
    vel = np.hypot(ucx, ucy) if ucx is not None else None
    if not np.isfinite(depth).all():
        return {"ok": False, "engine": "delft3d_dflowfm", "reason": "map file has non-finite water depth",
                "workdir": str(workdir)}
    dmax = float(np.nanmax(depth))
    vmax = float(np.nanmax(vel)) if vel is not None else None
    if dmax <= 0.0:
        return {"ok": False, "engine": "delft3d_dflowfm",
                "reason": f"Delft3D produced zero water depth (source not injecting?). max={dmax}",
                "workdir": str(workdir), "warnings": warns}

    from . import postprocess
    try:
        summary = postprocess.process(map_nc, out_dir, sc.to_dict())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "engine": "delft3d_dflowfm", "reason": f"postprocessing failed: {exc}",
                "workdir": str(workdir), "map_file": str(map_nc)}

    for name in ("flow.mdu", "breach.ext", "breach_source.pli", "breach_source.tim", "dflowfm_stdout.log"):
        if (workdir / name).exists():
            shutil.copyfile(workdir / name, out_dir / name)

    return {
        "ok": True,
        "engine": "delft3d_dflowfm",
        "engine_label": "Delft3D D-Flow FM — internal breach source at Ujjani dam",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "results_dir": str(out_dir),
        "available_frames": summary.get("available_frames", []),
        "summary": summary,
        "runtime_seconds": round(runtime, 2),
        "frames": int(depth.shape[0]),
        "time_range_s": [float(tt.min()), float(tt.max())],
        "max_depth_m": round(dmax, 4),
        "max_velocity_mps": round(vmax, 4) if vmax is not None else None,
        "mesh": mesh_info,
        "workdir": str(workdir),
        "map_file": str(map_nc),
        "command": f'"{exe}" --autostartstop flow.mdu',
        "release_representation": "internal discharge source point at the dam coordinate "
                                  "(EPSG:32643), inflow-only source-sink; NOT a mesh-edge boundary",
        "warnings": warns,
        "provenance": "Delft3D D-Flow FM on the real Ujjani DEM-derived mesh; breach released at the "
                      "project dam coordinate via a parameterised hydrograph. MODEL DEMONSTRATION — "
                      "not calibrated, not validated.",
    }
