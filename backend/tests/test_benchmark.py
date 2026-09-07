import json
import time
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from simulation import benchmark, config

FAST_DX = 0.014          # coarse SPH spacing so execution tests stay quick
HAS_DFLOWFM = config.DELFT3D_EXECUTABLE.exists()


class BenchmarkMetadataTests(unittest.TestCase):
    def test_benchmark_is_traceable_and_not_fabricated(self):
        b = benchmark.BENCHMARK
        self.assertEqual(b["id"], "dry_bed_dam_break_ritter_1892")
        self.assertFalse(b["reference"]["fabricated_values"])
        self.assertIn("Ritter", b["reference"]["primary_source"])
        self.assertIn("1892", b["reference"]["primary_source"])
        self.assertTrue(b["reference"]["geometry_lineage"])

    def test_geometry_is_self_consistent(self):
        g = benchmark.BENCHMARK["geometry"]
        self.assertAlmostEqual(g["column_height_H0_m"], 2 * g["column_width_a_m"], places=6)
        self.assertAlmostEqual(g["aspect_ratio_H0_over_a"], 2.0, places=6)
        self.assertEqual(g["dam_position_x0_m"], g["column_width_a_m"])


class RitterAnalyticTests(unittest.TestCase):
    def test_front_law(self):
        self.assertAlmostEqual(benchmark.ritter_front(0.0), benchmark.X0, places=9)
        f1 = benchmark.ritter_front(0.05)
        f2 = benchmark.ritter_front(0.10)
        self.assertGreater(f1, benchmark.X0)
        self.assertAlmostEqual(f2 - benchmark.X0, 2 * (f1 - benchmark.X0), places=6)  # linear in t

    def test_profile_bounds(self):
        x = np.linspace(0, benchmark.BOX[0], 200)
        h = benchmark.ritter_profile(x, 0.1)
        self.assertTrue(np.all(np.isfinite(h)))
        self.assertLessEqual(h.max(), benchmark.H0 + 1e-9)
        self.assertGreaterEqual(h.min(), 0.0)
        self.assertTrue(np.all(h[x > benchmark.ritter_front(0.1)] == 0.0))

    def test_arrival_positive(self):
        self.assertGreater(benchmark.ritter_arrival(benchmark.X0 + 0.3), 0.0)


class MetricFunctionTests(unittest.TestCase):
    def test_rmse_mae_basic_and_edges(self):
        self.assertAlmostEqual(benchmark.rmse([1, 2, 3], [1, 2, 3]), 0.0)
        self.assertAlmostEqual(benchmark.mae([0, 0], [1, 3]), 2.0)
        self.assertIsNone(benchmark.rmse([], []))
        self.assertIsNone(benchmark.mae([1, 2], [1, 2, 3]))

    def test_mean_relative_error_zero_reference(self):
        self.assertIsNone(benchmark.mean_relative_error([1, 2], [0, 0]))
        self.assertAlmostEqual(benchmark.mean_relative_error([2, 4], [1, 2]), 1.0)

    def test_wet_iou_identical_disjoint_and_dry(self):
        x = np.linspace(0, 1, 101)
        a = np.where(x < 0.5, 0.1, 0.0)
        self.assertAlmostEqual(benchmark.wet_iou(x, a, a, 0.005)["iou"], 1.0, places=6)
        b = np.where(x >= 0.5, 0.1, 0.0)
        self.assertAlmostEqual(benchmark.wet_iou(x, a, b, 0.005)["iou"], 0.0, places=6)
        dry = np.zeros_like(x)
        self.assertIsNone(benchmark.wet_iou(x, dry, dry, 0.005)["iou"])

    def test_first_crossing_time(self):
        t = [0.0, 0.1, 0.2, 0.3]
        s = [0.0, 0.2, 0.6, 1.0]
        self.assertAlmostEqual(benchmark.first_crossing_time(t, s, 0.4), 0.15, places=6)
        self.assertIsNone(benchmark.first_crossing_time(t, s, 5.0))


class SphBenchmarkExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = config.RESULTS_ROOT.parent / "benchmark" / "_test_sph"
        cls.res = benchmark.run_sph_benchmark(out, dx=FAST_DX)

    def test_sph_benchmark_runs_and_is_finite(self):
        self.assertTrue(self.res["ok"])
        s = self.res["summary"]
        self.assertTrue(s["finite"])
        self.assertGreater(s["particle_count"], 50)
        self.assertGreater(s["timesteps"], 5)
        self.assertGreater(s["velocity_max_mps"], 0.0)
        self.assertFalse(s["validated_hydraulic_output"])

    def test_sph_front_advances(self):
        front = self.res["front"]
        self.assertGreater(front[-1], front[0])                     # front moves downstream
        self.assertGreater(front[-1] - front[0], 0.15)              # by a meaningful distance
        # frame-0 front is the right edge of the particle column (~x0 - dx/2)
        self.assertGreater(front[0], benchmark.X0 - 0.03)
        self.assertLess(front[0], benchmark.X0 + 0.01)
        self.assertTrue(np.all(np.isfinite(front)))

    def test_sph_profile_present_and_finite(self):
        prof = np.array(self.res["profile"])
        self.assertEqual(prof.size, len(self.res["stations"]))
        self.assertTrue(np.all(np.isfinite(prof)))
        self.assertGreater(prof.max(), 0.0)


