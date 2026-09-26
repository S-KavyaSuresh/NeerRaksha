"""OBSERVATION branch — Sentinel-1 SAR water/flood evidence.

All offline: no live Google Earth Engine. Synthetic dB arrays are ALGORITHM
FIXTURES only and never reach a production path.
"""
import inspect
import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.main import app
from remote_sensing import observation, sentinel1
from remote_sensing.gee_client import GEEClient, gee_status

# These tests exercise the "not configured" branch explicitly, independent of
# whatever EARTHENGINE_PROJECT this machine's own local dev .env carries (see
# neerraksha_gee_persistent_config_fix_prompt: .env now persists that project id
# across restarts, so the ambient process environment is no longer guaranteed
# to be unconfigured the way it was before that fix).
_NO_PROJECT_ENV = {k: "" for k in ("EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT")}

RESULTS = observation.OBS_RESULTS / "_test"
RESULTS.mkdir(parents=True, exist_ok=True)
TRANSFORM = from_origin(75.05, 18.10, 0.001, 0.001)  # 5x5 grid ~ 75.05-75.055 / 18.095-18.10


def _pre_post():
    pre = np.full((5, 5), -8.0)          # dry-ish baseline VV(dB)
    post = np.full((5, 5), -8.0)
    post[1:3, 1:3] = -20.0               # a 2x2 block collapses -> new-water evidence
    return pre, post


class Sentinel1ConfigTests(unittest.TestCase):
    def test_collection_polarization_method_are_official(self):
        self.assertEqual(sentinel1.S1_COLLECTION, "COPERNICUS/S1_GRD")
        self.assertEqual(sentinel1.S1_INSTRUMENT_MODE, "IW")
        self.assertIn("VV", sentinel1.S1_POLARIZATIONS)
        self.assertIn("decibel", sentinel1.S1_UNITS.lower())
        self.assertEqual(sentinel1.METHOD_CHANGE, "sar_change_detection")
        self.assertEqual(sentinel1.METHOD_SINGLE, "sar_low_backscatter_single_scene")

    def test_run_observation_skeleton_reflects_request(self):
        r = observation.run_observation("2024-08-01", "2024-08-10",
                                        reference_start="2024-07-01", reference_end="2024-07-10",
                                        polarization="VV", out_dir=RESULTS / "skel")
        self.assertEqual(r["source"]["collection"], "COPERNICUS/S1_GRD")
        self.assertEqual(r["source"]["polarization"], "VV")
        self.assertEqual(r["method"], "sar_change_detection")   # reference window -> change detection
        self.assertIn("Copernicus", r["source"]["attribution"])
        s = observation.run_observation("2024-08-01", "2024-08-10", out_dir=RESULTS / "skel2")
        self.assertEqual(s["method"], "sar_low_backscatter_single_scene")  # no reference -> single scene


class AuthUnavailableTests(unittest.TestCase):
    """Exercises the "not configured" branch with EARTHENGINE_PROJECT explicitly
    cleared, regardless of what this machine's own .env persists it as."""

    def test_gee_status_unavailable_without_project(self):
        with patch.dict(os.environ, _NO_PROJECT_ENV):
            st = gee_status()
        self.assertFalse(st["available"])
        self.assertFalse(st["project_configured"])
        self.assertIn("earth engine", st["reason"].lower())

    def test_run_observation_unavailable_is_not_fabricated(self):
        with patch.dict(os.environ, _NO_PROJECT_ENV):
            r = observation.run_observation("2024-08-01", "2024-08-10", out_dir=RESULTS / "unavail")
        self.assertEqual(r["status"], "unavailable")
        self.assertIn("earth engine", r["reason"].lower())
        self.assertNotIn("water_evidence_area_km2", r)
        self.assertNotIn("outputs", r)
        self.assertFalse((RESULTS / "unavail" / "water_evidence.tif").exists())


class PersistentConfigTests(unittest.TestCase):
    """EARTHENGINE_PROJECT must come from .env (persistent), not only a value
    manually exported into one shell session (gone on the next process)."""

    def test_dotenv_value_is_visible_to_os_environ(self):
        # app.core.config is imported (directly or transitively) well before any
        # request is served; by then load_dotenv() must have already populated
        # os.environ from backend/.env for modules that read it directly.
        from app.core import config as _config

        self.assertTrue(_config._ENV_FILE.exists())
        env_text = _config._ENV_FILE.read_text(encoding="utf-8")
        if "EARTHENGINE_PROJECT=" in env_text and not any(
            line.strip().startswith("EARTHENGINE_PROJECT=") and line.strip() == "EARTHENGINE_PROJECT="
            for line in env_text.splitlines()
        ):
            self.assertTrue(os.environ.get("EARTHENGINE_PROJECT"),
                            ".env declares EARTHENGINE_PROJECT but it never reached os.environ")

    def test_gee_status_reflects_configured_project_without_touching_shell_env(self):
        with patch.dict(os.environ, {"EARTHENGINE_PROJECT": "neerraksha"}):
            st = gee_status()
        self.assertTrue(st["project_configured"])


