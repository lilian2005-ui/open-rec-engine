"""Secrets and environment values, read from .env (or real environment variables).
Editable app settings (threshold, fetch limit...) live in the app_setting table."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = ""
    HIMALAYAS_API_KEY: str = ""
    JWT_SECRET: str = ""


settings = Settings()