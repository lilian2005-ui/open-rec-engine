"""app_user: people who log in to review leads and drafts."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, Identity, Text, func,
                        text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import TextEnum, UserRole, enum_check

if TYPE_CHECKING:
    from backend.db.models.outreach_draft import OutreachDraft
    from backend.db.models.pipeline_run import PipelineRun


class AppUser(Base):
    """A reviewer or admin. Users are deactivated with ``is_active`` and never
    deleted, so runs, settings and reviews keep pointing at them.

    ``password_hash`` is a bcrypt hash; a plain-text password is never stored.
    """

    __tablename__ = "app_user"
    __table_args__ = (
        enum_check("role", UserRole),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("password_hash LIKE '$2%'", name="password_hash_bcrypt"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(TextEnum(UserRole), server_default=text("'reviewer'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="started_by_user",
                                                     passive_deletes="all")
    reviewed_drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="reviewer",
                                                                  passive_deletes="all")
