"""Phase 4 — engine-independent Ujjani dam-break scenario.

One scenario definition feeds the Delft3D, SPH and approximate adapters. It ties
the physical chain together explicitly:

    REAL UJJANI DEM  ->  DAM LOCATION (18.0739 N, 75.1200 E)
      ->  RESERVOIR LEVEL (scenario input)  ->  BREACH (width / depth / formation time)
      ->  BREACH-GROWTH + BROAD-CRESTED-WEIR HYDROGRAPH  ->  hydrodynamic routing

DATA CLASSIFICATION (mandatory, per field — see ``classification`` in to_dict()):
    REAL DATA   : Ujjani 30 m DEM, dam coordinate (project-supplied), CRS.
    MODEL INPUT : breach width/depth/formation time, simulation duration, Manning n.
    ASSUMPTION / DEMO : reservoir level / assumed head, recession time, weir Cd.
    MODEL OUTPUT: everything the engines produce.
    OBSERVATION : none in this phase.

Nothing here is calibrated or validated. Peak discharge is MODEL INPUT / DERIVED,
not an observed Ujjani value.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from . import config

# --- project-supplied target (do not invent a more precise geometry) --------- #
DAM_LAT = 18.0739
DAM_LON = 75.1200
UJJANI_DEM = config.ROOT / "data" / "cases" / "ujjani_real" / "dem" / "ujjani_dem_utm43.tif"
UJJANI_UGRID = config.ROOT / "data" / "cases" / "ujjani_real" / "dem" / "ujjani_ugrid.nc"
MODEL_CRS = "EPSG:32643"

GRAVITY = 9.81
BAD = ("NaN", "Inf")


class ScenarioError(ValueError):
    """Raised when a scenario fails physical sanity checks."""


@dataclass
class UjjaniScenario:
    case_id: str = "ujjani"
    engine: str = "delft3d"                 # delft3d | sph | approximate
    preset: str = "custom"

    dem_path: str = str(UJJANI_DEM)
    crs: str = MODEL_CRS
    dam_lat: float = DAM_LAT
    dam_lon: float = DAM_LON

    # reservoir / upstream water condition (ASSUMPTION / DEMO — no storage curve)
    reservoir_level_m: float | None = None      # if None -> terrain_elev_at_dam + assumed_head_m
    assumed_head_m: float = 15.0                 # DEMO head over the breach invert at full formation
    initial_downstream_level_m: float = 0.0      # dry bed downstream

    # breach (MODEL INPUT)
    breach_width_m: float = 150.0
    breach_depth_m: float = 12.0
    breach_formation_time_s: float = 1800.0
    recession_time_s: float = 3600.0            # ASSUMPTION — reservoir drawdown proxy

    # run controls (MODEL INPUT)
    simulation_duration_s: float = 3600.0
    output_interval_s: float = 300.0
    gravity_m_s2: float = GRAVITY
    manning_n: float = 0.035
    weir_coefficient_cd: float = 1.0           # ASSUMPTION (broad-crested weir Cd)

    # filled by resolve()
    terrain_elev_at_dam_m: float | None = None
    dam_x_m: float | None = None
    dam_y_m: float | None = None
    breach_invert_final_m: float | None = None
    in_domain: bool | None = None
    domain_bounds_m: list | None = field(default=None)

    # ----------------------------------------------------------------- #
    def validate(self) -> None:
        checks = {
            "breach_width_m > 0": self.breach_width_m > 0,
            "breach_depth_m > 0": self.breach_depth_m > 0,
            "breach_formation_time_s >= 0": self.breach_formation_time_s >= 0,
            "recession_time_s > 0": self.recession_time_s > 0,
            "simulation_duration_s > 0": self.simulation_duration_s > 0,
            "output_interval_s > 0": self.output_interval_s > 0,
            "output_interval_s <= simulation_duration_s":
                self.output_interval_s <= self.simulation_duration_s,
            "gravity_m_s2 > 0": self.gravity_m_s2 > 0,
            "manning_n >= 0": self.manning_n >= 0,
            "weir_coefficient_cd > 0": self.weir_coefficient_cd > 0,
            "assumed_head_m > 0": self.assumed_head_m > 0,
            "-90 <= dam_lat <= 90": -90 <= self.dam_lat <= 90,
            "-180 <= dam_lon <= 180": -180 <= self.dam_lon <= 180,
            "engine in {delft3d, sph, approximate}":
                self.engine in ("delft3d", "sph", "approximate"),
        }
        for value in (self.breach_width_m, self.breach_depth_m, self.breach_formation_time_s,
                      self.recession_time_s, self.simulation_duration_s, self.output_interval_s):
            checks["all inputs finite"] = math.isfinite(value)
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise ScenarioError("scenario failed physical sanity checks: " + "; ".join(failed))
        if self.reservoir_level_m is not None and not math.isfinite(self.reservoir_level_m):
            raise ScenarioError("reservoir_level_m is not finite")

    def resolve(self) -> "UjjaniScenario":
        """Fill DEM-derived fields; check the dam lies inside the modelling domain."""
        import rasterio
        from pyproj import Transformer

        self.validate()
        tf = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        self.dam_x_m, self.dam_y_m = (float(v) for v in tf.transform(self.dam_lon, self.dam_lat))

        dem = Path(self.dem_path)
        if not dem.exists():
            raise ScenarioError(f"Ujjani DEM not found: {dem}")
        with rasterio.open(dem) as src:
            b = src.bounds
            self.domain_bounds_m = [float(b.left), float(b.bottom), float(b.right), float(b.top)]
            inside = (b.left <= self.dam_x_m <= b.right) and (b.bottom <= self.dam_y_m <= b.top)
            self.in_domain = bool(inside)
            if inside:
                row, col = src.index(self.dam_x_m, self.dam_y_m)
                val = float(src.read(1)[row, col])
                nod = src.nodata
                self.terrain_elev_at_dam_m = None if (nod is not None and val == nod) else val
        if not self.in_domain:
            raise ScenarioError(
                f"dam coordinate ({self.dam_lat}, {self.dam_lon}) -> "
                f"UTM ({self.dam_x_m:.1f}, {self.dam_y_m:.1f}) is outside the DEM domain "
                f"{self.domain_bounds_m}"
            )
        if self.terrain_elev_at_dam_m is None:
            raise ScenarioError("DEM has no data at the dam coordinate")

        if self.reservoir_level_m is None:
            self.reservoir_level_m = self.terrain_elev_at_dam_m + self.assumed_head_m
        self.breach_invert_final_m = self.reservoir_level_m - self.breach_depth_m
        if self.reservoir_level_m <= self.breach_invert_final_m:
            raise ScenarioError("reservoir level is not above the final breach invert")
        return self

    # ----------------------------------------------------------------- #
    def to_dict(self) -> dict:
        d = asdict(self)
        d["dam_lat_lon"] = [self.dam_lat, self.dam_lon]
        d["classification"] = {
            "dem_path": "REAL DATA (Ujjani 30 m DEM; does not resolve the dam wall)",
            "crs": "REAL DATA",
            "dam_lat / dam_lon": "REAL DATA (project-supplied target coordinate)",
            "terrain_elev_at_dam_m": "REAL DATA (DEM sample at the dam coordinate)",
            "reservoir_level_m / assumed_head_m": "ASSUMPTION / DEMO (no Ujjani storage curve)",
            "breach_width_m / breach_depth_m / breach_formation_time_s": "MODEL INPUT",
            "recession_time_s": "ASSUMPTION / DEMO (reservoir-drawdown proxy)",
            "weir_coefficient_cd": "ASSUMPTION (broad-crested weir coefficient)",
            "simulation_duration_s / output_interval_s / manning_n / gravity_m_s2": "MODEL INPUT",
            "everything the engines return": "MODEL OUTPUT",
            "observations": "NONE in this phase",
        }
        return d


# --------------------------------------------------------------------------- #
# deterministic breach discharge hydrograph
# --------------------------------------------------------------------------- #
def breach_hydrograph(sc: UjjaniScenario) -> dict:
    """Deterministic breach outflow hydrograph from the scenario parameters.

    FORMULATION (documented, reproducible — NOT an observed Ujjani breach):
      Rectangular breach growing LINEARLY in width and depth over the formation
      time tf. Broad-crested weir discharge:

          f(t)  = min(t/tf, 1)                       (formation fraction)
          b(t)  = breach_width_m * f(t)              (breach width)
          H(t)  = breach_depth_m * f(t)              (head over the breach invert)
          Cw    = (2/3) * Cd * sqrt(2 g / 3)         (broad-crested weir constant)
          Q(t)  = Cw * b(t) * H(t)^(3/2)             for 0 <= t <= tf
          Qpeak = Cw * breach_width_m * breach_depth_m^(3/2)
          Q(t)  = Qpeak * exp(-(t - tf) / recession_time_s)   for t > tf

      Reservoir level is held constant during formation (no storage curve
      available); the exponential recession is an assumed drawdown proxy.
      Standard broad-crested-weir breach routing, cf. Fread (1988) DAMBRK /
      USBR (1988) practice, simplified. Peak discharge is MODEL INPUT / DERIVED.
    """
    tf = float(sc.breach_formation_time_s)
    dur = float(sc.simulation_duration_s)
    dt_out = float(sc.output_interval_s)
    cw = (2.0 / 3.0) * sc.weir_coefficient_cd * math.sqrt(2.0 * sc.gravity_m_s2 / 3.0)
    q_peak = cw * sc.breach_width_m * sc.breach_depth_m ** 1.5

    # fine internal grid for the shape, then sampled at output interval
    n = max(64, int(dur / min(dt_out, max(tf, 1.0) / 8.0)) + 1)
    t = np.linspace(0.0, dur, n)
    q = np.empty_like(t)
    forming = t <= tf if tf > 0 else t < 0
    f = np.clip(t / tf, 0.0, 1.0) if tf > 0 else np.ones_like(t)
    q_form = cw * (sc.breach_width_m * f) * (sc.breach_depth_m * f) ** 1.5
    q_rec = q_peak * np.exp(-(t - tf) / sc.recession_time_s)
    q = np.where(t <= tf, q_form, q_rec) if tf > 0 else q_rec
    q = np.maximum(q, 0.0)

    if not np.all(np.isfinite(q)):
        raise ScenarioError("hydrograph produced non-finite discharge")

    # sample at the output interval for the machine-readable series
    ts = np.arange(0.0, dur + 1e-6, dt_out)
    qs = np.interp(ts, t, q)
    k_peak = int(np.argmax(qs))

    return {
        "formulation": "growing-rectangular-breach broad-crested weir + exponential recession",
        "formulation_detail": breach_hydrograph.__doc__.strip(),
        "reference": "Fread (1988) DAMBRK; USBR (1988) — simplified broad-crested weir breach routing",
        "provenance": "MODEL INPUT / DERIVED from scenario parameters (NOT an observed Ujjani hydrograph)",
        "weir_constant_Cw": cw,
        "peak_discharge_m3s": float(q_peak),
        "time_of_peak_s": float(ts[k_peak]),
        "total_duration_s": dur,
        "output_interval_s": dt_out,
        "assumptions": [
            "reservoir level constant during breach formation (no storage curve)",
            "breach grows linearly in width and depth",
            "exponential recession with time constant recession_time_s (assumed)",
            f"broad-crested weir Cd = {sc.weir_coefficient_cd}",
        ],
        "series": {
            "columns": ["time_s", "discharge_m3s"],
            "time_s": [round(float(v), 3) for v in ts],
            "discharge_m3s": [round(float(v), 4) for v in qs],
        },
        # fine grid for the engines
        "_t_fine_s": t.tolist(),
        "_q_fine_m3s": q.tolist(),
    }


def write_hydrograph(hg: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = out_dir / "hydrograph.csv"
    rows = ["time_s,discharge_m3s"]
    rows += [f"{t},{q}" for t, q in zip(hg["series"]["time_s"], hg["series"]["discharge_m3s"])]
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    public = {k: v for k, v in hg.items() if not k.startswith("_")}
    (out_dir / "hydrograph.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return {"csv": str(csv), "json": str(out_dir / "hydrograph.json")}


# --------------------------------------------------------------------------- #
# scenario variants (DEMO / ASSUMED numeric defaults)
# --------------------------------------------------------------------------- #
SCENARIO_PRESETS = {
    "small_breach": {
        "preset": "small_breach",
        "breach_width_m": 60.0, "breach_depth_m": 6.0,
        "breach_formation_time_s": 3600.0, "recession_time_s": 5400.0,
        "assumed_head_m": 10.0, "simulation_duration_s": 3600.0, "output_interval_s": 300.0,
    },
    "medium_breach": {
        "preset": "medium_breach",
        "breach_width_m": 150.0, "breach_depth_m": 12.0,
        "breach_formation_time_s": 1800.0, "recession_time_s": 3600.0,
        "assumed_head_m": 15.0, "simulation_duration_s": 3600.0, "output_interval_s": 300.0,
    },
    "large_rapid_breach": {
        "preset": "large_rapid_breach",
        "breach_width_m": 250.0, "breach_depth_m": 25.0,
        "breach_formation_time_s": 600.0, "recession_time_s": 2400.0,
        "assumed_head_m": 25.0, "simulation_duration_s": 3600.0, "output_interval_s": 300.0,
    },
}


def from_request(payload: dict) -> UjjaniScenario:
    """Build a scenario from an API payload, applying a preset then overrides."""
    payload = dict(payload or {})
    preset = str(payload.get("preset", "custom"))
    base: dict = {}
    if preset in SCENARIO_PRESETS:
        base.update(SCENARIO_PRESETS[preset])
    allowed = {f for f in UjjaniScenario.__dataclass_fields__}
    for key, value in payload.items():
        if key in allowed:
            base[key] = value
    base.setdefault("preset", preset)
    return UjjaniScenario(**base)


if __name__ == "__main__":
    for name in SCENARIO_PRESETS:
        sc = from_request({"preset": name}).resolve()
        hg = breach_hydrograph(sc)
        print(f"{name:20s} Qpeak={hg['peak_discharge_m3s']:9.1f} m3/s "
              f"@ t={hg['time_of_peak_s']:.0f}s  res_level={sc.reservoir_level_m:.1f} m "
              f"(terrain {sc.terrain_elev_at_dam_m:.1f} m)  in_domain={sc.in_domain}")
