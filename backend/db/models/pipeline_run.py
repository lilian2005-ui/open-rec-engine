"""pipeline_run: one row per pipeline run (the run log)."""
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index,
                        Integer, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import RunStatus, TextEnum, TriggerType, enum_check

if TYPE_CHECKING:
    from backend.db.models.app_user import AppUser
    from backend.db.models.job_posting import JobPosting
    from backend.db.models.lead import Lead
    from backend.db.models.lead_snapshot import LeadSnapshot


class PipelineRun(Base):
    """A manual or scheduled run. ``started_by`` is NULL for a scheduled run, and
    ``finished_at`` stays NULL until the run ends.

    Q5: at most one run can be ``running`` at a time; the partial unique index
    ``uq_pipeline_run_one_running`` rejects a second one even if two requests
    arrive together.
    """

    __tablename__ = "pipeline_run"
    __table_args__ = (
        enum_check("trigger_type", TriggerType),
        enum_check("status", RunStatus),
        CheckConstraint("jobs_fetched >= 0", name="jobs_fetched_non_negative"),
        CheckConstraint("jobs_new >= 0", name="jobs_new_non_negative"),
        CheckConstraint("jobs_updated >= 0", name="jobs_updated_non_negative"),
        Index("uq_pipeline_run_one_running", "status", unique=True,
              postgresql_where=text("status = 'running'")),
    )

    run_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # no ON DELETE: users are deactivated, never deleted
    started_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.user_id"), index=True
    )
    trigger_type: Mapped[TriggerType] = mapped_column(TextEnum(TriggerType))
    status: Mapped[RunStatus] = mapped_column(TextEnum(RunStatus))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jobs_fetched: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    jobs_new: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    jobs_updated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    errors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    started_by_user: Mapped["AppUser | None"] = relationship(back_populates="runs")
    job_postings: Mapped[list["JobPosting"]] = relationship(back_populates="run",
                                                            passive_deletes="all")
    leads: Mapped[list["Lead"]] = relationship(back_populates="run", passive_deletes="all")
    snapshots: Mapped[list["LeadSnapshot"]] = relationship(back_populates="run",
                                                           passive_deletes="all")
