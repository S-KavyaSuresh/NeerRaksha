from __future__ import annotations

from functools import cached_property
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

from .models import DataQuality, DemMetadata, StudyCase, StudyCaseSummary
from .normalizer import normalized_id, normalized_name
from .paths import CSV_FILES, discover_dem_files


class StudyCaseRepository:
    """Read-only, cached access to the synthetic study-case datasets."""

    def __init__(self) -> None:
        self._warnings: list[str] = []

    @cached_property
    def pandas(self):
        try:
            import pandas as pd
            return pd
        except ImportError:
            self._warnings.append("pandas is not installed; CSV study cases are unavailable.")
            return None

    @cached_property
    def tables(self) -> dict[str, Any]:
        if self.pandas is None:
            return {}
        tables: dict[str, Any] = {}
        for name, path in CSV_FILES.items():
            if not path.exists():
                self._warnings.append(f"Optional dataset missing: {name}.")
                continue
            try:
                tables[name] = self.pandas.read_csv(path)
            except Exception as exc:
                self._warnings.append(f"Could not read {name}: {exc}")
        return tables

    @cached_property
    def dem_by_name(self) -> dict[str, DemMetadata]:
        metadata: dict[str, DemMetadata] = {}
        try:
            import rasterio
        except ImportError:
            self._warnings.append("rasterio is not installed; DEM metadata is unavailable.")
            return metadata
        for path in discover_dem_files():
            try:
                with rasterio.open(path) as dataset:
                    if dataset.width <= 0 or dataset.height <= 0 or not dataset.crs:
                        self._warnings.append(f"Invalid DEM metadata: {path.name}")
                        continue
                    metadata[normalized_name(path.stem)] = DemMetadata(
                        path=str(path), filename=path.name, width=dataset.width, height=dataset.height,
                        crs=str(dataset.crs), resolution=[float(dataset.res[0]), float(dataset.res[1])],
                        bounds=[float(dataset.bounds.left), float(dataset.bounds.bottom), float(dataset.bounds.right), float(dataset.bounds.top)],
                    )
            except Exception as exc:
                self._warnings.append(f"Could not open DEM {path.name}: {exc}")
        return metadata

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in row.to_dict().items():
            result[key] = None if value is None or (isinstance(value, float) and value != value) else value
        return result

    def _match_rows(self, table_name: str, dam: dict[str, Any]) -> list[dict[str, Any]]:
        table = self.tables.get(table_name)
        if table is None:
            return []
        dam_id = normalized_id(dam.get("dam_id"))
        dam_name = normalized_name(dam.get("dam_name"))
        river_name = normalized_name(dam.get("river_name"))
        matches = []
        for _, row in table.iterrows():
            item = self._record(row)
            if (
                normalized_id(item.get("dam_id")) == dam_id
                or normalized_id(item.get("upstream_dam_id")) == dam_id
                or normalized_name(item.get("dam_name")) == dam_name
                or (table_name.startswith("river_") and normalized_name(item.get("river_name")) == river_name)
            ):
                matches.append(item)
        return matches

    @staticmethod
    def _distance_km(latitude: float, longitude: float, item: dict[str, Any]) -> float:
        """Distance is used only where the source exposure CSV has no case key."""
        try:
            item_latitude = float(item["latitude"])
            item_longitude = float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            return float("inf")
        lat1, lon1, lat2, lon2 = map(radians, (latitude, longitude, item_latitude, item_longitude))
        a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return 6371 * 2 * asin(sqrt(a))

    def _nearby_rows(self, table_name: str, dam: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
        """Return source records in the same state, nearest to the actual dam point.

        Exposure CSVs do not include dam/case IDs, so this is the deterministic
        association available from their documented location fields.
        """
        table = self.tables.get(table_name)
        if table is None:
            return []
        try:
            latitude, longitude = float(dam["latitude"]), float(dam["longitude"])
        except (KeyError, TypeError, ValueError):
            return []
        state = normalized_name(dam.get("state"))
        rows = [self._record(row) for _, row in table.iterrows()]
        same_state = [row for row in rows if normalized_name(row.get("state")) == state]
        nearby = sorted(same_state, key=lambda row: (self._distance_km(latitude, longitude, row), str(row.get("asset_id") or row.get("population_id") or "")))
        return nearby[:limit]

    @staticmethod
    def _exposure_record(item: dict[str, Any], category: str) -> dict[str, Any]:
        """Present JSON-safe map fields while retaining actual source attributes."""
        return {
            "id": item.get("asset_id") or item.get("population_id"),
            "asset_type": item.get("asset_type") or category.rstrip("s"),
            "name": item.get("asset_name") or item.get("village_or_city"),
            "latitude": item.get("latitude"), "longitude": item.get("longitude"),
            "geometry": item.get("asset_geometry_wkt") or item.get("settlement_geometry_wkt"),
            "state": item.get("state"), "district": item.get("district"),
            "location": item.get("city_or_village") or item.get("village_or_city"),
            "criticality": item.get("criticality_level"),
            "population_exposed": item.get("population_exposed") or item.get("estimated_exposed_population"),
            "population_total": item.get("population_total"),
            "category": category,
        }

    def _exposure(self, dam: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        assets = self._nearby_rows("assets", dam)
        exposure = {"buildings": [], "roads": [], "facilities": [], "settlements": []}
        for item in assets:
            kind = normalized_name(item.get("asset_type"))
            if kind == "building":
                exposure["buildings"].append(self._exposure_record(item, "buildings"))
            elif kind == "road":
                exposure["roads"].append(self._exposure_record(item, "roads"))
            else:
                exposure["facilities"].append(self._exposure_record(item, "facilities"))
        exposure["settlements"] = [self._exposure_record(item, "settlements") for item in self._nearby_rows("population", dam)]
        return exposure

    @cached_property
    def cases(self) -> dict[str, StudyCase]:
        dams = self.tables.get("dams")
        if dams is None:
            return {}
        cases: dict[str, StudyCase] = {}
        for _, row in dams.iterrows():
            dam = self._record(row)
            key = normalized_name(dam.get("dam_name"))
            dem = self.dem_by_name.get(key)
            if dem is None:
                continue
            case_id = key.replace(" ", "-")
            reservoir = self._match_rows("reservoir", dam)
            breach = self._match_rows("breach", dam)
            river_geometry = self._match_rows("river_geometry", dam)
            discharge = self._match_rows("river_discharge", dam)
            case = StudyCase(
                case_id=case_id, dam_id=str(dam.get("dam_id") or "") or None,
                dam_name=str(dam.get("dam_name") or dem.filename.removesuffix(".tif").replace("_", " ").title()),
                river_name=dam.get("river_name"), state=dam.get("state"), latitude=dam.get("latitude"), longitude=dam.get("longitude"),
                dem_available=True, breach_available=bool(breach), reservoir_available=bool(reservoir), dem=dem,
                reservoir=reservoir[0] if reservoir else None, breach=breach[0] if breach else None,
                river={"cross_sections": river_geometry, "discharge_records": discharge},
                roughness=self._match_rows("roughness", dam), weather=self._match_rows("weather", dam),
                exposure=self._exposure(dam),
                data_quality=DataQuality(missing_fields=[name for name, value in {"reservoir": reservoir, "breach": breach}.items() if not value], warnings=list(self._warnings)),
            )
            cases[case_id] = case
        return cases

    def list_study_cases(self) -> list[StudyCaseSummary]:
        return [StudyCaseSummary(**case.model_dump(exclude={"dam_id", "dem", "reservoir", "breach", "river", "roughness", "weather", "exposure", "data_quality"})) for case in self.cases.values()]

    def get_study_case(self, case_id: str) -> StudyCase | None:
        return self.cases.get(case_id)

    def validation(self, case_id: str) -> dict[str, Any] | None:
        case = self.get_study_case(case_id)
        if case is None:
            return None
        return {"status": "warning" if case.data_quality.missing_fields or case.data_quality.warnings else "ok", "critical_errors": [], "warnings": case.data_quality.warnings, "available_datasets": {"dem": bool(case.dem), "reservoir": bool(case.reservoir), "breach": bool(case.breach), "river": bool(case.river.get("cross_sections") or case.river.get("discharge_records"))}, "synthetic_data": True}


repository = StudyCaseRepository()
