from __future__ import annotations

import csv, json
from pathlib import Path
from time import perf_counter

import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "data" / "cases"
DEM_PATH = CASE / "ujjani_synthetic" / "real_dem" / "ujjani_dem_cropped.tif"
RIVER_PATH = CASE / "ujjani_real" / "bhima_downstream_hecras.geojson"
HYDROGRAPH_PATH = CASE / "ujjani_synthetic" / "breach_hydrograph_baseline.csv"
OUT = ROOT / "results" / "ujjani"
DISCLAIMER = "Automated approximate 2D flood-routing prototype — not validated hydraulic output."

def _load_hydrograph():
    with HYDROGRAPH_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("Breach hydrograph is empty")
    columns = rows[0].keys()
    time_key = next((key for key in columns if key.lower() in {"time_s", "time_seconds", "time"}), None)
    discharge_key = next((key for key in columns if "discharge" in key.lower()), None)
    if not time_key or not discharge_key:
        raise ValueError("Hydrograph requires time and discharge columns")
    times = np.array([float(row[time_key]) for row in rows])
    discharge = np.array([float(row[discharge_key]) for row in rows])
    if np.any(~np.isfinite(times)) or np.any(~np.isfinite(discharge)) or np.any(discharge < 0):
        raise ValueError("Hydrograph has invalid values")
    return times, discharge, discharge_key

def _corridor(transform, shape):
    data = json.loads(RIVER_PATH.read_text(encoding="utf-8"))
    lines = [feature.get("geometry", {}).get("coordinates") for feature in data.get("features", []) if feature.get("geometry", {}).get("type") == "LineString"]
    lines = [line for line in lines if isinstance(line, list) and len(line) >= 2]
    if not lines:
        raise ValueError("No valid downstream Bhima LineString")
    mask = rasterize([({"type": "LineString", "coordinates": line}, 1) for line in lines], out_shape=shape, transform=transform, fill=0, all_touched=True, dtype="uint8")
    # Approx. 300 m half-width on the source DEM's ~30 m grid.
    return distance_transform_edt(mask == 0) <= 10, lines

def _extent_geojson(depth, transform, minute, threshold, cell_area, provenance):
    features = []
    for low, high, label in ((.05, 1., "0.05–1.0 m"), (1., 3., "1.0–3.0 m"), (3., 6., "3.0–6.0 m"), (6., float("inf"), "6.0+ m")):
        mask = (depth >= low) & (depth < high)
        for geometry, value in shapes(mask.astype("uint8"), mask=mask, transform=transform):
            if value:
                values = depth[mask]
                features.append({"type":"Feature", "properties":{"time_min":minute, "depth_min_m":low, "depth_max_m":None if not np.isfinite(high) else high, "depth_class":label, "max_depth_m":float(values.max()) if values.size else 0, "mean_depth_m":float(values.mean()) if values.size else 0, "flooded_area_km2":float(mask.sum() * cell_area / 1e6), "provenance":provenance, "model_type":"Automated approximate 2D flood-routing prototype"}, "geometry":geometry})
    return {"type":"FeatureCollection", "features":features}

