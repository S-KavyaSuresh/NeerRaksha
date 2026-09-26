# Ujjani population raster — `ujjani_population_2020.tif`

A small window clip of the WorldPop 2020 constrained population raster, used to
estimate **population exposure within the modelled Ujjani flood inundation
extent**. See `metadata.json` for machine-readable provenance.

## Source

| | |
|---|---|
| Dataset | WorldPop Global 2000–2020 **Constrained**, India **2020**, **UN-adjusted** |
| Product path | `Global_2000_2020_Constrained / BSGM / UN-adjusted` |
| Source file | `ind_ppp_2020_UNadj_constrained.tif` (488,818,147 bytes ≈ 466 MB — **kept outside Git**) |
| Native resolution | 3 arc-seconds (≈ 92 m N–S, ≈ 87 m E–W at 18 °N — *not exactly 100 m*) |
| CRS | EPSG:4326 (WGS84 geographic) |
| Units | estimated **persons per pixel** |
| NoData | `-99999.0` → cell has **no modelled residential population** (unsettled / non-residential). Not a surveyed zero, not missing data to impute. |
| DOI | `10.5258/SOTON/WP00684` |
| Official source | https://hub.worldpop.org/doi/10.5258/SOTON/WP00684 |
| License | Creative Commons Attribution 4.0 International (**CC BY 4.0**) — the clipped subset may be redistributed with attribution |
| Date accessed | 2026-09-08 |

### Attribution (required)

> Population data: WorldPop (www.worldpop.org — School of Geography and Environmental Science, University of Southampton). Global High Resolution Population Denominators Project. Constrained individual countries 2020, UN-adjusted, 100 m. DOI: 10.5258/SOTON/WP00684. Licensed under CC BY 4.0.

## The clip

| | |
|---|---|
| File | `ujjani_population_2020.tif` (32,643 bytes ≈ 32 KB, GeoTIFF, DEFLATE + predictor 3, tiled) |
| CRS | EPSG:4326 (**unchanged** — no reprojection) |
| dtype / NoData | float32 / `-99999.0` (**unchanged**) |
| Dimensions | 264 × 192 px @ 0.000833333° (**unchanged** grid) |
| Bounds (WGS84) | 74.97958 – 75.19958 E, 17.98042 – 18.14042 N |
| Valid cells | 6,247 (of 50,688; the other 44,441 are NoData / unsettled) |
| Min / max persons-per-pixel | 4.34 / 93.25 |
| Sum of all valid cells in the clip | ≈ 127,236 persons |
| sha256 | `1d3d5703a1d8cb03007f28b11a394135d5e83f55432e46c2214552150fca2911` |

Requested clip box: `74.98 – 75.20 E, 17.98 – 18.14 N` (the Ujjani DEM extent
`75.00–75.18 / 18.00–18.12` plus ~0.02° margin). Actual bounds are snapped to the
source raster grid.

## How to reproduce the clip

1. Download the source to a directory **outside this repository**:
   `https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/IND/ind_ppp_2020_UNadj_constrained.tif`
2. Window-clip to the Ujjani box (no reprojection, no resampling):
   ```
   gdal_translate -projwin 74.98 18.14 75.20 17.98 \
     ind_ppp_2020_UNadj_constrained.tif ujjani_population_2020.tif \
     -co COMPRESS=DEFLATE -co PREDICTOR=3 -co TILED=YES
   ```
   (The committed file was produced by an equivalent `rasterio` window read — see
   `metadata.json:clip_command`.)
3. Delete the 466 MB source. Only the ~32 KB clip lives in the repo
   (force-added past the global `*.tif` ignore rule).

## Exposure methodology (v1)

```
modelled Delft3D flood_extent.geojson  (per scenario job)
        -> read polygons -> unary union -> ensure EPSG:4326
        -> rasterio.mask(population_raster, [polygon], crop=True, all_touched=False, filled=False)
        -> exclude NoData / non-finite cells
        -> sum persons-per-pixel
        -> estimated population exposed
```

- **Cell-centre inclusion** (`all_touched=False`): a population cell contributes
  when its centre falls inside the flood polygon. Boundary pixels are all-or-nothing.
  Fractional-overlap weighting is a possible future refinement.
- **NoData excluded**: NoData / non-finite cells contribute nothing; no fabricated
  replacement value.
- **No reprojection / resampling** of the count raster (that would redistribute
  people). Only the flood polygon is transformed if its CRS differs.
- Implemented in `backend/simulation/impact.py::_population_impact`.

## What the number means — and does not

**Estimated residential population within the modelled flood inundation extent.**
It is `DERIVED IMPACT (estimate)`, computed from a **2020** population estimate
overlaid on a **modelled (hypothetical)** flood extent.

It is **not**: people displaced, people affected, casualties, evacuees, or a
surveyed / field-measured population. It is **not** the population present at the
time of any specific past or future event. **Validation: NOT PERFORMED.**

## Limitations

- Constrained product — population confined to cells mapped as built settlement
  circa 2020; small or newer settlements may be absent.
- 3-arc-second pixels are not exactly 100 m.
- UN-adjusted to UN World Population Prospects 2019 national totals.
- Input is India's census framework, projected to 2020 by WorldPop.
- If the raster is missing/unreadable the exposure result is `unavailable` — never
  a fabricated fallback.
