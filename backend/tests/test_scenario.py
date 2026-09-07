import json
import time
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from simulation import scenario as scen
from simulation import config

HAS_DFLOWFM = config.DELFT3D_EXECUTABLE.exists()


class ScenarioSchemaTests(unittest.TestCase):
    def test_valid_scenario_accepted_and_fields_preserved(self):
        sc = scen.from_request({"preset": "medium_breach", "breach_width_m": 175.0, "manning_n": 0.04})
        sc.validate()
        self.assertEqual(sc.breach_width_m, 175.0)
        self.assertEqual(sc.manning_n, 0.04)
        self.assertEqual(sc.preset, "medium_breach")
        self.assertEqual(sc.dam_lat, 18.0739)
        self.assertEqual(sc.dam_lon, 75.1200)

    def test_units_in_dict_and_classification_present(self):
        d = scen.from_request({"preset": "small_breach"}).to_dict()
        for f in ("breach_width_m", "breach_depth_m", "breach_formation_time_s",
                  "simulation_duration_s", "output_interval_s", "reservoir_level_m",
                  "manning_n", "gravity_m_s2"):
            self.assertIn(f, d)
        self.assertIn("classification", d)
        self.assertIn("ASSUMPTION / DEMO", d["classification"]["reservoir_level_m / assumed_head_m"])
        self.assertIn("REAL DATA", d["classification"]["dam_lat / dam_lon"])

    def test_invalid_breach_width_rejected(self):
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "breach_width_m": 0}).validate()
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "breach_width_m": -50}).validate()

    def test_invalid_breach_depth_rejected(self):
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "breach_depth_m": 0}).validate()

    def test_invalid_duration_rejected(self):
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "simulation_duration_s": -1}).validate()
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "output_interval_s": 0}).validate()

    def test_formation_time_zero_allowed(self):
        scen.from_request({"preset": "medium_breach", "breach_formation_time_s": 0}).validate()


class DamLocationTests(unittest.TestCase):
    def test_coordinate_transform_and_domain_check(self):
        sc = scen.from_request({"preset": "medium_breach"}).resolve()
        self.assertTrue(sc.in_domain)
        # dam ~ (512698, 1998366) in EPSG:32643
        self.assertAlmostEqual(sc.dam_x_m, 512698.0, delta=50.0)
        self.assertAlmostEqual(sc.dam_y_m, 1998366.0, delta=50.0)
        self.assertIsNotNone(sc.terrain_elev_at_dam_m)
        self.assertGreater(sc.terrain_elev_at_dam_m, 300.0)  # real DEM elevation
        self.assertLess(sc.terrain_elev_at_dam_m, 600.0)

    def test_out_of_domain_dam_rejected(self):
        with self.assertRaises(scen.ScenarioError):
            scen.from_request({"preset": "medium_breach", "dam_lat": 10.0, "dam_lon": 60.0}).resolve()


class HydrographTests(unittest.TestCase):
    def _hg(self, **over):
        sc = scen.from_request({"preset": "medium_breach", **over}).resolve()
        return sc, scen.breach_hydrograph(sc)

    def test_deterministic(self):
        _, a = self._hg()
        _, b = self._hg()
        self.assertEqual(a["series"]["discharge_m3s"], b["series"]["discharge_m3s"])

    def test_finite_nonnegative_and_peak(self):
        _, hg = self._hg()
        q = np.array(hg["series"]["discharge_m3s"])
        self.assertTrue(np.all(np.isfinite(q)))
        self.assertTrue(np.all(q >= 0.0))
        self.assertGreater(hg["peak_discharge_m3s"], 0.0)
        self.assertTrue(np.isfinite(hg["peak_discharge_m3s"]))
        self.assertGreaterEqual(hg["time_of_peak_s"], 0.0)

    def test_changes_with_breach_parameters(self):
        _, small = self._hg(breach_width_m=60, breach_depth_m=6)
        _, large = self._hg(breach_width_m=250, breach_depth_m=25)
        self.assertGreater(large["peak_discharge_m3s"], 5 * small["peak_discharge_m3s"])

    def test_provenance_is_model_derived_not_observed(self):
        _, hg = self._hg()
        self.assertIn("MODEL INPUT / DERIVED", hg["provenance"])
        self.assertIn("NOT an observed", hg["provenance"])
        self.assertIn("weir", hg["formulation"].lower())


