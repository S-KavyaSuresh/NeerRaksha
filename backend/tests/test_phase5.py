import json
import time
import unittest
import zipfile
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from simulation import config, gis_export, impact, scenario as scn, scenario_run

HAS_DFLOWFM = config.DELFT3D_EXECUTABLE.exists()
RESULTS = config.RESULTS_ROOT.parent / "ujjani_scenario"
UJJANI_BOUNDS = (74.9, 17.9, 75.4, 18.3)  # generous lon/lat box around the domain


def _make_extent(tmp: Path) -> Path:
    """A small valid depth-banded flood-extent GeoJSON in EPSG:4326 near Ujjani."""
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"time_min": 30, "depth_min_m": 1.0, "depth_max_m": 3.0,
                        "depth_class": "1.0-3.0 m", "model_type": "delft3d_dflowfm", "scenario_id": "t"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [75.115, 18.070], [75.135, 18.070], [75.135, 18.090], [75.115, 18.090], [75.115, 18.070]]]}},
    ]}
    p = tmp / "flood_extent.geojson"
    p.write_text(json.dumps(fc), encoding="utf-8")
    return p


class GisExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = RESULTS / "_test_gis"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        cls.fe = _make_extent(cls.tmp)

    def test_geojson_export_is_valid(self):
        p = gis_export.export(self.fe, self.tmp, "geojson")
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertEqual(d["type"], "FeatureCollection")
        self.assertTrue(d["features"])
        self.assertEqual(d["features"][0]["geometry"]["type"], "Polygon")

    def test_shapefile_bundle_with_crs(self):
        p = gis_export.export(self.fe, self.tmp, "shp")
        self.assertTrue(str(p).endswith(".zip"))
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            for ext in (".shp", ".shx", ".dbf", ".prj"):
                self.assertTrue(any(n.endswith(ext) for n in names), ext)
            prj = z.read(next(n for n in names if n.endswith("_wgs84.prj"))).decode()
            self.assertIn("WGS_1984", prj)
            self.assertTrue(any("utm43n" in n for n in names))  # metric copy present

    def test_kml_export_has_polygon_coordinates(self):
        p = gis_export.export(self.fe, self.tmp, "kml")
        text = Path(p).read_text(encoding="utf-8")
        self.assertIn("<coordinates>", text)
        self.assertIn("Polygon", text)

    def test_bad_format_rejected(self):
        with self.assertRaises(ValueError):
            gis_export.export(self.fe, self.tmp, "dwg")


class ImpactAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = RESULTS / "_test_impact"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        cls.fe = _make_extent(cls.tmp)
        cls.r = impact.analyse(cls.fe, cls.tmp, summary_area_km2=4.0)

    def test_roads_intersection_computed(self):
        self.assertEqual(self.r["roads"]["status"], "ok")
        self.assertGreaterEqual(self.r["roads"]["affected_count"], 0)
        self.assertLessEqual(self.r["roads"]["affected_count"], self.r["roads"]["total_in_dataset"])
        self.assertIn("OpenStreetMap", self.r["roads"]["source"])

    def test_facilities_intersection_computed(self):
        self.assertEqual(self.r["facilities"]["status"], "ok")
        self.assertIsInstance(self.r["facilities"]["affected_count"], int)

    def test_missing_settlements_is_unavailable_not_faked(self):
        self.assertEqual(self.r["settlements"]["status"], "unavailable")
        self.assertNotIn("affected_count", self.r["settlements"])

    def test_population_never_fabricated(self):
        self.assertEqual(self.r["population"]["status"], "unavailable")
        self.assertNotIn("count", self.r["population"])
        self.assertNotIn("exposed", self.r["population"])
        self.assertEqual(self.r["validation_status"], "NOT PERFORMED")

    def test_empty_flood_extent_handled(self):
        empty = self.tmp / "empty.geojson"
        empty.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        r = impact.analyse(empty, self.tmp)
        self.assertIn("error", r)
        self.assertEqual(r["population"]["status"], "unavailable")


class SphParticleFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = scenario_run.run_scenario({"engine": "sph", "preset": "small_breach"})
        cls.pf = json.loads(Path(cls.res["results_dir"]).joinpath("particle_frames.json").read_text(encoding="utf-8"))

    def test_particles_exist_and_finite(self):
        self.assertGreater(self.pf["particle_count"], 50)
        self.assertGreater(self.pf["frames"], 2)
        pts = np.array(self.pf["particle_frames"][0]["points"], dtype=float)
        self.assertTrue(np.all(np.isfinite(pts)))
        self.assertEqual(pts.shape[1], 4)  # lon, lat, speed, density

    def test_particle_positions_differ_between_frames(self):
        a = np.array(self.pf["particle_frames"][0]["points"], dtype=float)[:, :2]
        b = np.array(self.pf["particle_frames"][-1]["points"], dtype=float)[:, :2]
        self.assertGreater(np.abs(a - b).max(), 1e-6)

    def test_sph_time_axis_is_seconds_not_minutes(self):
        ts = [f["sph_time_s"] for f in self.pf["particle_frames"]]
        self.assertLess(max(ts), 5.0)  # physical time ~1 s, never "20 minutes"
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(ts[0], 0.0)

    def test_not_georeferenced_flag_and_footprint(self):
        self.assertFalse(self.pf["georeferenced"])
        self.assertIn("not georeferenced", self.pf["disclaimer"].lower())
        self.assertEqual(len(self.pf["footprint"]["corners_lonlat"]), 5)
        self.assertFalse(self.pf["footprint"]["georeferenced"])


