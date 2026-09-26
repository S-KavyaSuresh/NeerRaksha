from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# pydantic-settings reads _ENV_FILE into the Settings fields below only; it never
# exports those values into os.environ. Modules that read configuration directly
# from os.environ (e.g. remote_sensing/gee_client.py's EARTHENGINE_PROJECT) would
# otherwise only ever see a value manually exported in the current shell, which
# is lost on the next restart from a fresh process. load_dotenv() makes .env the
# single persistent local-config source for both paths; it never overrides a
# variable already present in the real process environment.
load_dotenv(_ENV_FILE)


class Settings(BaseSettings):
    database_url: str = ""
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return sorted({origin.strip().rstrip("/") for origin in [self.frontend_origin, *self.frontend_origins.split(",")] if origin.strip() and origin.strip() != "*"})


settings = Settings()
