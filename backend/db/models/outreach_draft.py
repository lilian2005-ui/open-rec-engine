"""outreach_draft: stage 5 drafts and the reviewer's decision."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity,
                        SmallInteger, Text, func, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import DraftStatus, TextEnum, enum_check

if TYPE_CHECKING:
    from backend.db.models.app_user import AppUser
    from backend.db.models.lead import Lead


class OutreachDraft(Base):
    """A draft message for a qualified lead. Nothing is ever sent. The review
    decision is saved with the id of the logged-in user (``reviewed_by``).

    The 120-180 word rule is checked by Pydantic before saving, not here, so a
    reviewer's manual edit is never blocked by the database.
    """

    __tablename__ = "outreach_draft"
    __table_args__ = (
        enum_check("status", DraftStatus),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("word_count >= 0", name="word_count_non_negative"),
        CheckConstraint("(reviewed_by IS NULL) = (reviewed_at IS NULL)", name="review_complete"),
    )

    draft_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lead.lead_id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(SmallInteger)
    version: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    status: Mapped[DraftStatus] = mapped_column(
        TextEnum(DraftStatus), server_default=text("'pending_review'")
    )
    # no ON DELETE: users are deactivated, never deleted
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.user_id"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="drafts")
    reviewer: Mapped["AppUser | None"] = relationship(back_populates="reviewed_drafts")