class ThresholdAlgorithmTests(unittest.TestCase):
    def test_change_detection_selects_only_the_dropped_block(self):
        pre, post = _pre_post()
        mask = sentinel1.water_mask_change(pre, post, threshold_db=-3.0)
        self.assertEqual(int(mask.sum()), 4)
        self.assertTrue(mask[1:3, 1:3].all())
        self.assertFalse(mask[0, 0])

    def test_change_threshold_is_configurable(self):
        pre, post = _pre_post()
        post[4, 4] = -12.0  # a -4 dB drop
        loose = sentinel1.water_mask_change(pre, post, threshold_db=-3.0)
        strict = sentinel1.water_mask_change(pre, post, threshold_db=-10.0)
        self.assertTrue(loose[4, 4])          # -4 <= -3
        self.assertFalse(strict[4, 4])        # -4 !<= -10
        self.assertTrue(strict[1, 1])         # -12 <= -10

    def test_single_scene_low_backscatter(self):
        _, post = _pre_post()
        mask = sentinel1.water_mask_single(post, threshold_db=-17.0)
        self.assertEqual(int(mask.sum()), 4)
        self.assertTrue(mask[1:3, 1:3].all())


class NoDataTests(unittest.TestCase):
    def test_nan_and_sentinel_nodata_never_become_water(self):
        pre, post = _pre_post()
        post[1, 1] = np.nan
        post[2, 2] = -9999.0
        m_change = sentinel1.water_mask_change(pre, post, threshold_db=-3.0, nodata=-9999.0)
        m_single = sentinel1.water_mask_single(post, threshold_db=-17.0, nodata=-9999.0)
        self.assertFalse(m_change[1, 1])
        self.assertFalse(m_change[2, 2])
        self.assertFalse(m_single[1, 1])
        self.assertFalse(m_single[2, 2])
        self.assertTrue(m_change[1, 2] and m_change[2, 1])  # the still-valid water cells remain


class GeometryConversionTests(unittest.TestCase):
    def test_mask_to_valid_geojson_polygons(self):
        from shapely.geometry import shape

        pre, post = _pre_post()
        feats = sentinel1.mask_to_features(sentinel1.water_mask_change(pre, post), TRANSFORM)
        self.assertTrue(feats)
        for f in feats:
            self.assertEqual(f["geometry"]["type"], "Polygon")
            self.assertTrue(shape(f["geometry"]).is_valid)
            self.assertEqual(f["properties"]["class"], "water_flood_evidence")

    def test_empty_mask_yields_no_features_and_zero_area(self):
        empty = np.zeros((5, 5), dtype=bool)
        self.assertEqual(sentinel1.mask_to_features(empty, TRANSFORM), [])
        stats = sentinel1.observation_statistics(empty, TRANSFORM)
        self.assertEqual(stats["water_evidence_cells"], 0)
        self.assertEqual(stats["water_evidence_area_km2"], 0.0)


class MetadataTests(unittest.TestCase):
    def test_process_arrays_writes_outputs_and_provenance(self):
        import rasterio

        pre, post = _pre_post()
        out = RESULTS / "meta"
        r = observation.process_arrays(post, TRANSFORM, "EPSG:4326", out, pre_db=pre,
                                       threshold_db=-3.0,
                                       meta=observation.run_observation("2024-08-01", "2024-08-10",
                                                                        reference_start="2024-07-01",
                                                                        reference_end="2024-07-10",
                                                                        out_dir=out))
        for k in ("crs", "method", "threshold_db", "water_evidence_area_km2", "water_evidence_cells"):
            self.assertIn(k, r)
        self.assertEqual(r["source"]["collection"], "COPERNICUS/S1_GRD")
        self.assertEqual(r["method"], "sar_change_detection")
        disk = json.loads((out / "observation.json").read_text())
        self.assertEqual(disk["outputs"]["raster"], "water_evidence.tif")
        self.assertEqual(disk["outputs"]["footprint"], "water_evidence.geojson")
        with rasterio.open(out / "water_evidence.tif") as ds:
            self.assertEqual(str(ds.crs), "EPSG:4326")
            self.assertEqual(int(ds.read(1).sum()), 4)


