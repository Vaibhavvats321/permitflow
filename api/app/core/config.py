from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    # Database
    #
    # DATABASE_URL is the *application* connection and must use the restricted
    # `permitflow_app` role, never a superuser: Row Level Security is enforced
    # per table and a superuser bypasses it, which would silently disable tenant
    # isolation at runtime.
    DATABASE_URL: str

    # Privileged connection used only by Alembic migrations and the seed script.
    # Those run as the schema owner because the app role deliberately cannot
    # write rows outside its own tenant. Never import this into app code.
    DATABASE_URL_ADMIN: str

    # Password for the permitflow_app role, applied by bootstrap_role.py.
    APP_DB_PASSWORD: str

    # Shared password for seeded demo users. Demo data only.
    DEMO_USER_PASSWORD: str

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS: browser origins allowed to call this API. Comma-separated.
    # NoDecode stops pydantic-settings from JSON-parsing the raw env value, so
    # the validator below can split a plain comma-separated string.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
