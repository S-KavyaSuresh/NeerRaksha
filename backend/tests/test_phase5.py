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
        self.assertEqual(self.r["roads"]["road_filter"], "highway IS NOT NULL")

    def test_road_length_uses_projected_crs_not_scalar_degrees(self):
        import geopandas as gpd
        from shapely.geometry import shape
        from shapely.ops import unary_union

        roads = self.r["roads"]
        self.assertEqual(roads["length_crs"], "EPSG:32643")
        got = roads["approx_flooded_length_km"]

        fe = json.loads(Path(self.fe).read_text(encoding="utf-8"))
        flood = unary_union([shape(f["geometry"]).buffer(0) for f in fe["features"]])
        g = gpd.read_file(impact.ROADS)
        g = g[g.geometry.type.isin(["LineString", "MultiLineString"])]
        inter = g.to_crs("EPSG:32643").intersection(
            gpd.GeoSeries([flood], crs="EPSG:4326").to_crs("EPSG:32643").iloc[0])
        proper_km = float(inter.length.sum()) / 1000.0
        scalar_km = float(g.intersection(flood).length.sum()) * 111.32  # the OLD method

        # matches the projected computation, and is NOT the old degrees*111.32 value
        self.assertAlmostEqual(got, round(proper_km, 2), places=2)
        self.assertGreater(abs(got - scalar_km), 0.01 * proper_km)

    def test_facilities_intersection_computed(self):
        self.assertEqual(self.r["facilities"]["status"], "ok")
        self.assertIsInstance(self.r["facilities"]["affected_count"], int)
        self.assertEqual(self.r["facilities"]["category_attribute"], "amenity")
        self.assertIn("hospital", self.r["facilities"]["total_by_type"])

    def test_facility_type_breakdown_from_real_amenity_attribute(self):
        # an extent over the Indapur facility cluster -> non-zero, categorised
        ind = self.tmp / "indapur.geojson"
        ind.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [75.020, 18.110], [75.035, 18.110], [75.035, 18.125],
                 [75.020, 18.125], [75.020, 18.110]]]}}]}), encoding="utf-8")
        f = impact.analyse(ind, self.tmp)["facilities"]
        self.assertEqual(f["status"], "ok")
        self.assertGreater(f["affected_count"], 0)
        self.assertEqual(sum(f["by_type"].values()), f["affected_count"])
        allowed = {"hospital", "school", "college", "clinic", "unknown"}
        self.assertTrue(set(f["by_type"]).issubset(allowed), f["by_type"])
        self.assertTrue(set(f["total_by_type"]).issubset(allowed), f["total_by_type"])

    def test_missing_gpkg_is_unavailable_but_curated_layers_still_ok(self):
        original = impact.GPKG
        impact.GPKG = impact.OSM / "does_not_exist.gpkg"
        try:
            r = impact.analyse(self.fe, self.tmp)
        finally:
            impact.GPKG = original
        self.assertEqual(r["buildings"]["status"], "unavailable")
        self.assertIn("not found", r["buildings"]["reason"])
        self.assertEqual(r["settlements"]["status"], "unavailable")
        # roads/facilities come from curated GeoJSON, unaffected by the missing GPKG
        self.assertEqual(r["roads"]["status"], "ok")
        self.assertEqual(r["facilities"]["status"], "ok")

    def test_buildings_intersection_from_real_gpkg(self):
        b = self.r["buildings"]
        self.assertEqual(b["status"], "ok")
        self.assertIn("osm_ujjani.gpkg", b["source"])
        self.assertEqual(b["crs"], "EPSG:4326")
        self.assertGreater(b["total_in_dataset"], 0)
        self.assertGreaterEqual(b["affected_count"], 0)
        self.assertLessEqual(b["affected_count"], b["total_in_dataset"])

    def test_settlements_from_real_gpkg_place_nodes(self):
        s = self.r["settlements"]
        self.assertEqual(s["status"], "ok")
        self.assertIn("osm_ujjani.gpkg", s["source"])
        self.assertGreater(s["total_in_dataset"], 0)
        self.assertGreaterEqual(s["affected_count"], 0)
        self.assertLessEqual(s["affected_count"], s["total_in_dataset"])
        self.assertEqual(len(s["affected"]), s["affected_count"])

    def test_zero_affected_is_not_reported_as_unavailable(self):
        # a flood extent far from any asset -> analysis still runs, counts are 0
        far = self.tmp / "far.geojson"
        far.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [70.0, 10.0], [70.001, 10.0], [70.001, 10.001], [70.0, 10.001], [70.0, 10.0]]]}}]}),
            encoding="utf-8")
        r = impact.analyse(far, self.tmp)
        self.assertEqual(r["buildings"]["status"], "ok")
        self.assertEqual(r["buildings"]["affected_count"], 0)
        self.assertEqual(r["settlements"]["status"], "ok")
        self.assertEqual(r["settlements"]["affected_count"], 0)

    def test_population_never_fabricated(self):
        pop = self.r["population"]
        self.assertIn(pop["status"], ("ok", "unavailable"))
        if pop["status"] == "unavailable":
            self.assertNotIn("population_exposed_estimate", pop)
        else:
            # real raster present -> a genuine DERIVED estimate, never a fabricated one
            self.assertIsInstance(pop["population_exposed_estimate"], int)
            self.assertGreaterEqual(pop["population_exposed_estimate"], 0)
            self.assertIn("estimate", pop["classification"].lower())
            self.assertEqual(pop["validation_status"], "NOT PERFORMED")
            self.assertIn("2020", pop["temporal_caveat"])
        self.assertEqual(self.r["validation_status"], "NOT PERFORMED")

    def test_empty_flood_extent_handled(self):
        empty = self.tmp / "empty.geojson"
        empty.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        r = impact.analyse(empty, self.tmp)
        self.assertIn("error", r)
        self.assertEqual(r["population"]["status"], "unavailable")


