"""job_posting: stage 1 output, one row per (source, external_id)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (CHAR, BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import JobStatus, Source, TextEnum, enum_check

if TYPE_CHECKING:
    from backend.db.models.company import Company
    from backend.db.models.job_requirement import JobRequirement
    from backend.db.models.pipeline_run import PipelineRun


class JobPosting(Base):
    """A job posting collected from Himalayas or Remotive.

    Q1: a posting that changed at the source (new ``content_hash``) updates this same
    row, found by (source, external_id); ``updated_at`` is set and the status goes
    back to ``discovered``. ``run_id`` is the last run that fetched it.
    Q7: ``expires_at`` comes from Himalayas ``expiryDate`` (NULL for Remotive); after
    it, the job no longer counts in the lead score.
    """

    __tablename__ = "job_posting"
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        enum_check("source", Source),
        enum_check("status", JobStatus),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_length"),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # no ON DELETE: a company that has jobs cannot be deleted
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("company.company_id"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pipeline_run.run_id"), index=True
    )
    source: Mapped[Source] = mapped_column(TextEnum(Source))
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description_raw: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(CHAR(64), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[JobStatus] = mapped_column(
        TextEnum(JobStatus), server_default=text("'discovered'"), index=True
    )

    company: Mapped["Company"] = relationship(back_populates="job_postings")
    run: Mapped["PipelineRun | None"] = relationship(back_populates="job_postings")
    requirement: Mapped["JobRequirement | None"] = relationship(
        back_populates="job_posting", cascade="all, delete-orphan", passive_deletes=True
    )
