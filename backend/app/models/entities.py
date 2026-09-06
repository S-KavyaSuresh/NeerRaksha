import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Float, Integer, Uuid, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class Record:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Dam(Record, Base):
    __tablename__ = "dams"
    name: Mapped[str] = mapped_column(String(160))
    river: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Scenario(Record, Base):
    __tablename__ = "scenarios"
    dam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dams.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    breach_type: Mapped[str] = mapped_column(String(60))
    breach_width_m: Mapped[float] = mapped_column(Float)
    breach_time_minutes: Mapped[float] = mapped_column(Float)
    initial_water_level_m: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="draft")


class SimulationRun(Record, Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (CheckConstraint("progress >= 0 AND progress <= 100", name="valid_progress"),)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id"), index=True)
    engine: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_path: Mapped[str | None] = mapped_column(String(512))


class ImpactSummary(Record, Base):
    __tablename__ = "impact_summaries"
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id"), unique=True, index=True)
    flooded_area_km2: Mapped[float] = mapped_column(Float)
    maximum_depth_m: Mapped[float] = mapped_column(Float)
    population_exposed: Mapped[int] = mapped_column(Integer)
    buildings_affected: Mapped[int] = mapped_column(Integer)
    critical_assets: Mapped[int] = mapped_column(Integer)