# Phase-1 demonstration extent that must NEVER be what the scenario impact uses.
PHASE1_DEMO_EXTENT = config.DELFT3D_RESULTS / "flood_extent.geojson"


class ScenarioResultIsolationTests(unittest.TestCase):
    """Two scenario runs must not share a results directory (so a later run cannot
    overwrite the flood extent an earlier job's /impact still resolves to)."""

    def test_each_run_id_gets_its_own_results_dir_and_extent(self):
        a = scenario_run.run_scenario({"engine": "sph", "preset": "small_breach"}, run_id="scn-isolation-a")
        b = scenario_run.run_scenario({"engine": "sph", "preset": "small_breach"}, run_id="scn-isolation-b")
        self.assertTrue(a["ok"] and b["ok"], (a.get("reason"), b.get("reason")))
        da, db = Path(a["results_dir"]), Path(b["results_dir"])
        self.assertNotEqual(da, db)
        self.assertEqual(da.name, "scn-isolation-a")
        self.assertEqual(db.name, "scn-isolation-b")
        # both extents still exist after the second run finished
        self.assertTrue((da / "flood_extent.geojson").exists())
        self.assertTrue((db / "flood_extent.geojson").exists())
        # not the shared legacy path, not the Phase-1 demo path
        self.assertNotEqual(da.resolve(), (scenario_run.RESULTS_ROOT / "sph").resolve())
        self.assertNotEqual(da.resolve(), PHASE1_DEMO_EXTENT.parent.resolve())


