"""Secrets and environment values, read from .env (or real environment variables).
Editable app settings (threshold, fetch limit...) live in the app_setting table."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_MIN_INTERVAL_SECONDS: float = 4.5   # free tier: 15 requests/minute
    HIMALAYAS_API_KEY: str = ""
    JWT_SECRET: str = ""
    JWT_EXPIRE_MINUTES: int = 480
    # Frontend addresses allowed to call the API (CORS). In .env write it as a JSON list.
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
