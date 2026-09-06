import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.database.session import Base, get_engine, get_session
from app.services.seed import seed
from app.services.sample import DAM_ID, MAJOR_ID, PARTIAL_ID, SIMULATION_ID


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        get_engine.cache_clear()

    def test_missing_database_keeps_api_alive(self):
        with patch.object(settings, "database_url", ""):
            get_engine.cache_clear()
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            for route in ["/api/database/health", "/api/dams", "/api/scenarios", f"/api/simulations/{SIMULATION_ID}/timeline"]:
                response = self.client.get(route)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error"]["code"], "DATABASE_NOT_CONFIGURED")

    def test_unreachable_database_is_sanitized(self):
        with patch.object(settings, "database_url", "postgresql://demo:never-echo-this@127.0.0.1:1/missing"):
            get_engine.cache_clear()
            response = self.client.get("/api/database/health")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "DATABASE_UNAVAILABLE")
            self.assertNotIn("never-echo-this", response.text)
            self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_seed_and_all_read_routes(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        with patch("app.services.seed.get_engine", return_value=engine):
            seed()
            seed()
        def test_session():
            with Session(engine) as session:
                yield session
        app.dependency_overrides[get_session] = test_session
        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            for route in ["/api/health", "/api/database/health", "/api/scenarios", f"/api/scenarios/{MAJOR_ID}", f"/api/simulations/{SIMULATION_ID}/summary", f"/api/simulations/{SIMULATION_ID}/timeline"]:
                with self.subTest(origin=origin, route=route):
                    response = self.client.get(route, headers={"Origin": origin})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
                    self.assertNotIn("access-control-allow-credentials", response.headers)
                    preflight = self.client.options(route, headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "content-type"})
                    self.assertEqual(preflight.status_code, 200)
                    self.assertEqual(preflight.headers.get("access-control-allow-origin"), origin)
        for route in ["/api/database/health", "/api/dams", f"/api/dams/{DAM_ID}", "/api/scenarios", f"/api/scenarios/{MAJOR_ID}", f"/api/scenarios/{PARTIAL_ID}", f"/api/simulations/{SIMULATION_ID}", f"/api/simulations/{SIMULATION_ID}/summary", f"/api/simulations/{SIMULATION_ID}/timeline"]:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.client.get("/api/scenarios").json()), 2)
        summary = self.client.get(f"/api/simulations/{SIMULATION_ID}/summary").json()
        self.assertEqual(summary["population_exposed"], 18420)
        self.assertTrue(summary["is_sample"])
        self.assertEqual([point["minute"] for point in self.client.get(f"/api/simulations/{SIMULATION_ID}/timeline").json()["values"]], [0, 15, 30, 60])
        self.assertEqual(self.client.get("/api/dams/99999999-9999-4999-8999-999999999999").status_code, 404)
        self.assertEqual(self.client.get("/api/dams/invalid").status_code, 422)
        response = self.client.get("/api/health", headers={"Origin": settings.frontend_origin})
        self.assertEqual(response.headers["access-control-allow-origin"], settings.frontend_origin)
        engine.dispose()

    def test_cors_on_database_errors_and_rejects_unknown_origins(self):
        with patch.object(settings, "database_url", ""):
            get_engine.cache_clear()
            for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
                for route in ["/api/database/health", "/api/scenarios", f"/api/simulations/{SIMULATION_ID}/summary", f"/api/simulations/{SIMULATION_ID}/timeline"]:
                    response = self.client.get(route, headers={"Origin": origin})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
            response = self.client.get("/api/health", headers={"Origin": "https://untrusted.example"})
            self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
