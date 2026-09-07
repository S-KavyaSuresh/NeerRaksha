"""Minimal DEM -> UGRID (D-Flow FM ``*_net.nc``) builder for the MVP.

Builds a small structured quad mesh from a GeoTIFF using only numpy + rasterio +
netCDF4 (no xarray / meshio / scipy). The variable layout follows the proven
D-Flow FM UGRID structure of the repository test file
``2d_ugrid_net.nc`` (mesh2d_node_x/y/z, mesh2d_edge_nodes, mesh2d_face_nodes, ...).

This does NOT relocate a synthetic DEM to Ujjani — it keeps the DEM's own CRS and
coordinates.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def build_ugrid(dem_path: str | Path, out_path: str | Path, max_cells: int = 4000) -> dict:
    import rasterio  # local import: keeps module importable without rasterio
    import netCDF4

    dem_path = Path(dem_path)
    out_path = Path(out_path)
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM not found: {dem_path}")

    with rasterio.open(dem_path) as src:
        band = src.read(1).astype("float64")
        transform = src.transform
        nodata = src.nodata
        crs = src.crs
        h, w = band.shape

    # Downsample so the mesh stays small and fast for a demo.
    stride = 1
    while (h // (stride + 1)) * (w // (stride + 1)) > max_cells and stride < min(h, w):
        stride += 1
    rows = np.arange(0, h, stride)
    cols = np.arange(0, w, stride)
    ny, nx = len(rows), len(cols)
    if nx < 2 or ny < 2:
        raise ValueError("DEM too small to build a mesh")

    # Node grid (cell corners). Node (j, i) sits at raster coord (rows0..., cols0...).
    node_x = np.zeros((ny, nx))
    node_y = np.zeros((ny, nx))
    node_z = np.zeros((ny, nx))
    for jj, r in enumerate(rows):
        for ii, c in enumerate(cols):
            x, y = transform * (c + 0.5, r + 0.5)
            node_x[jj, ii] = x
            node_y[jj, ii] = y
            z = band[min(r, h - 1), min(c, w - 1)]
            node_z[jj, ii] = np.nan if (nodata is not None and z == nodata) else z

    node_z = np.where(np.isfinite(node_z), node_z, float(np.nanmin(node_z)))

    def nid(j, i):
        return j * nx + i

    faces = []           # 4 node indices per quad, CCW
    edges = set()
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = nid(j, i), nid(j, i + 1), nid(j + 1, i + 1), nid(j + 1, i)
            faces.append((a, b, c, d))
            for u, v in ((a, b), (b, c), (c, d), (d, a)):
                edges.add((min(u, v), max(u, v)))

    node_x_f = node_x.ravel()
    node_y_f = node_y.ravel()
    node_z_f = node_z.ravel()
    edge_nodes = np.array(sorted(edges), dtype="int32")
    face_nodes = np.array(faces, dtype="int32")
    edge_x = node_x_f[edge_nodes].mean(axis=1)
    edge_y = node_y_f[edge_nodes].mean(axis=1)
    face_x = node_x_f[face_nodes].mean(axis=1)
    face_y = node_y_f[face_nodes].mean(axis=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds = netCDF4.Dataset(out_path, "w", format="NETCDF4")
    try:
        ds.Conventions = "CF-1.8 UGRID-1.0"
        ds.institution = "NeerRaksha (hackathon MVP DEM->UGRID)"
        ds.source = f"dem_to_ugrid from {dem_path.name}"
        if crs is not None:
            ds.crs = str(crs)

        ds.createDimension("nmesh2d_node", node_x_f.size)
        ds.createDimension("nmesh2d_edge", edge_nodes.shape[0])
        ds.createDimension("nmesh2d_face", face_nodes.shape[0])
        ds.createDimension("Two", 2)
        ds.createDimension("nmesh2d_face_nodes", 4)

        mesh = ds.createVariable("mesh2d", "i4")
        mesh.cf_role = "mesh_topology"
        mesh.topology_dimension = 2
        mesh.node_coordinates = "mesh2d_node_x mesh2d_node_y"
        mesh.node_dimension = "nmesh2d_node"
        mesh.edge_node_connectivity = "mesh2d_edge_nodes"
        mesh.edge_dimension = "nmesh2d_edge"
        mesh.edge_coordinates = "mesh2d_edge_x mesh2d_edge_y"
        mesh.face_node_connectivity = "mesh2d_face_nodes"
        mesh.face_dimension = "nmesh2d_face"
        mesh.face_coordinates = "mesh2d_face_x mesh2d_face_y"

        def _var(name, data, dims, **attrs):
            v = ds.createVariable(name, data.dtype.str.replace("<", "").replace(">", ""), dims)
            v[:] = data
            for key, val in attrs.items():
                setattr(v, key, val)
            return v

        _var("mesh2d_node_x", node_x_f, ("nmesh2d_node",), units="m", standard_name="projection_x_coordinate")
        _var("mesh2d_node_y", node_y_f, ("nmesh2d_node",), units="m", standard_name="projection_y_coordinate")
        _var("mesh2d_node_z", node_z_f, ("nmesh2d_node",), units="m",
             standard_name="altitude", long_name="bed level at nodes", mesh="mesh2d", location="node")
        _var("mesh2d_edge_nodes", edge_nodes, ("nmesh2d_edge", "Two"),
             cf_role="edge_node_connectivity", start_index=0)
        _var("mesh2d_face_nodes", face_nodes, ("nmesh2d_face", "nmesh2d_face_nodes"),
             cf_role="face_node_connectivity", start_index=0)
        _var("mesh2d_edge_x", edge_x, ("nmesh2d_edge",), units="m")
        _var("mesh2d_edge_y", edge_y, ("nmesh2d_edge",), units="m")
        _var("mesh2d_face_x", face_x, ("nmesh2d_face",), units="m")
        _var("mesh2d_face_y", face_y, ("nmesh2d_face",), units="m")
    finally:
        ds.close()

    return {
        "path": str(out_path),
        "nodes": int(node_x_f.size),
        "edges": int(edge_nodes.shape[0]),
        "faces": int(face_nodes.shape[0]),
        "stride": stride,
        "crs": str(crs) if crs is not None else None,
    }


if __name__ == "__main__":
    import sys
    from . import config

    dem = sys.argv[1] if len(sys.argv) > 1 else str(config.SYNTHETIC_DEM)
    out = sys.argv[2] if len(sys.argv) > 2 else str(config.SIM_WORKDIR / "mesh" / "demo_net.nc")
    print(build_ugrid(dem, out))
