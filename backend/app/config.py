import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# config.py lives at <project_root>/backend/app/config.py
# parents[0] = backend/app  parents[1] = backend  parents[2] = project root
# The same expression works inside Docker when the Dockerfile copies
# backend/ to /app/backend/ — parents[2] then resolves to /app.
_default_scenarios_dir = str(Path(__file__).resolve().parents[2] / "scenarios")


class Settings(BaseSettings):
    APP_NAME: str = "Neonatal Resuscitation Simulator"
    DEBUG: bool = False
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Override with SCENARIOS_DIR env var when the default path is wrong
    # (e.g. a custom Docker layout or running tests from a non-standard CWD).
    SCENARIOS_DIR: str = _default_scenarios_dir

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            if value.startswith("["):
                decoded = json.loads(value)
                return [str(origin).strip() for origin in decoded if str(origin).strip()]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