class ModelSatelliteDistinctionTests(unittest.TestCase):
    def test_result_is_observation_not_validated_hydraulic_output(self):
        pre, post = _pre_post()
        r = observation.process_arrays(post, TRANSFORM, "EPSG:4326", RESULTS / "class",
                                       pre_db=pre, meta=observation.run_observation(
                                           "2024-08-01", "2024-08-10", out_dir=RESULTS / "class"))
        self.assertEqual(r["classification"], "SATELLITE OBSERVATION — WATER/FLOOD EVIDENCE")
        self.assertTrue(r["not_validated"])
        self.assertFalse(r["validated_hydraulic_output"])
        self.assertFalse(r["is_model_output"])
        self.assertNotIn("VALIDATED HYDRAULIC", r["classification"].upper())

    def test_spatial_agreement_is_an_indicator_not_a_score(self):
        model = RESULTS / "model_extent.geojson"
        model.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[
                [75.050, 18.095], [75.054, 18.095], [75.054, 18.099], [75.050, 18.099], [75.050, 18.095]]]}}]}),
            encoding="utf-8")
        pre, post = _pre_post()
        feats = sentinel1.mask_to_features(sentinel1.water_mask_change(pre, post), TRANSFORM)
        agr = sentinel1.spatial_agreement(str(model), feats)
        self.assertEqual(agr["indicator"], "spatial_agreement_indicator")
        self.assertGreaterEqual(agr["iou"], 0.0)
        self.assertLessEqual(agr["iou"], 1.0)
        self.assertIn("not", agr["disclaimer"].lower())
        self.assertIn("validation", agr["disclaimer"].lower())  # explicitly says NOT validation
        self.assertNotIn("validation_accuracy", agr)


class SyntheticIsolationTests(unittest.TestCase):
    def test_no_prototype_or_sample_dependency(self):
        for mod in (observation, sentinel1):
            src = inspect.getsource(mod)
            for bad in ("prototype.js", "prototypeImpact", "sample.js", "comparison.js",
                        "18420", "SYNTHETIC SIMULATION DATA", "is_sample"):
                self.assertNotIn(bad, src)

    def test_process_arrays_is_a_pure_function_of_its_arrays(self):
        pre, post = _pre_post()
        a = observation.process_arrays(post, TRANSFORM, "EPSG:4326", RESULTS / "pureA", pre_db=pre)
        b = observation.process_arrays(post, TRANSFORM, "EPSG:4326", RESULTS / "pureB", pre_db=pre)
        self.assertEqual(a["water_evidence_cells"], b["water_evidence_cells"])
        self.assertEqual(a["water_evidence_area_km2"], b["water_evidence_area_km2"])


def _tiny_geotiff_bytes():
    import io as _io

    import rasterio
    a = np.array([[-8.0, -20.0], [-20.0, -8.0]], dtype="float32")
    buf = _io.BytesIO()
    with rasterio.open(buf, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(75.05, 18.10, 0.001, 0.001)) as ds:
        ds.write(a, 1)
    return buf.getvalue()


class _FakeResp:
    def __init__(self, payload=None, exc=None):
        self._payload, self._exc = payload, exc

    def raise_for_status(self):
        if self._exc:
            raise self._exc

    def iter_content(self, chunk_size=65536):
        if self._exc:
            raise self._exc
        yield self._payload


class _FakeSession:
    """Raises `exc` on the first `fail_times` GETs, then serves `payload`."""
    def __init__(self, payload, exc, fail_times):
        self.payload, self.exc, self.fail_times, self.calls = payload, exc, fail_times, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, timeout=None, stream=False):
        self.calls += 1
        if self.calls <= self.fail_times:
            return _FakeResp(exc=self.exc)
        return _FakeResp(payload=self.payload)


class _FakeImg:
    def select(self, _bands):
        return self

    def getDownloadURL(self, _params):
        return "https://fake.invalid/download"


