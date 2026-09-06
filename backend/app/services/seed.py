from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.database.session import get_engine
from app.models import Dam, Scenario, SimulationRun, ImpactSummary
from app.services.sample import DAM_ID, PARTIAL_ID, MAJOR_ID, SIMULATION_ID, SUMMARY_ID


def seed():
    timestamp = datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc)
    with Session(get_engine()) as session, session.begin():
        if not session.get(Dam, DAM_ID):
            session.add(Dam(id=DAM_ID, name="Hirakud Dam", river="Mahanadi", state="Odisha", latitude=21.53, longitude=83.87))
        session.flush()
        for identifier, name, kind, width, duration in [(PARTIAL_ID, "Hypothetical Partial Breach", "partial", 80, 45), (MAJOR_ID, "Hypothetical Major Breach", "major", 250, 30)]:
            if not session.get(Scenario, identifier):
                session.add(Scenario(id=identifier, dam_id=DAM_ID, name=name, breach_type=kind, breach_width_m=width, breach_time_minutes=duration, initial_water_level_m=192, status="prototype"))
        session.flush()
        if not session.get(SimulationRun, SIMULATION_ID):
            session.add(SimulationRun(id=SIMULATION_ID, scenario_id=MAJOR_ID, engine="prototype-sample", status="completed", progress=100, started_at=timestamp, completed_at=timestamp + timedelta(minutes=1), output_path="data/sample/timeline.json"))
        session.flush()
        if not session.get(ImpactSummary, SUMMARY_ID):
            session.add(ImpactSummary(id=SUMMARY_ID, simulation_run_id=SIMULATION_ID, flooded_area_km2=42.8, maximum_depth_m=8.4, population_exposed=18420, buildings_affected=3260, critical_assets=27))
    print("Prototype records seeded successfully. Existing records were preserved.")


if __name__ == "__main__":
    seed()