@unittest.skipUnless(HAS_DFLOWFM, "dflowfm-cli.exe not available")
class Delft3dVisualisationGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = scenario_run.run_scenario({"engine": "delft3d", "preset": "large_rapid_breach",
                                             "params": {"simulation_duration_s": 900, "output_interval_s": 300}})
        cls.rd = Path(cls.res["results_dir"])
        cls.fe = json.loads((cls.rd / "flood_extent.geojson").read_text(encoding="utf-8"))

    def test_flood_extent_has_polygons_not_empty(self):
        self.assertTrue(self.res["ok"], self.res.get("reason"))
        self.assertTrue(self.fe["features"])
        self.assertTrue(all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in self.fe["features"]))

    def test_coordinates_within_ujjani_bounds_no_shift(self):
        w, s, e, n = UJJANI_BOUNDS
        for f in self.fe["features"]:
            g = f["geometry"]
            rings = g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]
            for ring in rings:
                for lon, lat in ring:
                    self.assertTrue(w <= lon <= e, f"lon {lon} out of Ujjani bounds")
                    self.assertTrue(s <= lat <= n, f"lat {lat} out of Ujjani bounds")

    def test_continuous_field_not_only_single_cell_squares(self):
        # after the gap-fill, at least one polygon should have > 5 vertices
        vc = [len(f["geometry"]["coordinates"][0]) for f in self.fe["features"] if f["geometry"]["type"] == "Polygon"]
        self.assertTrue(any(v > 5 for v in vc), "flood extent is only single-cell squares")

    def test_velocity_vectors_are_linestrings(self):
        vv = self.rd / "velocity_vectors.geojson"
        if vv.exists():
            d = json.loads(vv.read_text(encoding="utf-8"))
            for f in d["features"]:
                self.assertEqual(f["geometry"]["type"], "LineString")
                self.assertIn("speed_mps", f["properties"])


class Phase5ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _wait(self, sid, timeout=180):
        for _ in range(timeout * 2):
            b = self.client.get(f"/api/scenarios/{sid}").json()
            if b["status"] in ("completed", "failed"):
                return b
            time.sleep(0.5)
        raise AssertionError("scenario did not finish")

    def test_impact_export_particles_endpoints(self):
        created = self.client.post("/api/scenarios/run", json={"engine": "sph", "preset": "small_breach"})
        sid = created.json()["id"]
        final = self._wait(sid)
        self.assertEqual(final["status"], "completed", final)

        imp = self.client.get(f"/api/scenarios/{sid}/impact").json()
        self.assertEqual(imp["population"]["status"], "unavailable")
        self.assertEqual(imp["validation_status"], "NOT PERFORMED")
        self.assertIn(imp["roads"]["status"], ("ok", "unavailable"))

        for fmt, ctype in (("geojson", "application/geo+json"),
                           ("kml", "application/vnd.google-earth.kml+xml"),
                           ("shp", "application/zip")):
            r = self.client.get(f"/api/scenarios/{sid}/export/{fmt}")
            self.assertEqual(r.status_code, 200, fmt)
            self.assertEqual(r.headers["content-type"], ctype)
            self.assertGreater(len(r.content), 100)

        pf = self.client.get(f"/api/scenarios/{sid}/particles").json()
        self.assertFalse(pf["georeferenced"])
        self.assertGreater(pf["frames"], 2)
        self.assertLess(pf["physical_duration_s"], 5.0)

    def test_delft3d_particles_endpoint_404(self):
        # a non-SPH run has no particle_frames.json
        created = self.client.post("/api/scenarios/run", json={"engine": "approximate", "preset": "medium_breach"}).json()
        self._wait(created["id"])
        self.assertEqual(self.client.get(f"/api/scenarios/{created['id']}/particles").status_code, 404)

    def test_export_bad_format_rejected(self):
        created = self.client.post("/api/scenarios/run", json={"engine": "approximate", "preset": "small_breach"}).json()
        self._wait(created["id"])
        self.assertEqual(self.client.get(f"/api/scenarios/{created['id']}/export/dwg").status_code, 400)


if __name__ == "__main__":
    unittest.main()
