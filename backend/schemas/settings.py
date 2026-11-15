"""Editable settings stored in app_setting (FR-32). Secrets stay in .env, not here."""
from pydantic import Field

from .common import Schema
from .enums import TriggerType


class AppSettings(Schema):
    lead_threshold: int = Field(default=60, ge=0, le=100)
    fetch_limit: int = Field(default=100, ge=1, le=500)
    himalayas_enabled: bool = True
    remotive_enabled: bool = True
    run_mode: TriggerType = TriggerType.MANUAL
    max_retries: int = Field(default=3, ge=0, le=5)
    # P1-7: a scheduled run starts when the last finished run is this many hours old
    run_interval_hours: int = Field(default=32, ge=1, le=168)

    def to_rows(self) -> list[tuple[str, str]]:
        """(key, value) pairs for the app_setting table."""
        return [(k, str(v.value if hasattr(v, "value") else v).lower()) for k, v in self.model_dump().items()]

    @classmethod
    def from_rows(cls, rows: dict[str, str]) -> "AppSettings":
        """Build settings from app_setting rows; missing keys get their defaults."""
        return cls.model_validate(rows)
