from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.transform import rowcol


BASE = Path(
    r"C:\Users\kavya\JalDrishti\data\cases"
    r"\ujjani_synthetic\real_dem"
)

DEM_FILE = BASE / "ujjani_dem_cropped.tif"
ACC_FILE = BASE / "ujjani_flow_accumulation.tif"
OUTPUT = BASE / "ujjani_flow_accumulation_preview.png"

DAM_LON = 75.120278
DAM_LAT = 18.075000


with rasterio.open(DEM_FILE) as dem_src:
    dem = dem_src.read(1)
    bounds = dem_src.bounds
    transform = dem_src.transform

with rasterio.open(ACC_FILE) as acc_src:
    acc = acc_src.read(1).astype("float64")


# ------------------------------------------------------------
# DAM PIXEL
# ------------------------------------------------------------

r, c = rowcol(
    transform,
    DAM_LON,
    DAM_LAT
)

print("Dam pixel:", r, c)
print(
    "Flow accumulation at dam pixel:",
    acc[r, c]
)


# ------------------------------------------------------------
# SEARCH NEAR DAM
# ------------------------------------------------------------

# approximately 3 km radius at 30 m resolution
radius_cells = 100

r0 = max(0, r - radius_cells)
r1 = min(acc.shape[0], r + radius_cells + 1)

c0 = max(0, c - radius_cells)
c1 = min(acc.shape[1], c + radius_cells + 1)

near = acc[
    r0:r1,
    c0:c1
]

local_index = np.unravel_index(
    np.argmax(near),
    near.shape
)

best_r = r0 + local_index[0]
best_c = c0 + local_index[1]

best_lon, best_lat = rasterio.transform.xy(
    transform,
    best_r,
    best_c,
    offset="center"
)

print(
    "Maximum accumulation within ~3 km:",
    acc[best_r, best_c]
)

print(
    "Nearest major drainage coordinate:",
    f"{best_lat:.6f}, {best_lon:.6f}"
)


# ------------------------------------------------------------
# VISUALIZE LOG FLOW ACCUMULATION
# ------------------------------------------------------------

display_acc = np.log10(
    np.maximum(
        acc,
        1
    )
)

fig, ax = plt.subplots(
    figsize=(14, 7)
)

image = ax.imshow(
    display_acc,
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
    marker="^",
    s=100,
    label="Ujjani Dam"
)

ax.scatter(
    best_lon,
    best_lat,
    marker="x",
    s=100,
    label="Highest accumulation near dam"
)

ax.set_title(
    "Ujjani — Log10 Flow Accumulation"
)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

ax.legend()

plt.colorbar(
    image,
    ax=ax,
    label="log10(flow accumulation)"
)

plt.tight_layout()

plt.savefig(
    OUTPUT,
    dpi=180,
    bbox_inches="tight"
)

print("Created:", OUTPUT)