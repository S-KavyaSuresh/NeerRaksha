from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class RecordOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DamOut(RecordOut):
    name: str
    river: str
    state: str
    latitude: float
    longitude: float


class ScenarioOut(RecordOut):
    dam_id: UUID
    name: str
    breach_type: str
    breach_width_m: float
    breach_time_minutes: float
    initial_water_level_m: float
    status: str


class SimulationOut(RecordOut):
    scenario_id: UUID
    engine: str
    status: str
    progress: int
    started_at: datetime | None
    completed_at: datetime | None
    output_path: str | None


class ImpactOut(RecordOut):
    simulation_run_id: UUID
    flooded_area_km2: float
    maximum_depth_m: float
    population_exposed: int
    buildings_affected: int
    critical_assets: int
    is_sample: bool = True


class TimelinePoint(BaseModel):
    minute: int
    depth_m: float
    flooded_area_km2: float


class TimelineOut(BaseModel):
    simulation_run_id: UUID
    is_sample: bool = True
    values: list[TimelinePoint]
