"""Google Earth Engine provider for the Sentinel-1 observation workflow.

Auth model (official: developers.google.com/earth-engine/guides/auth):
    * Python client needs a Cloud project: ee.Initialize(project=...).
    * Interactive: `earthengine authenticate` stores a user credential; then
      ee.Initialize(project=<EARTHENGINE_PROJECT>).
    * Headless / server: a service account key ->
      ee.ServiceAccountCredentials(email, key_file); ee.Initialize(creds, project).

Credentials come ONLY from environment / configuration and are never logged,
returned in an API response, or written to the repository:
    EARTHENGINE_PROJECT             Cloud project id
    GOOGLE_APPLICATION_CREDENTIALS  path to a service-account JSON key (optional)
    EARTHENGINE_SERVICE_ACCOUNT     service-account email (needed with the key)

If anything required is missing the client reports it as unavailable — it never
falls back to synthetic satellite data.
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone


class GEEUnavailable(RuntimeError):
    """Earth Engine cannot be used (package missing, not authenticated, empty query)."""


def _env(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None


def gee_status() -> dict:
    """Non-sensitive summary of whether a live GEE observation is possible.

    Never includes key contents or paths beyond a boolean 'configured'.
    """
    project = _env("EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT")
    sa_key = _env("GOOGLE_APPLICATION_CREDENTIALS")
    sa_email = _env("EARTHENGINE_SERVICE_ACCOUNT")
    try:
        import ee  # noqa: F401
        ee_version = getattr(ee, "__version__", "unknown")
        ee_installed = True
    except Exception:  # noqa: BLE001
        ee_version = None
        ee_installed = False

    if not ee_installed:
        return {"available": False, "ee_installed": False, "ee_version": None,
                "project_configured": bool(project),
                "reason": "Google Earth Engine client (earthengine-api) is not installed"}
    if not project:
        return {"available": False, "ee_installed": True, "ee_version": ee_version,
                "project_configured": False,
                "reason": "Google Earth Engine authentication is not configured "
                          "(set EARTHENGINE_PROJECT and authenticate)"}
    return {"available": True, "ee_installed": True, "ee_version": ee_version,
            "project_configured": True,
            "service_account": bool(sa_key and sa_email),
            "reason": "configured"}


class GEEClient:
    def __init__(self, project: str | None = None,
                 service_account_key: str | None = None,
                 service_account_email: str | None = None):
        self.project = project or _env("EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT")
        self.sa_key = service_account_key or _env("GOOGLE_APPLICATION_CREDENTIALS")
        self.sa_email = service_account_email or _env("EARTHENGINE_SERVICE_ACCOUNT")
        self._ee = None

    # -- lifecycle ---------------------------------------------------------- #
    def initialize(self):
        try:
            import ee
        except Exception as exc:  # noqa: BLE001
            raise GEEUnavailable("earthengine-api is not installed") from exc
        if not self.project:
            raise GEEUnavailable("Google Earth Engine authentication is not configured "
                                 "(EARTHENGINE_PROJECT unset)")
        try:
            if self.sa_key and self.sa_email:
                creds = ee.ServiceAccountCredentials(self.sa_email, self.sa_key)
                ee.Initialize(creds, project=self.project,
                              opt_url="https://earthengine-highvolume.googleapis.com")
            else:
                ee.Initialize(project=self.project,
                              opt_url="https://earthengine-highvolume.googleapis.com")
        except Exception as exc:  # noqa: BLE001
            raise GEEUnavailable(f"Earth Engine initialisation failed: {exc}") from exc
        self._ee = ee
        return self

    @property
    def ee(self):
        if self._ee is None:
            raise GEEUnavailable("GEEClient.initialize() has not been called")
        return self._ee

    # -- Sentinel-1 ------------------------------------------------------------ #
    def s1_median(self, aoi_bbox, date_range, polarization="VV",
                  orbit_pass: str | None = None, speckle_radius_m: int = 30):
        """Speckle-filtered median VV(dB) composite for the AOI + date window.

        Returns (ee.Image, acquisition_info dict). Raises GEEUnavailable if the
        filtered collection is empty.
        """
        ee = self.ee
        w, s, e, n = [float(v) for v in aoi_bbox]
        region = ee.Geometry.Rectangle([w, s, e, n], proj="EPSG:4326", geodesic=False)
        start, end = date_range

        col = (ee.ImageCollection("COPERNICUS/S1_GRD")
               .filterBounds(region)
               .filterDate(str(start), str(end))
               .filter(ee.Filter.eq("instrumentMode", "IW"))
               .filter(ee.Filter.listContains("transmitterReceiverPolarisation", polarization))
               .select([polarization]))
        if orbit_pass:
            col = col.filter(ee.Filter.eq("orbitProperties_pass", orbit_pass.upper()))

        size = col.size().getInfo()
        if not size:
            raise GEEUnavailable(
                f"no COPERNICUS/S1_GRD {polarization} IW scenes for AOI in {start}..{end}"
                + (f" ({orbit_pass} pass)" if orbit_pass else ""))

        dates = (col.aggregate_array("system:time_start")
                 .map(lambda t: ee.Date(t).format("YYYY-MM-dd'T'HH:mm:ss'Z'")).getInfo())
        speckle = ee.Number(speckle_radius_m).divide(10).round().max(1)
        composite = col.map(lambda img: img.focal_median(speckle, "circle", "pixels")).median()
        return composite.clip(region), {
            "scene_count": int(size),
            "acquisitions": sorted(dates),
            "first": min(dates), "last": max(dates),
            "orbit_pass": orbit_pass.upper() if orbit_pass else "ANY",
        }

    # Download robustness: Earth Engine's pixel endpoint can drop a large HTTPS
    # transfer mid-stream (SSL UNEXPECTED_EOF / connection reset), and GEE's own
    # guidance is to retry transient failures. This only hardens the transport —
    # the AOI, dates, band, scale, collection and detection method are unchanged.
    _DOWNLOAD_ATTEMPTS = 4
    _DOWNLOAD_BACKOFF_S = 2.0

    def _download_session(self):
        import requests
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
        except Exception:  # noqa: BLE001
            from requests.packages.urllib3.util.retry import Retry  # type: ignore

        retry = Retry(total=4, connect=4, read=4, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET"]), raise_on_status=False)
        sess = requests.Session()          # fresh pool per call -> no stale keep-alive socket
        sess.mount("https://", HTTPAdapter(max_retries=retry))
        return sess

    def download_band(self, image, aoi_bbox, band: str, scale_m: int = 30):
        """getDownloadURL -> GeoTIFF bytes -> (numpy array, rasterio transform, crs).

        Suitable only for small AOIs (Earth Engine caps getDownloadURL size).
        Retries transient transport failures (SSL EOF / connection reset / 5xx);
        a genuine failure still propagates so the job reports status "error".
        """
        import time as _time

        import numpy as np
        import rasterio
        import requests

        ee = self.ee
        w, s, e, n = [float(v) for v in aoi_bbox]
        region = ee.Geometry.Rectangle([w, s, e, n], proj="EPSG:4326", geodesic=False)
        img1 = image.select([band])
        params = {"region": region, "scale": int(scale_m), "crs": "EPSG:4326",
                  "format": "GEO_TIFF", "filePerBand": False}

        last_exc = None
        for attempt in range(1, self._DOWNLOAD_ATTEMPTS + 1):
            try:
                url = img1.getDownloadURL(params)  # re-minted each attempt (URLs expire)
                with self._download_session() as sess:
                    resp = sess.get(url, timeout=180, stream=True)
                    resp.raise_for_status()
                    payload = b"".join(resp.iter_content(chunk_size=1 << 16))
                if len(payload) < 128:
                    raise OSError(f"Earth Engine returned {len(payload)} bytes (truncated)")
                if payload[:2] == b"PK":
                    with zipfile.ZipFile(io.BytesIO(payload)) as z:
                        name = next(nm for nm in z.namelist()
                                    if nm.lower().endswith((".tif", ".tiff")))
                        payload = z.read(name)
                with rasterio.open(io.BytesIO(payload)) as ds:
                    arr = ds.read(1).astype("float64")
                    nodata = ds.nodata
                    if nodata is not None:
                        arr[arr == nodata] = np.nan
                    return arr, ds.transform, str(ds.crs or "EPSG:4326")
            except (requests.exceptions.RequestException, OSError, zipfile.BadZipFile) as exc:
                last_exc = exc
                if attempt < self._DOWNLOAD_ATTEMPTS:
                    _time.sleep(self._DOWNLOAD_BACKOFF_S * attempt)
        # transient retries exhausted -> a real failure; run_observation maps this
        # to status "error" (NOT "unavailable", NOT a synthetic fallback).
        raise ConnectionError(
            f"Sentinel-1 pixel retrieval failed after {self._DOWNLOAD_ATTEMPTS} attempts "
            f"(Earth Engine transport error): {last_exc}") from last_exc

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
