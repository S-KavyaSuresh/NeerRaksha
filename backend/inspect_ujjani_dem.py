from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource


DEM = Path(
    r"C:\Users\kavya\JalDrishti\data\cases"
    r"\ujjani_synthetic\real_dem\ujjani_dem_cropped.tif"
)

OUTPUT = DEM.parent / "ujjani_dem_hillshade.png"

DAM_LON = 75.120278
DAM_LAT = 18.075000


with rasterio.open(DEM) as src:
    elevation = src.read(1).astype("float32")
    nodata = src.nodata
    bounds = src.bounds

if nodata is not None:
    elevation[elevation == nodata] = np.nan

valid = elevation[np.isfinite(elevation)]

print("DEM:", DEM)
print("Bounds:", bounds)
print("Minimum elevation:", float(valid.min()), "m")
print("Maximum elevation:", float(valid.max()), "m")
print("Mean elevation:", float(valid.mean()), "m")

# Fill NaNs only for hillshade calculation.
filled = np.where(
    np.isfinite(elevation),
    elevation,
    np.nanmedian(valid)
)

ls = LightSource(
    azdeg=315,
    altdeg=45
)

hillshade = ls.hillshade(
    filled,
    vert_exag=1.5,
    dx=30,
    dy=30
)

fig, ax = plt.subplots(
    figsize=(14, 7)
)

ax.imshow(
    hillshade,
    cmap="gray",
    extent=[
        bounds.left,
        bounds.right,
        bounds.bottom,
        bounds.top
    ],
    origin="upper"
)

ax.scatter(
    DAM_LON,
    DAM_LAT,
    s=80,
    marker="^",
    label="Ujjani Dam"
)

ax.set_title(
    "Ujjani Dam — 30 m DEM Hillshade"
)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

ax.legend()

plt.tight_layout()

plt.savefig(
    OUTPUT,
    dpi=180,
    bbox_inches="tight"
)

print("Created:", OUTPUT)