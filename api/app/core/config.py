import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    DATABASE_URL: str
    
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

settings = Settings()

