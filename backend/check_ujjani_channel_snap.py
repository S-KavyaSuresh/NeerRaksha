from pathlib import Path
import math

import numpy as np
import rasterio
from rasterio.transform import rowcol, xy


BASE = Path(
    r"C:\Users\kavya\JalDrishti\data\cases"
    r"\ujjani_synthetic\real_dem"
)

DEM_FILE = BASE / "ujjani_dem_cropped.tif"
ACC_FILE = BASE / "ujjani_flow_accumulation.tif"

DAM_LON = 75.120278
DAM_LAT = 18.075000


def distance_m(lat1, lon1, lat2, lon2):
    r = 6371000.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return (
        2
        * r
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


with rasterio.open(DEM_FILE) as dem_src:
    dem = dem_src.read(1).astype(float)
    transform = dem_src.transform
    nodata = dem_src.nodata


with rasterio.open(ACC_FILE) as acc_src:
    acc = acc_src.read(1).astype(float)


if nodata is not None:
    dem[dem == nodata] = np.nan


dam_r, dam_c = rowcol(
    transform,
    DAM_LON,
    DAM_LAT
)

print()
print("UJJANI DAM")
print("==========")
print(
    f"Coordinate : "
    f"{DAM_LAT:.6f}, {DAM_LON:.6f}"
)

print(
    f"Pixel      : "
    f"{dam_r}, {dam_c}"
)

print(
    f"DEM elev   : "
    f"{dem[dam_r, dam_c]:.2f} m"
)

print(
    f"Accum      : "
    f"{acc[dam_r, dam_c]:.0f}"
)


# Search approximately 5 km around dam.
radius = 180

r0 = max(
    0,
    dam_r - radius
)

r1 = min(
    acc.shape[0],
    dam_r + radius + 1
)

c0 = max(
    0,
    dam_c - radius
)

c1 = min(
    acc.shape[1],
    dam_c + radius + 1
)


thresholds = [
    100,
    500,
    1000,
    5000,
    10000,
    20000,
    30000
]


print()
print("NEAREST HIGH-ACCUMULATION CELLS")
print("===============================")


for threshold in thresholds:

    candidates = np.argwhere(
        acc[
            r0:r1,
            c0:c1
        ]
        >= threshold
    )

    if len(candidates) == 0:

        print(
            f"{threshold:>6}: "
            f"none within search radius"
        )

        continue


    best = None


    for local_r, local_c in candidates:

        rr = r0 + local_r
        cc = c0 + local_c

        lon, lat = xy(
            transform,
            rr,
            cc,
            offset="center"
        )

        distance = distance_m(
            DAM_LAT,
            DAM_LON,
            lat,
            lon
        )


        if (
            best is None
            or
            distance < best[0]
        ):

            best = (
                distance,
                rr,
                cc,
                lat,
                lon,
                acc[rr, cc],
                dem[rr, cc]
            )


    (
        distance,
        rr,
        cc,
        lat,
        lon,
        accumulation,
        elevation
    ) = best


    print(
        f"{threshold:>6} : "
        f"{distance:8.1f} m | "
        f"{lat:.6f}, {lon:.6f} | "
        f"acc={accumulation:.0f} | "
        f"elev={elevation:.2f} m"
    )


# Local DEM statistics around the dam.
window_radius = 20

dr0 = max(
    0,
    dam_r - window_radius
)

dr1 = min(
    dem.shape[0],
    dam_r + window_radius + 1
)

dc0 = max(
    0,
    dam_c - window_radius
)

dc1 = min(
    dem.shape[1],
    dam_c + window_radius + 1
)

local_dem = dem[
    dr0:dr1,
    dc0:dc1
]

valid = local_dem[
    np.isfinite(local_dem)
]


print()
print("LOCAL TERRAIN (~1.2 km WINDOW)")
print("==============================")

print(
    f"Minimum : "
    f"{np.min(valid):.2f} m"
)

print(
    f"Maximum : "
    f"{np.max(valid):.2f} m"
)

print(
    f"Mean    : "
    f"{np.mean(valid):.2f} m"
)

print(
    f"Median  : "
    f"{np.median(valid):.2f} m"
)