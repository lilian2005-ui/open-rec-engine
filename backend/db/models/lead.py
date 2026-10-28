"""lead: one row per company with its score, reason and evidence (stage 4)."""
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer,
                        SmallInteger, Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import LeadStatus, TextEnum, enum_check

if TYPE_CHECKING:
    from backend.db.models.company import Company
    from backend.db.models.outreach_draft import OutreachDraft


class Lead(Base):
    """A company ranked as a lead. The score is computed in code; the LLM writes
    only ``reason``. ``evidence`` always holds ``{"job_ids": [...]}``.

    Scoring rules:
    - Only jobs with status ``scored`` count (Q1). A changed posting goes back to
      ``discovered`` and is left out until it is scored again.
    - An expired job (``expires_at`` in the past) is not counted (Q7).
    - A lead with no qualifying job is ``not_qualified``, and the reverse.
    """

    __tablename__ = "lead"
    __table_args__ = (
        enum_check("status", LeadStatus),
        CheckConstraint("char_length(reason) > 0", name="reason_not_empty"),
        CheckConstraint("lead_score >= 0", name="lead_score_non_negative"),
        CheckConstraint("qualifying_jobs >= 0", name="qualifying_jobs_non_negative"),
        CheckConstraint("(status = 'not_qualified') = (qualifying_jobs = 0)",
                        name="not_qualified_iff_no_jobs"),
        # coalesce: a missing key gives NULL, and NULL passes a CHECK
        CheckConstraint("coalesce(jsonb_typeof(evidence -> 'job_ids'), '') = 'array'",
                        name="evidence_has_job_ids"),
    )

    lead_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("company.company_id", ondelete="CASCADE"), unique=True
    )
    lead_score: Mapped[int] = mapped_column(Integer)
    qualifying_jobs: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[LeadStatus] = mapped_column(TextEnum(LeadStatus), index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="lead")
    drafts: Mapped[list["OutreachDraft"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", passive_deletes=True
    )
