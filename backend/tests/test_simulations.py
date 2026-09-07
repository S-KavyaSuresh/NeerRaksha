import time
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _wait(client, sim_id, timeout=30):
    for _ in range(timeout * 4):
        body = client.get(f"/api/simulations/{sim_id}").json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.25)
    raise AssertionError("simulation did not finish")


class SimulationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_lifecycle_completes_and_serves_flood_geometry(self):
        created = self.client.post(
            "/api/simulations",
            json={"scenario": {"preset": "major", "breach_type": "major"}, "engine": "approximate"},
        )
        self.assertEqual(created.status_code, 200)
        sim_id = created.json()["id"]
        self.assertTrue(sim_id.startswith("sim-"))

        final = _wait(self.client, sim_id)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["data_class"], "MODEL OUTPUT")
        self.assertTrue(final["available_frames"])

        summary = self.client.get(f"/api/simulations/{sim_id}/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertIsNone(summary.json()["population_exposed"])

        timeline = self.client.get(f"/api/simulations/{sim_id}/timeline").json()
        self.assertTrue(timeline["values"])

        first = timeline["available_frames"][0]
        last = timeline["available_frames"][-1]
        frame_first = self.client.get(f"/api/simulations/{sim_id}/timeline/{first}").json()
        frame_last = self.client.get(f"/api/simulations/{sim_id}/timeline/{last}").json()
        self.assertEqual(frame_first["type"], "FeatureCollection")
        self.assertGreater(len(frame_last["features"]), len(frame_first["features"]))

        self.assertEqual(self.client.get(f"/api/simulations/{sim_id}/results/flood_extent").status_code, 200)
        missing = self.client.get(f"/api/simulations/{sim_id}/results/max_depth")
        self.assertIn(missing.status_code, (200, 404))

    def test_unknown_simulation_is_404(self):
        self.assertEqual(self.client.get("/api/simulations/sim-does-not-exist").status_code, 404)

    def test_validation_is_honest_stub(self):
        created = self.client.post("/api/simulations", json={"scenario": {"preset": "partial"}}).json()
        body = self.client.get(f"/api/simulations/{created['id']}/validation").json()
        self.assertEqual(body["status"], "unavailable")
        self.assertIsNone(body["agreement"])


if __name__ == "__main__":
    unittest.main()
