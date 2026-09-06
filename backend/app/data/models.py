from typing import Any
from pydantic import BaseModel, Field


class DemMetadata(BaseModel):
    path: str
    filename: str
    width: int | None = None
    height: int | None = None
    crs: str | None = None
    resolution: list[float] | None = None
    bounds: list[float] | None = None


class DataQuality(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    synthetic_data: bool = True


class StudyCaseSummary(BaseModel):
    case_id: str
    dam_name: str
    river_name: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    dem_available: bool
    breach_available: bool
    reservoir_available: bool


class StudyCase(StudyCaseSummary):
    dam_id: str | None = None
    dem: DemMetadata | None = None
    reservoir: dict[str, Any] | None = None
    breach: dict[str, Any] | None = None
    river: dict[str, Any] = Field(default_factory=dict)
    roughness: list[dict[str, Any]] = Field(default_factory=list)
    weather: list[dict[str, Any]] = Field(default_factory=list)
    exposure: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    data_quality: DataQuality = Field(default_factory=DataQuality)
