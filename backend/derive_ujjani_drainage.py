from pathlib import Path

import numpy as np
import rasterio
from pysheds.grid import Grid


BASE = Path(
    r"C:\Users\kavya\JalDrishti\data\cases"
    r"\ujjani_synthetic\real_dem"
)

DEM_FILE = BASE / "ujjani_dem_cropped.tif"

FILLED_DEM_FILE = BASE / "ujjani_dem_filled.tif"
FLOWDIR_FILE = BASE / "ujjani_flow_direction.tif"
FLOWACC_FILE = BASE / "ujjani_flow_accumulation.tif"


print("Loading DEM...")

grid = Grid.from_raster(
    str(DEM_FILE)
)

dem = grid.read_raster(
    str(DEM_FILE)
)


print("Filling pits...")

pit_filled = grid.fill_pits(
    dem
)


print("Filling depressions...")

depression_filled = grid.fill_depressions(
    pit_filled
)


print("Resolving flats...")

inflated_dem = grid.resolve_flats(
    depression_filled
)


# Standard ESRI-style D8 direction mapping used by pysheds:
#
# N   = 64
# NE  = 128
# E   = 1
# SE  = 2
# S   = 4
# SW  = 8
# W   = 16
# NW  = 32

DIRMAP = (
    64,
    128,
    1,
    2,
    4,
    8,
    16,
    32
)


print("Computing flow direction...")

fdir = grid.flowdir(
    inflated_dem,
    dirmap=DIRMAP
)


print("Computing flow accumulation...")

acc = grid.accumulation(
    fdir,
    dirmap=DIRMAP
)


print("Saving outputs...")


with rasterio.open(DEM_FILE) as src:

    # --------------------------------------------------------
    # FILLED DEM
    # --------------------------------------------------------

    filled_array = np.asarray(
        inflated_dem,
        dtype=np.float32
    )

    filled_profile = src.profile.copy()

    filled_profile.update(
        dtype="float32",
        nodata=-9999,
        compress="lzw"
    )

    with rasterio.open(
        FILLED_DEM_FILE,
        "w",
        **filled_profile
    ) as dst:

        dst.write(
            filled_array,
            1
        )


    # --------------------------------------------------------
    # FLOW DIRECTION
    # --------------------------------------------------------

    flowdir_array = np.asarray(
        fdir,
        dtype=np.int16
    )

    flowdir_profile = src.profile.copy()

    flowdir_profile.update(
        dtype="int16",
        nodata=0,
        compress="lzw"
    )

    with rasterio.open(
        FLOWDIR_FILE,
        "w",
        **flowdir_profile
    ) as dst:

        dst.write(
            flowdir_array,
            1
        )


    # --------------------------------------------------------
    # FLOW ACCUMULATION
    # --------------------------------------------------------

    acc_array = np.asarray(
        acc,
        dtype=np.float32
    )

    acc_profile = src.profile.copy()

    acc_profile.update(
        dtype="float32",
        nodata=0,
        compress="lzw"
    )

    with rasterio.open(
        FLOWACC_FILE,
        "w",
        **acc_profile
    ) as dst:

        dst.write(
            acc_array,
            1
        )


print()
print("DONE")

print()
print("Filled DEM:")
print(FILLED_DEM_FILE)

print()
print("Flow direction:")
print(FLOWDIR_FILE)

print()
print("Flow accumulation:")
print(FLOWACC_FILE)

print()
print(
    "Maximum flow accumulation:",
    float(
        np.nanmax(
            acc_array
        )
    )
)