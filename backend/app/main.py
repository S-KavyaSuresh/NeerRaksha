from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import router
from app.core.config import settings
from app.database.session import DatabaseUnavailable

app = FastAPI(title="NeerRaksha API", version="0.1.0", description="Dam-break and flood intelligence API. All simulation results are synthetic data.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["Accept", "Content-Type"])
app.include_router(router)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request: Request, exception: DatabaseUnavailable):
    messages = {"DATABASE_NOT_CONFIGURED": "Set DATABASE_URL in backend/.env, then restart the API.", "DATABASE_CONFIGURATION_INVALID": "Check the PostgreSQL connection string in backend/.env."}
    return JSONResponse(status_code=503, content={"error": {"code": exception.code, "message": messages.get(exception.code, "Database is unavailable. Try again shortly."), "retryable": exception.code == "DATABASE_UNAVAILABLE"}})


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exception: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"error": {"code": "DATABASE_UNAVAILABLE", "message": "Database connection or schema unavailable. Check Neon connectivity and run Alembic migrations.", "retryable": True}})
