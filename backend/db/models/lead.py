"""lead: the current score, reason and evidence of each company (stage 4)."""
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, SmallInteger,
                        Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import LeadStatus, TextEnum, enum_check

if TYPE_CHECKING:
    from backend.db.models.company import Company
    from backend.db.models.lead_snapshot import LeadSnapshot
    from backend.db.models.outreach_draft import OutreachDraft
    from backend.db.models.pipeline_run import PipelineRun


class Lead(Base):
    """A company ranked as a lead. The score is computed in code (data contract
    section 6); the LLM writes only ``reason``. ``evidence`` always holds
    ``{"job_ids": [...]}``. Each run also saves the numbers in ``lead_snapshot``.

    Scoring rules:
    - A job is suitable when its status is ``scored`` (Q1: a changed posting goes
      back to ``discovered`` and is left out until it is scored again), its
      fit_score is at least ``lead_threshold``, and it has not expired (Q7).
    - lead_score = best suitable job + 5 per extra suitable job, capped at 100.
    - With no suitable job the score is 0 and the status ``not_qualified``,
      and the reverse.
    """

    __tablename__ = "lead"
    __table_args__ = (
        enum_check("status", LeadStatus),
        CheckConstraint("char_length(reason) > 0", name="reason_not_empty"),
        CheckConstraint("lead_score BETWEEN 0 AND 100", name="lead_score_range"),
        CheckConstraint("best_job_score BETWEEN 0 AND 100", name="best_job_score_range"),
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
    # no ON DELETE: a run that scored leads cannot be deleted
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pipeline_run.run_id"), index=True
    )
    lead_score: Mapped[int] = mapped_column(SmallInteger)
    best_job_score: Mapped[int] = mapped_column(SmallInteger)
    qualifying_jobs: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[LeadStatus] = mapped_column(TextEnum(LeadStatus), index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="lead")
    run: Mapped["PipelineRun | None"] = relationship(back_populates="leads")
    drafts: Mapped[list["OutreachDraft"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", passive_deletes=True
    )
    snapshots: Mapped[list["LeadSnapshot"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", passive_deletes=True
    )