class ScenarioImpactRoutingTests(unittest.TestCase):
    """GET /api/scenarios/{id}/impact must analyse THAT job's completed scenario
    flood extent — near Ujjani (~75E,18N) — not the Phase-1 demo extent."""

    def setUp(self):
        self.client = TestClient(app)
        self.tmp = RESULTS / "_test_impact_routing"
        self.tmp.mkdir(parents=True, exist_ok=True)

    def _wait(self, sid, timeout=30):
        for _ in range(timeout * 2):
            b = self.client.get(f"/api/scenarios/{sid}").json()
            if b["status"] in ("completed", "failed"):
                return b
            time.sleep(0.5)
        raise AssertionError("scenario did not finish")

    def test_impact_endpoint_reads_that_jobs_completed_extent(self):
        import app.simulation.scenario_jobs as sj

        # a distinctive Ujjani flood extent, clearly inside the domain and clearly
        # different from the Phase-1 demo blob near 75.00E/18.00N
        run_dir = self.tmp / f"run_{int(time.time())}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "flood_extent.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "features": [{
                "type": "Feature",
                "properties": {"time_min": 60, "depth_min_m": 1.0, "depth_max_m": 3.0,
                               "model_type": "delft3d_dflowfm", "validated_hydraulic_output": False,
                               "scenario_id": "large_rapid_breach"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [75.110, 18.060], [75.130, 18.060], [75.130, 18.080],
                    [75.110, 18.080], [75.110, 18.060]]]}}]}), encoding="utf-8")

        original = sj.scenario_run.run_scenario
        sj.scenario_run.run_scenario = lambda *a, **k: {
            "ok": True, "engine": "delft3d_dflowfm", "engine_label": "Delft3D D-Flow FM",
            "results_dir": str(run_dir), "available_frames": [60],
            "summary": {"flooded_area_km2": 4.2}, "validation_status": "NOT PERFORMED",
        }
        orig_pop = impact.POPULATION
        impact.POPULATION = self.tmp / "no_population_here.tif"  # isolate: this test is about routing
        try:
            created = self.client.post("/api/scenarios/run",
                                       json={"engine": "delft3d", "preset": "large_rapid_breach"}).json()
            final = self._wait(created["id"])
            self.assertEqual(final["status"], "completed", final)
            imp = self.client.get(f"/api/scenarios/{created['id']}/impact").json()
        finally:
            sj.scenario_run.run_scenario = original
            impact.POPULATION = orig_pop

        # analysed THIS job's extent: bounds match the file we wrote
        w, s, e, n = imp["flood_bounds_lonlat"]
        self.assertAlmostEqual(w, 75.110, places=3)
        self.assertAlmostEqual(s, 18.060, places=3)
        self.assertAlmostEqual(e, 75.130, places=3)
        self.assertAlmostEqual(n, 18.080, places=3)
        # around Ujjani, NOT the Phase-1 demo extent near 75.00/18.00
        self.assertTrue(74.9 <= w <= 75.4 and 17.9 <= s <= 18.3)
        self.assertGreater(w, 75.05)
        # scientific labels preserved, population still honestly unavailable
        self.assertEqual(imp["flooded_area_km2"], 4.2)
        self.assertEqual(imp["population"]["status"], "unavailable")
        self.assertEqual(imp["validation_status"], "NOT PERFORMED")
        self.assertIn("DERIVED", imp["data_classification"]["counts"])
        # provenance: the payload names the engine/scenario that produced the extent
        self.assertEqual(imp["source"]["engine"], "delft3d_dflowfm")
        self.assertEqual(imp["source"]["engine_label"], "Delft3D D-Flow FM")
        self.assertEqual(imp["source"]["scenario_id"], created["id"])
        self.assertIn("/api/scenarios/", imp["source"]["api"])
        self.assertTrue(imp["source"]["flood_extent_source"].endswith("flood_extent.geojson"))

    def test_simulations_impact_provenance_marks_non_scenario_path(self):
        import app.simulation.jobs as jb

        created = self.client.post("/api/simulations", json={"scenario": {}, "engine": "approximate"}).json()
        for _ in range(120):
            b = self.client.get(f"/api/simulations/{created['id']}").json()
            if b["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)
        rd = jb.results_path(created["id"])
        stray = (rd / "impact.json") if rd else None
        pre_existing = bool(stray and stray.exists())
        orig_pop = impact.POPULATION
        impact.POPULATION = (rd or RESULTS) / "no_population_here.tif"  # isolate: this test is about provenance
        try:
            imp = self.client.get(f"/api/simulations/{created['id']}/impact").json()
            self.assertIn("source", imp)
            self.assertIn("general simulation lifecycle", imp["source"]["api"])
            self.assertIn("approximate", (imp["source"]["engine"] or "").lower())
            self.assertEqual(imp["population"]["status"], "unavailable")
        finally:
            impact.POPULATION = orig_pop
            # impact.analyse caches impact.json next to the extent; the approximate
            # engine reuses a tracked demo results dir, so don't leave an artifact
            if stray and stray.exists() and not pre_existing:
                stray.unlink()

    def test_population_overlay_uses_that_jobs_flood_extent(self):
        import app.simulation.scenario_jobs as sj

        run_dir = self.tmp / f"poprun_{int(time.time())}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "flood_extent.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {"scenario_id": "large_rapid_breach"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [75.110, 18.060], [75.130, 18.060], [75.130, 18.080],
                    [75.110, 18.080], [75.110, 18.060]]]}}]}), encoding="utf-8")

        # synthetic population raster covering that extent: 4x4 @ 0.01deg from (75.10, 18.09)
        # flood box 75.11-75.13 / 18.06-18.08 -> centres of cols 1-2, rows 1-2 = 4 cells * 25
        pop_tif = self.tmp / "pop_route.tif"
        _pop_raster(pop_tif, [[25, 25, 25, 25]] * 4, west=75.10, north=18.09, res=0.01)

        original = sj.scenario_run.run_scenario
        sj.scenario_run.run_scenario = lambda *a, **k: {
            "ok": True, "engine": "delft3d_dflowfm", "engine_label": "Delft3D D-Flow FM",
            "results_dir": str(run_dir), "available_frames": [60],
            "summary": {"flooded_area_km2": 4.2}, "validation_status": "NOT PERFORMED",
        }
        orig_pop, orig_meta = impact.POPULATION, impact.POPULATION_META
        impact.POPULATION, impact.POPULATION_META = pop_tif, pop_tif.with_suffix(".json")
        try:
            created = self.client.post("/api/scenarios/run",
                                       json={"engine": "delft3d", "preset": "large_rapid_breach"}).json()
            self._wait(created["id"])
            imp = self.client.get(f"/api/scenarios/{created['id']}/impact").json()
        finally:
            sj.scenario_run.run_scenario = original
            impact.POPULATION, impact.POPULATION_META = orig_pop, orig_meta

        self.assertEqual(imp["population"]["status"], "ok")
        self.assertEqual(imp["population"]["population_exposed_estimate"], 100)  # 4 * 25 from THIS extent
        self.assertIn("population_dataset", imp["source"])
        self.assertIn("WorldPop", imp["source"]["population_dataset"]["dataset"])
        self.assertEqual(imp["source"]["population_dataset"]["year"], 2020)


