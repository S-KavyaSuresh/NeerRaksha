import json
import time
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from simulation import sph_solver, sph_engine


def _small_cfg():
    cfg = sph_solver.SPHConfig()
    cfg.dx = 0.035          # coarser than production (0.032) but still resolved
    cfg.t_end = 0.30
    cfg.n_frames = 6
    return cfg


class SPHSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = sph_solver.run(_small_cfg())
        cls.m = cls.res.metrics

    def test_initialisation_and_particle_count(self):
        self.assertGreater(self.res.positions0.shape[0], 50)
        self.assertEqual(self.res.positions0.shape[1], 2)
        self.assertEqual(self.m["particle_count"], self.res.positions0.shape[0])

    def test_multiple_timesteps_executed(self):
        self.assertGreater(self.m["timesteps"], 5)
        self.assertGreater(self.m["frames"], 2)

    def test_particles_moved(self):
        first = self.res.frames[0]["x"]
        last = self.res.frames[-1]["x"]
        self.assertGreater(np.abs(last - first).max(), 1e-3)
        self.assertGreater(self.m["max_displacement_m"], 1e-3)

    def test_velocity_becomes_nonzero(self):
        self.assertGreater(self.m["max_velocity_mps"], 0.0)

    def test_density_pressure_velocity_positions_finite(self):
        for f in self.res.frames:
            for key in ("x", "v", "rho", "p"):
                self.assertTrue(np.all(np.isfinite(f[key])), key)
        self.assertTrue(self.m["finite"])
        self.assertGreater(self.m["min_density"], 0.0)
        self.assertLess(self.m["max_density"], 5.0 * self.res.config.rho0)
        self.assertGreaterEqual(self.m["min_pressure_pa"], 0.0)
        self.assertTrue(np.isfinite(self.m["max_pressure_pa"]))

    def test_bulk_density_is_physical(self):
        # No density blow-up, and the bulk (median) stays within the
        # free-surface deficit expected of summation-density WCSPH at this
        # demonstration resolution. Production resolution gives ~3%.
        self.assertLess(self.m["max_density"], 1.25 * self.res.config.rho0)
        self.assertGreater(self.m["median_density"], 0.80 * self.res.config.rho0)
        self.assertLess(self.m["density_relative_error_pct"], 20.0)

    def test_reproducible(self):
        res2 = sph_solver.run(_small_cfg())
        self.assertTrue(np.array_equal(self.res.frames[-1]["x"], res2.frames[-1]["x"]))


class SPHApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _wait(self, sim_id, timeout=120):
        for _ in range(timeout * 4):
            body = self.client.get(f"/api/simulations/{sim_id}").json()
            if body["status"] in ("completed", "failed", "cancelled"):
                return body
            time.sleep(0.25)
        raise AssertionError("SPH simulation did not finish")

    def test_sph_lifecycle_and_metadata(self):
        created = self.client.post("/api/simulations", json={
            "engine": "sph",
            "scenario": {"preset": "sph_demo", "sph_duration_s": 0.3, "sph_particles_target": 140},
        })
        self.assertEqual(created.status_code, 200)
        sim_id = created.json()["id"]
        self.assertIn(created.json()["status"], ("queued", "running"))

        final = self._wait(sim_id)
        self.assertEqual(final["status"], "completed", final)
        self.assertEqual(final["resolved_engine"], "sph_demo")
        self.assertFalse(final["validated_hydraulic_output"])
        self.assertIn("not validated", (final["disclaimer"] or "").lower())
        self.assertGreater(final["particle_count"], 50)
        self.assertGreater(final["timesteps"], 5)
        self.assertGreater(final["max_velocity_mps"], 0.0)
        self.assertGreater(len(final["available_frames"]), 2)

        summary = self.client.get(f"/api/simulations/{sim_id}/summary").json()
        self.assertEqual(summary["data_class"], "MODEL OUTPUT")
        self.assertIn("sph", summary)
        self.assertIn("kernel", summary["sph"])

        timeline = self.client.get(f"/api/simulations/{sim_id}/timeline").json()
        self.assertGreater(len(timeline["values"]), 2)
        first = timeline["available_frames"][0]
        last = timeline["available_frames"][-1]
        f0 = self.client.get(f"/api/simulations/{sim_id}/timeline/{first}").json()
        fl = self.client.get(f"/api/simulations/{sim_id}/timeline/{last}").json()
        self.assertEqual(f0["type"], "FeatureCollection")
        # genuine distinct frames: the state at the two ends is not identical
        self.assertNotEqual(json.dumps(f0["features"]), json.dumps(fl["features"]))
        self.assertEqual(self.client.get(f"/api/simulations/{sim_id}/results/flood_extent").status_code, 200)

    def test_sph_failure_is_not_silently_replaced(self):
        # sph_duration_s clamps to >= 0.3, so force failure by monkeypatching the solver
        import simulation.sph_engine as eng
        original = eng.sph_solver.run

        def boom(*a, **k):
            raise RuntimeError("forced SPH instability for test")

        eng.sph_solver.run = boom
        try:
            created = self.client.post("/api/simulations", json={"engine": "sph", "scenario": {}}).json()
            final = self._wait(created["id"])
        finally:
            eng.sph_solver.run = original

        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["resolved_engine"], "sph_demo")
        self.assertFalse(final["fallback_used"])
        self.assertIn("sph", (final["error"]["detail"] or "").lower())


if __name__ == "__main__":
    unittest.main()