class PixelRetrievalRobustnessTests(unittest.TestCase):
    """download_band must ride out a transient SSL EOF / connection reset and
    only surface a real error once retries are exhausted — never fabricate."""

    def _client(self):
        import types
        c = GEEClient(project="test")
        c._ee = types.SimpleNamespace(Geometry=types.SimpleNamespace(
            Rectangle=lambda *a, **k: None))
        return c

    def test_recovers_after_transient_ssl_eof(self):
        import requests
        c = self._client()
        total = {"sessions": 0}
        payload = _tiny_geotiff_bytes()
        eof = requests.exceptions.SSLError("[SSL: UNEXPECTED_EOF_WHILE_READING]")

        def fake_session():
            total["sessions"] += 1
            # each session fails once then would serve; download_band makes a
            # fresh session per attempt, so 2 failing attempts + 1 success
            return _FakeSession(payload, eof, fail_times=1 if total["sessions"] <= 2 else 0)

        c._download_session = fake_session
        c._DOWNLOAD_BACKOFF_S = 0.0
        arr, transform, crs = c.download_band(_FakeImg(), (74.98, 17.98, 75.20, 18.14), "VV", 30)
        self.assertEqual(arr.shape, (2, 2))
        self.assertEqual(crs, "EPSG:4326")
        self.assertGreaterEqual(total["sessions"], 3)

    def test_raises_connection_error_after_exhausting_retries(self):
        import requests
        c = self._client()
        c._DOWNLOAD_BACKOFF_S = 0.0
        eof = requests.exceptions.SSLError("[SSL: UNEXPECTED_EOF_WHILE_READING]")
        c._download_session = lambda: _FakeSession(b"", eof, fail_times=99)
        with self.assertRaises(ConnectionError) as ctx:
            c.download_band(_FakeImg(), (74.98, 17.98, 75.20, 18.14), "VV", 30)
        self.assertIn("attempts", str(ctx.exception))
        self.assertIn("UNEXPECTED_EOF", str(ctx.exception))

    def test_run_observation_maps_transport_failure_to_error_not_unavailable(self):
        import remote_sensing.observation as obs_mod

        class _Boom:
            def initialize(self):
                return self

            def s1_median(self, *a, **k):
                import numpy as _np
                from rasterio.transform import from_origin as _fo
                return object(), {"scene_count": 2, "acquisitions": ["2024-08-23T00:55:00Z"],
                                  "first": "2024-08-23T00:55:00Z", "last": "2024-09-04T00:55:00Z",
                                  "orbit_pass": "ANY"}

            def download_band(self, *a, **k):
                raise ConnectionError("Sentinel-1 pixel retrieval failed after 4 attempts")

        orig_client, orig_status = obs_mod.GEEClient, obs_mod.gee_status
        obs_mod.GEEClient = lambda *a, **k: _Boom()
        obs_mod.gee_status = lambda: {"available": True, "reason": "configured"}
        try:
            r = obs_mod.run_observation("2024-08-20", "2024-09-05", out_dir=RESULTS / "boom")
        finally:
            obs_mod.GEEClient, obs_mod.gee_status = orig_client, orig_status
        self.assertEqual(r["status"], "error")
        self.assertIn("retrieval failed", r["reason"])
        self.assertNotIn("water_evidence_area_km2", r)
        self.assertEqual(r["classification"], "SATELLITE OBSERVATION — WATER/FLOOD EVIDENCE")


class ObservationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_status_endpoint_reports_unavailable(self):
        with patch.dict(os.environ, _NO_PROJECT_ENV):
            b = self.client.get("/api/remote-sensing/status").json()
        self.assertFalse(b["gee_available"])
        self.assertIn("earth engine", b["reason"].lower())
        self.assertEqual(len(b["default_aoi_bbox_wgs84"]), 4)

    def test_observe_job_returns_truthful_unavailable(self):
        with patch.dict(os.environ, _NO_PROJECT_ENV):
            created = self.client.post("/api/remote-sensing/sentinel1/observe",
                                       json={"observation_start": "2024-08-01",
                                             "observation_end": "2024-08-12"}).json()
            jid = created["id"]
            for _ in range(40):
                b = self.client.get(f"/api/remote-sensing/jobs/{jid}").json()
                if b["status"] in ("completed", "unavailable", "error"):
                    break
                time.sleep(0.25)
        self.assertEqual(b["status"], "unavailable")
        self.assertTrue(b["not_validated"])
        self.assertIsNone(b["water_evidence_area_km2"])

        res = self.client.get(f"/api/remote-sensing/jobs/{jid}/result").json()
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("reason", res)
        self.assertEqual(res["classification"], "SATELLITE OBSERVATION — WATER/FLOOD EVIDENCE")

        self.assertEqual(self.client.get(f"/api/remote-sensing/jobs/{jid}/layers/water_evidence").status_code, 404)

    def test_unknown_job_is_404(self):
        self.assertEqual(self.client.get("/api/remote-sensing/jobs/obs-nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
