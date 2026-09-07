"""Phase 5 — GIS export of the modelled flood extent / depth-band polygons.

Reuses the GeoJSON the engines already produce (EPSG:4326, depth-banded
polygons). Writes:
    geojson : the file as-is
    shp     : ESRI Shapefile bundle zipped (.shp/.shx/.dbf/.prj/.cpg)
    kml     : OGC KML

CRS is preserved (EPSG:4326 for web; a projected EPSG:32643 copy is written for
the shapefile so areas/lengths are metric). geopandas only — no new deps.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

VALID_FORMATS = ("geojson", "shp", "kml")


def _read(flood_geojson: Path):
    import geopandas as gpd

    gdf = gpd.read_file(flood_geojson)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    # keep a tidy attribute set for SHP's 10-char field limit
    keep = [c for c in ("time_min", "depth_min_m", "depth_max_m", "depth_class",
                        "model_type", "scenario_id") if c in gdf.columns]
    return gdf[keep + ["geometry"]] if keep else gdf


def export(flood_geojson: str | Path, out_dir: str | Path, fmt: str) -> Path:
    fmt = fmt.lower()
    if fmt not in VALID_FORMATS:
        raise ValueError(f"format must be one of {VALID_FORMATS}")
    flood_geojson = Path(flood_geojson)
    out_dir = Path(out_dir)
    exports = out_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    if not flood_geojson.exists():
        raise FileNotFoundError(f"flood extent not found: {flood_geojson}")

    if fmt == "geojson":
        target = exports / "flood_extent.geojson"
        target.write_bytes(flood_geojson.read_bytes())
        return target

    gdf = _read(flood_geojson)

    if fmt == "kml":
        target = exports / "flood_extent.kml"
        try:
            gdf.to_file(target, driver="KML")
        except Exception:
            gdf.to_file(target, driver="LIBKML")
        return target

    # fmt == "shp" -> write the .shp bundle (WGS84) + a metric EPSG:32643 copy, zip
    shp_dir = exports / "flood_extent_shp"
    shp_dir.mkdir(exist_ok=True)
    gdf.to_file(shp_dir / "flood_extent_wgs84.shp")
    try:
        gdf.to_crs("EPSG:32643").to_file(shp_dir / "flood_extent_utm43n.shp")
    except Exception:
        pass
    zpath = exports / "flood_extent_shp.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in shp_dir.iterdir():
            zf.write(p, p.name)
    return zpath


def media_type(fmt: str) -> str:
    return {"geojson": "application/geo+json",
            "kml": "application/vnd.google-earth.kml+xml",
            "shp": "application/zip"}[fmt.lower()]