class ApproximateAdapterTests(unittest.TestCase):
    def test_approximate_still_runs_via_generalized_scenario(self):
        from simulation import scenario_run
        r = scenario_run.run_scenario({"engine": "approximate", "preset": "medium_breach"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["engine"], "approximate_2d_flood_routing_prototype")
        self.assertGreater(len(r["available_frames"]), 1)
        self.assertEqual(r["validation_status"], "NOT PERFORMED")


class SphAdapterTests(unittest.TestCase):
    def test_sph_adapter_runs_genuine_solver_and_is_finite(self):
        from simulation import scenario_run
        r = scenario_run.run_scenario({"engine": "sph", "preset": "small_breach"})
        self.assertTrue(r["ok"], r.get("reason"))
        self.assertEqual(r["engine"], "sph_wcsph")
        self.assertGreater(r["particle_count"], 50)
        self.assertGreater(r["timesteps"], 5)
        self.assertGreater(r["max_velocity_mps"], 0.0)
        s = r["summary"]
        self.assertTrue(s["finite"])
        self.assertFalse(s["georeferenced"])
        self.assertIn("prototype", s["status"].lower())
        # particles genuinely moved
        self.assertGreater(s["max_displacement_m"], 1e-2)


@unittest.skipUnless(HAS_DFLOWFM, "dflowfm-cli.exe not available")
class Delft3dPhase4Tests(unittest.TestCase):
    def test_phase4_ujjani_scenario_generates_config_and_runs(self):
        from simulation import scenario_run
        r = scenario_run.run_scenario({"engine": "delft3d", "preset": "medium_breach",
                                       "params": {"simulation_duration_s": 900, "output_interval_s": 300}})
        self.assertTrue(r["ok"], r.get("reason"))
        self.assertEqual(r["engine"], "delft3d_dflowfm")
        self.assertGreater(r["max_depth_m"], 0.0)
        self.assertTrue(np.isfinite(r["max_velocity_mps"]))
        self.assertGreater(len(r["available_frames"]), 1)
        self.assertIn("NOT a mesh-edge boundary", r["release_representation"])
        self.assertEqual(r["mesh"]["faces"], 4345)

    def test_phase1_ujjani_regression_still_passes(self):
        # Phase-1 engine is untouched; confirm it still runs the proven Ujjani case.
        from simulation import delft3d_engine
        res = delft3d_engine.run({"simulation_duration_minutes": 5})
        self.assertTrue(res["ok"], res.get("reason"))
        self.assertEqual(res["mesh"]["faces"], 4345)
        self.assertGreater(res["max_depth_m"], 0.0)


class Phase4ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _wait(self, sid, timeout=180):
        for _ in range(timeout * 2):
            b = self.client.get(f"/api/scenarios/{sid}").json()
            if b["status"] in ("completed", "failed"):
                return b
            time.sleep(0.5)
        raise AssertionError("scenario did not finish")

    def test_presets_endpoint_labels_assumptions(self):
        p = self.client.get("/api/scenarios/presets").json()
        self.assertEqual(set(p["presets"]), {"small_breach", "medium_breach", "large_rapid_breach"})
        self.assertIn("ASSUMPTION / DEMO", p["note"])
        self.assertIn("REAL DATA", p["dam_location"]["class"])

    def test_legacy_scenarios_route_untouched(self):
        # DB is not configured in tests -> legacy DB route returns 503, not shadowed by Phase 4
        self.assertEqual(self.client.get("/api/scenarios").status_code, 503)

    def test_sph_scenario_lifecycle_and_results(self):
        created = self.client.post("/api/scenarios/run", json={"engine": "sph", "preset": "small_breach"})
        self.assertEqual(created.status_code, 200)
        sid = created.json()["id"]
        self.assertTrue(sid.startswith("scn-"))
        self.assertEqual(created.json()["validation_status"], "NOT PERFORMED")

        final = self._wait(sid)
        self.assertEqual(final["status"], "completed", final)
        self.assertEqual(final["resolved_engine"], "sph_wcsph")
        self.assertGreater(final["particle_count"], 50)

        res = self.client.get(f"/api/scenarios/{sid}/results").json()
        self.assertEqual(res["validation_status"], "NOT PERFORMED")
        self.assertEqual(res["run_class"], "MODEL DEMONSTRATION / SCENARIO SIMULATION")
        self.assertTrue(res["scenario"]["classification"])

        hg = self.client.get(f"/api/scenarios/{sid}/hydrograph").json()
        self.assertIn("MODEL INPUT / DERIVED", hg["provenance"])
        self.assertGreater(hg["peak_discharge_m3s"], 0.0)

    def test_invalid_scenario_fails_no_fallback(self):
        created = self.client.post("/api/scenarios/run",
                                   json={"engine": "delft3d", "preset": "medium_breach",
                                         "params": {"breach_width_m": -10}}).json()
        final = self._wait(created["id"])
        self.assertEqual(final["status"], "failed")
        self.assertIn("sanity", final["message"].lower())
        self.assertEqual(self.client.get(f"/api/scenarios/{created['id']}/results").status_code, 409)

    def test_engine_failure_reported_not_swallowed(self):
        import app.simulation.scenario_jobs as sj
        original = sj.scenario_run.run_scenario
        sj.scenario_run.run_scenario = lambda *a, **k: {"ok": False, "stage": "delft3d",
                                                        "reason": "forced Delft3D failure for test"}
        try:
            created = self.client.post("/api/scenarios/run", json={"engine": "delft3d"}).json()
            final = self._wait(created["id"])
        finally:
            sj.scenario_run.run_scenario = original
        self.assertEqual(final["status"], "failed")
        self.assertIn("forced Delft3D failure", final["message"])

    def test_unknown_scenario_is_404(self):
        self.assertEqual(self.client.get("/api/scenarios/scn-nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