def _pop_raster(path: Path, values, *, west=75.00, north=18.04, res=0.01, nodata=-99999.0):
    """Write a tiny EPSG:4326 persons-per-pixel test raster. Algorithm fixture
    only — never application/demo data."""
    import rasterio
    from rasterio.transform import from_origin

    arr = np.asarray(values, dtype="float32")
    transform = from_origin(west, north, res, res)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs="EPSG:4326", transform=transform,
                       nodata=nodata) as dst:
        dst.write(arr, 1)
    return path


def _box(w, s, e, n):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Polygon", "coordinates": [[
             [w, s], [e, s], [e, n], [w, n], [w, s]]]}}]}


class PopulationExposureTests(unittest.TestCase):
    """DERIVED IMPACT population estimate: WorldPop-style persons/pixel raster
    masked by the modelled flood polygon, cell-centre inclusion, NoData excluded."""

    def setUp(self):
        self.tmp = RESULTS / "_test_population"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self._orig_pop, self._orig_meta = impact.POPULATION, impact.POPULATION_META

    def tearDown(self):
        impact.POPULATION, impact.POPULATION_META = self._orig_pop, self._orig_meta

    def _run(self, raster, extent_fc):
        impact.POPULATION = raster
        impact.POPULATION_META = raster.with_suffix(".json")  # absent -> defaults
        fe = self.tmp / "fe.geojson"
        fe.write_text(json.dumps(extent_fc), encoding="utf-8")
        return impact.analyse(fe, self.tmp)["population"]

    def test_1_population_overlap_sum_is_centre_inclusion(self):
        r = _pop_raster(self.tmp / "p1.tif", [[10, 10, 10, 10]] * 4)  # 75.00-75.04 / 18.00-18.04
        # box covers the 2x2 block of cell-centres at cols 0-1, rows 0-1
        pop = self._run(r, _box(75.001, 18.021, 75.019, 18.039))
        self.assertEqual(pop["status"], "ok")
        self.assertEqual(pop["population_exposed_estimate"], 40)  # 4 cells * 10
        self.assertEqual(pop["valid_cells"], 4)

    def test_2_nodata_contributes_nothing(self):
        vals = [[10, 10, 10, 10] for _ in range(4)]
        vals[0][0] = -99999.0  # one NoData cell inside the box
        r = _pop_raster(self.tmp / "p2.tif", vals)
        pop = self._run(r, _box(75.001, 18.021, 75.019, 18.039))
        self.assertEqual(pop["status"], "ok")
        self.assertEqual(pop["population_exposed_estimate"], 30)  # 3 valid * 10, NoData excluded
        self.assertEqual(pop["valid_cells"], 3)
        self.assertIn("excluded", pop["nodata_handling"].lower())

    def test_3_zero_exposure_is_ok_with_zero(self):
        r = _pop_raster(self.tmp / "p3.tif", [[10, 10, 10, 10]] * 4)
        pop = self._run(r, _box(70.0, 10.0, 70.02, 10.02))  # nowhere near the raster
        self.assertEqual(pop["status"], "ok")
        self.assertEqual(pop["population_exposed_estimate"], 0)
        self.assertIn("not", (pop.get("note") or "").lower())

    def test_4_missing_raster_is_unavailable(self):
        impact.POPULATION = self.tmp / "does_not_exist.tif"
        impact.POPULATION_META = self.tmp / "does_not_exist.json"
        fe = self.tmp / "fe.geojson"
        fe.write_text(json.dumps(_box(75.001, 18.021, 75.019, 18.039)), encoding="utf-8")
        pop = impact.analyse(fe, self.tmp)["population"]
        self.assertEqual(pop["status"], "unavailable")
        self.assertIn("not found", pop["reason"])
        self.assertNotIn("population_exposed_estimate", pop)

    def test_5_provenance_and_labels_present(self):
        r = _pop_raster(self.tmp / "p5.tif", [[10, 10, 10, 10]] * 4)
        pop = self._run(r, _box(75.001, 18.021, 75.019, 18.039))
        for k in ("dataset", "year", "crs", "method", "nodata_handling", "doi",
                  "classification", "temporal_caveat", "validation_status"):
            self.assertIn(k, pop)
        self.assertIn("WorldPop", pop["dataset"])
        self.assertEqual(pop["year"], 2020)
        self.assertEqual(pop["crs"], "EPSG:4326")
        self.assertEqual(pop["validation_status"], "NOT PERFORMED")
        self.assertIn("estimate", pop["classification"].lower())
        self.assertNotIn("observed", pop["classification"].split("—")[0].lower())

    def test_6_no_synthetic_data_dependency(self):
        import inspect
        src = inspect.getsource(impact._population_impact)
        for bad in ("prototype.js", "prototypeImpact", "sample.js", "is_sample",
                    "comparison.js", "18420", "44444444", "83.0", "21.0"):
            self.assertNotIn(bad, src)
        # result is a pure function of raster + polygon
        r = _pop_raster(self.tmp / "p6.tif", [[7, 3, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        pop = self._run(r, _box(75.001, 18.031, 75.029, 18.039))  # top row, cols 0-2 centres
        self.assertEqual(pop["population_exposed_estimate"], 10)  # 7 + 3 + 0

    def test_7_population_coexists_with_osm_layers(self):
        r = _pop_raster(self.tmp / "p7.tif", [[10, 10, 10, 10]] * 4)
        impact.POPULATION = r
        impact.POPULATION_META = r.with_suffix(".json")
        fe = self.tmp / "fe.geojson"
        fe.write_text(json.dumps(_box(75.001, 18.021, 75.019, 18.039)), encoding="utf-8")
        full = impact.analyse(fe, self.tmp)
        self.assertEqual(full["population"]["status"], "ok")
        for layer in ("roads", "facilities", "buildings", "settlements"):
            self.assertIn(full[layer]["status"], ("ok", "unavailable"))
        self.assertEqual(full["roads"]["status"], "ok")


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
        self.assertIn(imp["population"]["status"], ("ok", "unavailable"))
        if imp["population"]["status"] == "ok":
            self.assertGreaterEqual(imp["population"]["population_exposed_estimate"], 0)
            self.assertEqual(imp["population"]["validation_status"], "NOT PERFORMED")
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
