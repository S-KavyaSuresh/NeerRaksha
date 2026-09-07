from uuid import UUID
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database.session import get_session
from app.models import Dam, Scenario, SimulationRun, ImpactSummary
from app.schemas.responses import DamOut, ScenarioOut, SimulationOut, ImpactOut, TimelineOut
from app.services.sample import SIMULATION_ID, TIMELINE
from app.data.repository import repository

router = APIRouter(prefix="/api")
UJJANI_RESULTS = Path(__file__).resolve().parents[3] / "results" / "ujjani"


def require_record(session, model, identifier):
    record = session.get(model, identifier)
    if record is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "The requested record does not exist."})
    return record


@router.get("/health")
def health():
    return {"status": "ok", "service": "NeerRaksha"}


@router.get("/study-cases")
def study_cases():
    return repository.list_study_cases()


@router.get("/study-cases/ujjani/simulation/summary")
def ujjani_simulation_summary():
    path = UJJANI_RESULTS / "summary.json"
    if not path.exists():
        raise HTTPException(404, detail={"code": "SIMULATION_NOT_RUN", "message": "Run python -m simulation.run_ujjani first."})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/study-cases/ujjani/simulation/timeline")
def ujjani_simulation_timeline():
    summary = UJJANI_RESULTS / "summary.json"
    if not summary.exists():
        raise HTTPException(404, detail={"code": "SIMULATION_NOT_RUN", "message": "Simulation outputs are unavailable."})
    return json.loads(summary.read_text(encoding="utf-8")).get("timeline", [])


@router.get("/study-cases/ujjani/simulation/timeline/{minute}")
def ujjani_simulation_frame(minute: int):
    path = UJJANI_RESULTS / "timeline" / f"t{minute:03d}.geojson"
    if not path.exists():
        raise HTTPException(404, detail={"code": "FRAME_NOT_FOUND", "message": "Simulation frame is unavailable."})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/study-cases/{case_id}")
def study_case(case_id: str):
    case = repository.get_study_case(case_id)
    if case is None:
        raise HTTPException(404, detail={"code": "STUDY_CASE_NOT_FOUND", "message": "The requested study case does not exist."})
    return case


@router.get("/study-cases/{case_id}/validation")
def study_case_validation(case_id: str):
    validation = repository.validation(case_id)
    if validation is None:
        raise HTTPException(404, detail={"code": "STUDY_CASE_NOT_FOUND", "message": "The requested study case does not exist."})
    return validation


@router.get("/database/health")
def database_health(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "postgresql"}


@router.get("/dams", response_model=list[DamOut])
def dams(session: Session = Depends(get_session)):
    return session.scalars(select(Dam).order_by(Dam.name)).all()


@router.get("/dams/{dam_id}", response_model=DamOut)
def dam(dam_id: UUID, session: Session = Depends(get_session)):
    return require_record(session, Dam, dam_id)


@router.get("/scenarios", response_model=list[ScenarioOut])
def scenarios(session: Session = Depends(get_session)):
    return session.scalars(select(Scenario).order_by(Scenario.name)).all()


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def scenario(scenario_id: UUID, session: Session = Depends(get_session)):
    return require_record(session, Scenario, scenario_id)


@router.get("/simulations/{simulation_id}", response_model=SimulationOut)
def simulation(simulation_id: UUID, session: Session = Depends(get_session)):
    return require_record(session, SimulationRun, simulation_id)


@router.get("/simulations/{simulation_id}/summary", response_model=ImpactOut)
def summary(simulation_id: UUID, session: Session = Depends(get_session)):
    require_record(session, SimulationRun, simulation_id)
    record = session.scalar(select(ImpactSummary).where(ImpactSummary.simulation_run_id == simulation_id))
    if record is None:
        raise HTTPException(404, detail={"code": "SUMMARY_NOT_FOUND", "message": "No impact summary is available."})
    return record


@router.get("/simulations/{simulation_id}/timeline", response_model=TimelineOut)
def timeline(simulation_id: UUID, session: Session = Depends(get_session)):
    require_record(session, SimulationRun, simulation_id)
    if simulation_id != SIMULATION_ID:
        raise HTTPException(404, detail={"code": "TIMELINE_NOT_FOUND", "message": "No timeline output is available for this run."})
    return {"simulation_run_id": simulation_id, "is_sample": True, "values": TIMELINE}
