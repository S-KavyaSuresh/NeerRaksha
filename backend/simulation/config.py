"""Machine-configurable paths and engine settings for the simulation pipeline.

Every path can be overridden with an environment variable so the demo runs on any
machine and the real Ujjani DEM can be plugged in later without code changes.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw) if raw else default


# --- Pre-computed approximate-solver products (MODEL OUTPUT, not validated) -----
RESULTS_ROOT = _env_path("NEERRAKSHA_RESULTS_ROOT", ROOT / "results" / "ujjani")

# --- DEM configuration --------------------------------------------------------
# Real cropped Ujjani DEM if the developer has produced one (preferred).
UJJANI_DEM = _env_path(
    "NEERRAKSHA_DEM",
    ROOT / "data" / "cases" / "ujjani_real" / "dem" / "ujjani_dem_utm43.tif",
)
# Synthetic development DEM (SYNTHETIC DATA — not real Ujjani terrain).
SYNTHETIC_DEM = _env_path(
    "NEERRAKSHA_SYNTHETIC_DEM",
    Path(r"D:\SIH 2026\mine\data\synthetic\synthetic_dem.tif"),
)

# --- Delft3D D-Flow FM -------------------------------------------------------
DELFT3D_EXECUTABLE = _env_path(
    "DELFT3D_EXECUTABLE",
    Path(r"D:\Delft3D-OSS\Delft3D\install_dflowfm\bin\dflowfm-cli.exe"),
)
DELFT3D_REFERENCE_MESH = _env_path(
    "DELFT3D_REFERENCE_MESH",
    Path(r"D:\Delft3D-OSS\Delft3D\src\engines_gpl\dflowfm\tests\test_data\2d_ugrid_net.nc"),
)

# Proven D-Flow FM UGRID mesh for the Ujjani demonstration domain (4345 faces,
# 4480 nodes). The forcing boundary below sits on this mesh's left edge, so the
# engine reuses this file rather than rebuilding a mesh whose edge would not line
# up with the boundary polyline.
DELFT3D_UGRID = _env_path(
    "DELFT3D_UGRID",
    ROOT / "data" / "cases" / "ujjani_real" / "dem" / "ujjani_ugrid.nc",
)

# Proven discharge-boundary polyline (EPSG:32643, left edge of DELFT3D_UGRID).
# This is a DEMONSTRATION / integration boundary, NOT the physical Ujjani dam.
DELFT3D_BOUNDARY_NAME = "DamBreak"
DELFT3D_BOUNDARY_POINTS = ((500015.46, 1990338.79), (500015.46, 2003456.89))

# Default demonstration hydrograph: (time_minutes, discharge_m3s). Same shape as
# the proven forcing test; peak 3000 m3/s. Not a calibrated breach hydrograph.
DELFT3D_DEMO_HYDROGRAPH = ((0.0, 0.0), (0.2, 500.0), (0.4, 1500.0), (0.5, 3000.0),
                           (0.7, 1500.0), (0.9, 500.0), (1.0, 0.0))

# Where each engine writes run artefacts.
SIM_WORKDIR = _env_path("NEERRAKSHA_SIM_WORKDIR", ROOT / "data" / "processed" / "simulations")
DELFT3D_RESULTS = _env_path("NEERRAKSHA_DELFT3D_RESULTS", ROOT / "results" / "ujjani_delft3d")

# Demo defaults — small + short, per the hackathon performance rules.
DEMO_DURATION_MIN = int(os.environ.get("NEERRAKSHA_DEMO_DURATION_MIN", "60"))
DEMO_INTERVAL_MIN = int(os.environ.get("NEERRAKSHA_DEMO_INTERVAL_MIN", "5"))
DELFT3D_DURATION_MIN = float(os.environ.get("NEERRAKSHA_DELFT3D_DURATION_MIN", "5"))
DELFT3D_MAP_INTERVAL_S = int(os.environ.get("NEERRAKSHA_DELFT3D_MAP_INTERVAL_S", "60"))
DELFT3D_DT_USER_S = int(os.environ.get("NEERRAKSHA_DELFT3D_DT_USER_S", "60"))


def scenario_preset(scenario: dict | None) -> str:
    """Map a frontend scenario payload to a pre-computed results directory name."""
    scenario = scenario or {}
    preset = str(scenario.get("preset") or "").lower()
    breach = str(scenario.get("breach_type") or "").lower()
    if preset in {"partial", "partial_breach"} or breach == "partial":
        return "partial_breach"
    if preset in {"major", "major_breach"} or breach == "major":
        return "major_breach"
    return "baseline"


def results_dir_for(scenario: dict | None) -> Path:
    preset = scenario_preset(scenario)
    candidate = RESULTS_ROOT / preset
    if (candidate / "summary.json").exists():
        return candidate
    # Fall back to the top-level baseline products.
    return RESULTS_ROOT
