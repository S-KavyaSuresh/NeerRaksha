from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from app.core.config import settings


class Base(DeclarativeBase):
    pass


class DatabaseUnavailable(Exception):
    def __init__(self, code="DATABASE_UNAVAILABLE"):
        self.code = code


@lru_cache
def get_engine():
    if not settings.database_url.strip():
        raise DatabaseUnavailable("DATABASE_NOT_CONFIGURED")
    try:
        url = make_url(settings.database_url)
        if url.get_backend_name() not in ("postgres", "postgresql"):
            raise ValueError("PostgreSQL required")
        url = url.set(drivername="postgresql+psycopg")
        return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 5})
    except Exception:
        raise DatabaseUnavailable("DATABASE_CONFIGURATION_INVALID") from None


def get_session():
    with Session(get_engine()) as session:
        yield session
