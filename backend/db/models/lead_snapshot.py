"""lead_snapshot: a company's lead numbers at each run (lead history)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, SmallInteger,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import LeadStatus, TextEnum, enum_check

if TYPE_CHECKING:
    from backend.db.models.lead import Lead
    from backend.db.models.pipeline_run import PipelineRun


class LeadSnapshot(Base):
    """One row per company per run, with the same numbers as ``lead`` at that time."""

    __tablename__ = "lead_snapshot"
    __table_args__ = (
        UniqueConstraint("lead_id", "run_id"),
        enum_check("status", LeadStatus),
        CheckConstraint("lead_score BETWEEN 0 AND 100", name="lead_score_range"),
        CheckConstraint("best_job_score BETWEEN 0 AND 100", name="best_job_score_range"),
        CheckConstraint("qualifying_jobs >= 0", name="qualifying_jobs_non_negative"),
    )

    snapshot_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # indexed by uq_lead_snapshot_lead_id_run_id (lead_id is its first column)
    lead_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lead.lead_id", ondelete="CASCADE"))
    # no ON DELETE: a run with history cannot be deleted
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pipeline_run.run_id"), index=True
    )
    lead_score: Mapped[int] = mapped_column(SmallInteger)
    best_job_score: Mapped[int] = mapped_column(SmallInteger)
    qualifying_jobs: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[LeadStatus] = mapped_column(TextEnum(LeadStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="snapshots")
    run: Mapped["PipelineRun"] = relationship(back_populates="snapshots")