def run(duration_min=60, output_interval_min=5, threshold=0.05):
    started = perf_counter(); OUT.mkdir(parents=True, exist_ok=True); (OUT / "timeline").mkdir(exist_ok=True)
    times, hydrograph, discharge_key = _load_hydrograph()
    with rasterio.open(DEM_PATH) as source:
        dem = source.read(1).astype("float64"); profile = source.profile.copy(); transform = source.transform; crs = str(source.crs); nodata = source.nodata
    valid = np.isfinite(dem) & (dem != nodata)
    corridor, lines = _corridor(transform, dem.shape); corridor &= valid
    if not corridor.any(): raise ValueError("Bhima corridor does not overlap DEM")
    # EPSG:4326 source raster: calculate local metric cell area without modifying it on disk.
    latitude = (transform.f + transform.e * dem.shape[0] / 2); dx = abs(transform.a) * 111320 * np.cos(np.deg2rad(latitude)); dy = abs(transform.e) * 110540; cell_area = dx * dy
    elevations = dem[corridor]; low, high = float(elevations.min()), float(elevations.max() + 30)
    max_depth = np.zeros_like(dem); max_velocity = np.zeros_like(dem); arrival = np.full(dem.shape, -1.0)
    injected = outflow = 0.0; previous_t = 0.0; previous_q = float(hydrograph[0]); timeline = []
    for minute in range(0, duration_min + 1, output_interval_min):
        target_t = minute * 60.0; q = float(np.interp(target_t, times, hydrograph)); injected += max(0.0, (previous_q + q) * .5 * (target_t - previous_t)); previous_t, previous_q = target_t, q
        # Monotone bisection solves sum(depth * cell_area) = injected volume; no mass clipping occurs.
        lo, hi = low, high
        for _ in range(36):
            level = (lo + hi) * .5; volume = np.maximum(level - elevations, 0).sum() * cell_area
            if volume < injected: lo = level
            else: hi = level
        depth = np.zeros_like(dem); depth[corridor] = np.maximum(((lo + hi) * .5) - elevations, 0)
        depth[depth < threshold] = 0
        surface = dem + depth; gy, gx = np.gradient(surface, dy, dx); slope = np.maximum(np.hypot(gx, gy), 1e-7)
        roughness = np.where(corridor, .035, .050); velocity = np.where(depth > 0, np.power(depth, 2/3) * np.sqrt(slope) / roughness, 0)
        max_depth = np.maximum(max_depth, depth); max_velocity = np.maximum(max_velocity, velocity)
        arrival[(arrival < 0) & (depth >= threshold)] = minute
        frame = _extent_geojson(depth, transform, minute, threshold, cell_area, DISCLAIMER); (OUT / "timeline" / f"t{minute:03d}.geojson").write_text(json.dumps(frame), encoding="utf-8"); timeline.append({"minute":minute, "flooded_area_km2":float((depth >= threshold).sum() * cell_area / 1e6), "max_depth_m":float(depth.max()), "max_velocity_mps":float(velocity.max())})
    for name, array, dtype in (("max_depth.tif", max_depth, "float32"), ("max_velocity.tif", max_velocity, "float32"), ("arrival_time.tif", arrival, "float32")):
        profile.update(dtype=dtype, count=1, compress="deflate", nodata=-1 if name == "arrival_time.tif" else 0)
        with rasterio.open(OUT / name, "w", **profile) as dest: dest.write(array.astype(dtype), 1)
    final = _extent_geojson(max_depth, transform, duration_min, threshold, cell_area, DISCLAIMER); (OUT / "flood_extent.geojson").write_text(json.dumps(final), encoding="utf-8")
    stored = float(max_depth.sum() * cell_area); summary = {"case_id":"ujjani", "dam_name":"Ujjani Dam", "model_type":"automated_approximate_2d_flood_routing_prototype", "disclaimer":DISCLAIMER, "simulation_duration_min":duration_min, "output_interval_min":output_interval_min, "peak_breach_discharge_m3s":float(hydrograph.max()), "injected_volume_m3":injected, "downstream_outflow_m3":outflow, "final_stored_volume_m3":stored, "mass_balance_error_percent":((injected - outflow - stored) / injected * 100) if injected else 0, "flooded_area_km2":timeline[-1]["flooded_area_km2"], "maximum_depth_m":float(max_depth.max()), "maximum_velocity_mps":float(max_velocity.max()), "assumptions":{"channel_manning_n":.035,"floodplain_manning_n":.050,"corridor_half_width_m":300,"boundaries":"closed; downstream outflow not activated in first prototype"}, "source_files":[str(DEM_PATH.relative_to(ROOT)),str(RIVER_PATH.relative_to(ROOT)),str(HYDROGRAPH_PATH.relative_to(ROOT))], "crs":crs, "runtime_seconds":perf_counter()-started, "timeline":timeline}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8"); return summary
