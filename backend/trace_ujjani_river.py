from pathlib import Path

import json
import math

import numpy as np
import rasterio
from rasterio.transform import rowcol, xy


BASE = Path(
    r"C:\Users\kavya\JalDrishti\data\cases"
    r"\ujjani_synthetic\real_dem"
)

FLOWDIR_FILE = BASE / "ujjani_flow_direction.tif"
DEM_FILE = BASE / "ujjani_dem_filled.tif"

OUTPUT_GEOJSON = BASE / "river_centerline_real.geojson"

# Snapped channel point near Ujjani
START_LON = 75.130422
START_LAT = 18.076533

# Limit trace so it cannot loop forever
MAX_STEPS = 20000

# D8 codes:
# N=64, NE=128, E=1, SE=2,
# S=4, SW=8, W=16, NW=32
D8 = {
    64: (-1, 0),
    128: (-1, 1),
    1: (0, 1),
    2: (1, 1),
    4: (1, 0),
    8: (1, -1),
    16: (0, -1),
    32: (-1, -1),
}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0

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
        * R
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


with rasterio.open(FLOWDIR_FILE) as fdir_src:
    fdir = fdir_src.read(1)
    transform = fdir_src.transform
    rows = fdir_src.height
    cols = fdir_src.width


with rasterio.open(DEM_FILE) as dem_src:
    dem = dem_src.read(1)


r, c = rowcol(
    transform,
    START_LON,
    START_LAT
)


coords = []
elevations = []
visited = set()

total_distance = 0.0

previous_lon = None
previous_lat = None


for step in range(MAX_STEPS):

    if (
        r < 0 or
        r >= rows or
        c < 0 or
        c >= cols
    ):
        print("Reached raster boundary.")
        break


    if (r, c) in visited:
        print("Loop detected.")
        break


    visited.add((r, c))


    lon, lat = xy(
        transform,
        r,
        c,
        offset="center"
    )


    coords.append([
        float(lon),
        float(lat)
    ])


    elevations.append(
        float(dem[r, c])
    )


    if (
        previous_lon is not None and
        previous_lat is not None
    ):
        total_distance += haversine_m(
            previous_lat,
            previous_lon,
            lat,
            lon
        )


    previous_lon = lon
    previous_lat = lat


    direction = int(
        fdir[r, c]
    )


    if direction not in D8:
        print(
            f"Stopped: invalid/no-flow direction "
            f"{direction} at step {step}"
        )
        break


    dr, dc = D8[direction]

    r += dr
    c += dc


print()
print("TRACE COMPLETE")
print("==============")

print(
    "Number of points:",
    len(coords)
)

print(
    "Approximate length:",
    f"{total_distance / 1000:.2f} km"
)

if elevations:
    print(
        "Start elevation:",
        f"{elevations[0]:.2f} m"
    )

    print(
        "End elevation:",
        f"{elevations[-1]:.2f} m"
    )

if coords:
    print(
        "Start coordinate:",
        f"{coords[0][1]:.6f}, "
        f"{coords[0][0]:.6f}"
    )

    print(
        "End coordinate:",
        f"{coords[-1][1]:.6f}, "
        f"{coords[-1][0]:.6f}"
    )


geojson = {
    "type": "FeatureCollection",
    "name": "ujjani_real_dem_derived_river",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "DEM-derived downstream channel",
                "source": "ujjani_dem_real_30m",
                "method": "D8 flow-direction trace",
                "synthetic": False,
                "derived_from_dem": True,
                "start_latitude": START_LAT,
                "start_longitude": START_LON,
                "length_km": total_distance / 1000,
                "point_count": len(coords)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            }
        }
    ]
}


with open(
    OUTPUT_GEOJSON,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        geojson,
        f,
        indent=2
    )


print()
print(
    "Created:",
    OUTPUT_GEOJSON
)