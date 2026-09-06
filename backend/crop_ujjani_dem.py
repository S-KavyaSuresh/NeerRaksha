import rasterio
from rasterio.windows import from_bounds

src_path = r"C:\Users\kavya\JalDrishti\data\cases\ujjani_synthetic\real_dem\ujjani_dem_real_30m.tif"

dst_path = r"C:\Users\kavya\JalDrishti\data\cases\ujjani_synthetic\real_dem\ujjani_dem_cropped.tif"

# Initial study bounds around Ujjani + downstream reach.
# We can refine these later after checking the real Bhima direction.
west = 75.05
south = 18.00
east = 75.65
north = 18.20

with rasterio.open(src_path) as src:
    window = from_bounds(
        west,
        south,
        east,
        north,
        src.transform
    )

    window = window.round_offsets().round_lengths()

    data = src.read(
        window=window
    )

    transform = src.window_transform(
        window
    )

    profile = src.profile.copy()

    profile.update(
        height=data.shape[1],
        width=data.shape[2],
        transform=transform
    )

    with rasterio.open(
        dst_path,
        "w",
        **profile
    ) as dst:
        dst.write(data)

print("Created:", dst_path)