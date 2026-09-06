from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = ""
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return sorted({origin.strip().rstrip("/") for origin in [self.frontend_origin, *self.frontend_origins.split(",")] if origin.strip() and origin.strip() != "*"})


settings = Settings()