class CompareStructureTests(unittest.TestCase):
    def _fake_engine_result(self, front_scale):
        times = np.linspace(0, benchmark.T_END, 12)
        stations = np.linspace(0, benchmark.BOX[0], 240)
        front = benchmark.X0 + front_scale * times
        prof = benchmark.ritter_profile(stations, benchmark.PROFILE_T) * 0.9
        return {"ok": True, "summary": {"engine": "x", "validated_hydraulic_output": False},
                "times": times.tolist(), "front": front.tolist(),
                "stations": stations.tolist(), "profile": prof.tolist(),
                "profile_time_s": benchmark.PROFILE_T}

    def test_compare_produces_full_metric_block(self):
        out = config.RESULTS_ROOT.parent / "benchmark" / "_test_cmp"
        cmp = benchmark.compare(self._fake_engine_result(2.5), self._fake_engine_result(3.0), out)
        m = cmp["metrics"]
        for key in ("front_position", "depth_profile_at_t", "wet_region_at_t", "arrival_time_at_gauge"):
            self.assertIn(key, m)
        self.assertIn("sph_vs_ritter", m["front_position"])
        self.assertIn("delft3d_vs_ritter", m["front_position"])
        self.assertIsNotNone(m["front_position"]["sph_vs_delft3d"]["rmse_m"])
        self.assertIn("NOT PERFORMED", cmp["status"]["calibration"])
        self.assertIn("NOT PERFORMED", cmp["status"]["validation"])
        self.assertTrue(cmp["limitations"])
        self.assertTrue((out / "metrics.json").exists())
        self.assertTrue((out / "comparison.json").exists())


@unittest.skipUnless(HAS_DFLOWFM, "dflowfm-cli.exe not available")
class Delft3dBenchmarkExecutionTests(unittest.TestCase):
    def test_delft3d_benchmark_runs(self):
        out = config.RESULTS_ROOT.parent / "benchmark" / "_test_d3d"
        res = benchmark.run_delft3d_benchmark(out)
        self.assertTrue(res["ok"], res.get("reason"))
        s = res["summary"]
        self.assertGreater(s["depth_max_m"], 0.0)
        self.assertGreater(s["frames"], 1)
        self.assertTrue(s["finite"])
        self.assertTrue(np.all(np.isfinite(res["front"])))


class BenchmarkApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _wait(self, bid, timeout=180):
        for _ in range(timeout * 4):
            b = self.client.get(f"/api/benchmarks/{bid}").json()
            if b["status"] in ("completed", "failed"):
                return b
            time.sleep(0.25)
        raise AssertionError("benchmark did not finish")

    @unittest.skipUnless(HAS_DFLOWFM, "dflowfm-cli.exe not available")
    def test_benchmark_lifecycle_and_comparison(self):
        created = self.client.post("/api/benchmarks/run", json={"options": {"sph_dx": FAST_DX}})
        self.assertEqual(created.status_code, 200)
        bid = created.json()["id"]
        self.assertTrue(bid.startswith("bench-"))
        self.assertFalse(created.json()["validated_hydraulic_output"])

        final = self._wait(bid)
        self.assertEqual(final["status"], "completed", final)
        self.assertIsNotNone(final["metrics"])
        self.assertIn("Ritter", final["reference_source"])

        cmp = self.client.get(f"/api/benchmarks/{bid}/comparison")
        self.assertEqual(cmp.status_code, 200)
        body = cmp.json()
        self.assertIn("metrics", body)
        self.assertIn("front_position", body["metrics"])
        self.assertIn("NOT PERFORMED", body["status"]["validation"])

    def test_benchmark_failure_reported_not_swallowed(self):
        import app.simulation.benchmark_jobs as bj
        original = bj.benchmark.run_benchmark
        bj.benchmark.run_benchmark = lambda *a, **k: {"ok": False, "stage": "delft3d",
                                                      "reason": "forced benchmark failure for test"}
        try:
            created = self.client.post("/api/benchmarks/run", json={}).json()
            final = self._wait(created["id"])
        finally:
            bj.benchmark.run_benchmark = original
        self.assertEqual(final["status"], "failed")
        self.assertIn("forced benchmark failure", final["message"])
        self.assertEqual(self.client.get(f"/api/benchmarks/{created['id']}/comparison").status_code, 409)

    def test_unknown_benchmark_is_404(self):
        self.assertEqual(self.client.get("/api/benchmarks/bench-nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
