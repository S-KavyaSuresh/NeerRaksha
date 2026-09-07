"""Delft3D D-Flow FM output -> frontend-friendly GIS products.

Reads a D-Flow FM map file (``*_map.nc``, UGRID) and produces:
  GeoTIFF : max_depth.tif, max_velocity.tif, arrival_time.tif
  GeoJSON : flood_extent.geojson, timeline/t###.geojson (depth-banded polygons)
  JSON    : summary.json, plus a timeline array inside it

Uses numpy + netCDF4 + rasterio only. The frontend never sees raw Delft3D files.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DEPTH_BANDS = ((0.05, 1.0, "0.05–1.0 m"), (1.0, 3.0, "1.0–3.0 m"),
               (3.0, 6.0, "3.0–6.0 m"), (6.0, float("inf"), "6.0+ m"))
DISCLAIMER = "Delft3D D-Flow FM MODEL OUTPUT — demonstration mesh, not validated for operations."


DEFAULT_CRS = "EPSG:32643"  # UTM 43N — the Ujjani demonstration mesh CRS


def _valid_epsg(raw) -> str | None:
    code = str(raw).split(":")[-1].strip()
    return f"EPSG:{code}" if code.isdigit() and int(code) > 0 else None


def _read_crs(ds):
    """Best-effort CRS from the map file; falls back to the known mesh CRS.

    D-Flow FM writes epsg=0 / 'EPSG:0' when the MDU carries no projection, so
    those are treated as 'unknown' and the Ujjani mesh CRS is used instead.
    """
    for name in ("projected_coordinate_system", "wgs84", "crs"):
        if name in getattr(ds, "variables", {}):
            var = ds.variables[name]
            for attr in ("EPSG_code", "epsg_code", "epsg"):
                if hasattr(var, attr):
                    found = _valid_epsg(getattr(var, attr))
                    if found:
                        return found
    for attr in ("crs", "epsg", "EPSG_code"):
        if hasattr(ds, attr):
            found = _valid_epsg(getattr(ds, attr))
            if found:
                return found
    return DEFAULT_CRS


def _read_map(map_nc: Path):
    import netCDF4

    ds = netCDF4.Dataset(map_nc)
    try:
        fx = np.array(ds.variables["mesh2d_face_x"][:])
        fy = np.array(ds.variables["mesh2d_face_y"][:])
        if "time" in ds.variables:
            times = np.array(ds.variables["time"][:], dtype="float64")
            time_units = str(getattr(ds.variables["time"], "units", "seconds"))
        else:
            times = np.array([0.0])
            time_units = "seconds"
        depth_var = next((n for n in ("mesh2d_waterdepth", "mesh2d_hs", "waterdepth") if n in ds.variables), None)
        if depth_var is None:
            raise KeyError("no water-depth variable in map file")
        depth = np.array(ds.variables[depth_var][:])  # (time, face)
        ucx = ds.variables.get("mesh2d_ucx")
        ucy = ds.variables.get("mesh2d_ucy")
        vel = None
        if ucx is not None and ucy is not None:
            vel = np.hypot(np.array(ucx[:]), np.array(ucy[:]))
        crs = _read_crs(ds)
        return fx, fy, times, time_units, depth, vel, crs
    finally:
        ds.close()


def _minutes(times, time_units):
    """Convert a D-Flow FM time axis to minutes using its declared units."""
    unit = str(time_units).strip().lower()
    if unit.startswith("second") or unit.startswith("s "):
        factor = 1.0 / 60.0
    elif unit.startswith("hour"):
        factor = 60.0
    elif unit.startswith("day"):
        factor = 1440.0
    elif unit.startswith("minute"):
        factor = 1.0
    else:  # "seconds since ..." style, or unknown -> assume seconds
        factor = 1.0 / 60.0
    return [float(t) * factor for t in times]


def process(map_nc: str | Path, out_dir: str | Path, scenario: dict | None = None,
            cell_size: float = 30.0) -> dict:
    import rasterio
    from rasterio.transform import from_origin

    map_nc = Path(map_nc)
    out_dir = Path(out_dir)
    (out_dir / "timeline").mkdir(parents=True, exist_ok=True)
    if not map_nc.exists():
        raise FileNotFoundError(f"D-Flow FM map file not found: {map_nc}")

    fx, fy, times, time_units, depth, vel, crs = _read_map(map_nc)
    try:
        crs = rasterio.crs.CRS.from_user_input(crs)
    except Exception:
        crs = rasterio.crs.CRS.from_string(DEFAULT_CRS)
    nt = depth.shape[0]
    minutes_axis = _minutes(times, time_units)

    # Rasterise scattered face values onto a regular grid by nearest-cell binning.
    minx, maxx = float(fx.min()), float(fx.max())
    miny, maxy = float(fy.min()), float(fy.max())
    ncols = max(2, int(np.ceil((maxx - minx) / cell_size)))
    nrows = max(2, int(np.ceil((maxy - miny) / cell_size)))
    transform = from_origin(minx, maxy, cell_size, cell_size)
    col = np.clip(((fx - minx) / cell_size).astype(int), 0, ncols - 1)
    row = np.clip(((maxy - fy) / cell_size).astype(int), 0, nrows - 1)

    max_depth = np.zeros((nrows, ncols), "float32")
    max_vel = np.zeros((nrows, ncols), "float32")
    arrival = np.full((nrows, ncols), -1.0, "float32")
    timeline = []

    for t in range(nt):
        grid = np.zeros((nrows, ncols), "float32")
        grid[row, col] = np.nan_to_num(depth[t])
        max_depth = np.maximum(max_depth, grid)
        vg = np.zeros((nrows, ncols), "float32")
        if vel is not None:
            vg[row, col] = np.nan_to_num(vel[t])
            max_vel = np.maximum(max_vel, vg)
        minute = minutes_axis[t]
        newly = (arrival < 0) & (grid >= 0.05)
        arrival[newly] = minute
        _write_frame(out_dir / "timeline" / f"t{int(round(minute)):03d}.geojson",
                     grid, transform, minute, scenario, crs)
        timeline.append({
            "minute": int(round(minute)),
            "flooded_area_km2": float((grid >= 0.05).sum() * cell_size ** 2 / 1e6),
            "max_depth_m": float(grid.max()),
            "max_velocity_mps": float(vg.max()) if vel is not None else None,
        })

    prof = {"driver": "GTiff", "height": nrows, "width": ncols, "count": 1,
            "dtype": "float32", "transform": transform, "crs": crs, "compress": "deflate"}
    for name, arr, nodata in (("max_depth.tif", max_depth, 0), ("max_velocity.tif", max_vel, 0),
                              ("arrival_time.tif", arrival, -1)):
        with rasterio.open(out_dir / name, "w", nodata=nodata, **prof) as dst:
            dst.write(arr, 1)

    _write_frame(out_dir / "flood_extent.geojson", max_depth, transform,
                 timeline[-1]["minute"] if timeline else 0, scenario, crs)

    summary = {
        "case_id": "ujjani",
        "model_type": "delft3d_dflowfm",
        "engine_label": "Delft3D D-Flow FM",
        "data_class": "MODEL OUTPUT",
        "validated_hydraulic_output": False,
        "disclaimer": DISCLAIMER,
        "source_map_file": str(map_nc),
        "available_frames": [pt["minute"] for pt in timeline],
        "flooded_area_km2": timeline[-1]["flooded_area_km2"] if timeline else 0.0,
        "maximum_depth_m": float(max_depth.max()),
        "maximum_velocity_mps": float(max_vel.max()) if vel is not None else None,
        "timeline": timeline,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _write_frame(path: Path, grid, transform, minute: float, scenario: dict | None,
                 src_crs=None) -> None:
    from rasterio.features import shapes
    from rasterio.warp import transform_geom
    from rasterio.crs import CRS

    wgs84 = CRS.from_epsg(4326)
    reproject = src_crs is not None and CRS.from_user_input(src_crs) != wgs84

    feats = []
    for low, high, label in DEPTH_BANDS:
        mask = (grid >= low) & (grid < high)
        if not mask.any():
            continue
        for geom, val in shapes(mask.astype("uint8"), mask=mask, transform=transform):
            if val:
                # Frontend Cesium consumes lon/lat; GeoTIFFs keep the source CRS.
                if reproject:
                    geom = transform_geom(src_crs, wgs84, geom, precision=7)
                feats.append({
                    "type": "Feature",
                    "properties": {
                        "time_min": int(round(minute)), "depth_min_m": low,
                        "depth_max_m": None if high == float("inf") else high,
                        "depth_class": label, "model_type": "delft3d_dflowfm",
                        "validated_hydraulic_output": False,
                        "scenario_id": (scenario or {}).get("preset"),
                    },
                    "geometry": geom,
                })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
