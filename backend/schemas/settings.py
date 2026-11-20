"""Editable settings stored in app_setting (FR-32). Secrets stay in .env, not here."""
from pydantic import Field, field_validator

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
    # Daily run: start once a day at this hour, Gaza time (0-23).
    # None = no fixed hour, use run_interval_hours instead.
    run_at_hour: int | None = Field(default=None, ge=0, le=23)

    @field_validator("run_at_hour", mode="before")
    @classmethod
    def empty_hour_is_none(cls, value):
        """app_setting stores text, so "no hour" is saved as "none"."""
        return None if value in ("none", "") else value

    def to_rows(self) -> list[tuple[str, str]]:
        """(key, value) pairs for the app_setting table."""
        return [(k, str(v.value if hasattr(v, "value") else v).lower()) for k, v in self.model_dump().items()]

    @classmethod
    def from_rows(cls, rows: dict[str, str]) -> "AppSettings":
        """Build settings from app_setting rows; missing keys get their defaults."""
        return cls.model_validate(rows)
