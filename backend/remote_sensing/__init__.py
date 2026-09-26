"""NeerRaksha OBSERVATION branch — Sentinel-1 SAR water/flood evidence via Google
Earth Engine.

This is deliberately separate from the MODEL branch (Delft3D / SPH). A satellite
water/flood evidence layer is an OBSERVATION, not validated hydraulic output and
not ground truth:

    MODELLED FLOOD  !=  SATELLITE-OBSERVED WATER EVIDENCE

Nothing here fabricates observations. If Earth Engine is not authenticated the
workflow returns status "unavailable" with an explicit reason.
"""
from .observation import (  # noqa: F401
    UJJANI_AOI,
    OBS_RESULTS,
    run_observation,
    process_arrays,
    compare_with_model,
)
from .gee_client import GEEClient, GEEUnavailable, gee_status  # noqa: F401
from . import sentinel1  # noqa: F401
