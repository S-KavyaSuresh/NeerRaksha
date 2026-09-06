from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database.session import get_session
from app.models import Dam, Scenario, SimulationRun, ImpactSummary
from app.schemas.responses import DamOut, ScenarioOut, SimulationOut, ImpactOut, TimelineOut
from app.services.sample import SIMULATION_ID, TIMELINE

router = APIRouter(prefix="/api")


def require_record(session, model, identifier):
    record = session.get(model, identifier)
    if record is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "The requested record does not exist."})
    return record


@router.get("/health")
def health():
    return {"status": "ok", "service": "JalDrishti", "milestone": 1}


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
