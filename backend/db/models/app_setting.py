"""app_setting: settings edited from the Settings screen, one row per key."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

# Seeded by the initial migration (data contract v1.1, app_setting defaults).
DEFAULT_SETTINGS = {
    "lead_threshold": "60",
    "fetch_limit": "100",
    "himalayas_enabled": "true",
    "remotive_enabled": "true",
    "run_mode": "manual",
    "max_retries": "3",
}


class AppSetting(Base):
    """A setting as text (e.g. ``lead_threshold`` = ``"60"``); it is parsed by
    ``backend.schemas.AppSettings``. Secrets stay in .env and never go here."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    # no ON DELETE: users are deactivated, never deleted
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.user_id"), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
