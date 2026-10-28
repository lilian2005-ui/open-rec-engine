"""job_requirement: stage 2 output (requirements) plus the stage 3 fit score."""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (CHAR, BigInteger, CheckConstraint, DateTime, ForeignKey, Identity,
                        Numeric, SmallInteger, Text, text)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.db.models.enums import (EmploymentType, ExtractionStatus, RemotePolicy, Seniority,
                                     TextEnum, enum_check)

if TYPE_CHECKING:
    from backend.db.models.job_posting import JobPosting


class JobRequirement(Base):
    """Requirements extracted by the LLM from one job posting. Anything the posting
    does not state stays NULL; the system never guesses. A fit score is always
    stored together with its reason."""

    __tablename__ = "job_requirement"
    __table_args__ = (
        enum_check("seniority", Seniority),
        enum_check("employment_type", EmploymentType),
        enum_check("remote_policy", RemotePolicy),
        enum_check("extraction_status", ExtractionStatus),
        CheckConstraint("fit_score IS NULL OR fit_score BETWEEN 0 AND 100", name="fit_score_range"),
        CheckConstraint("(fit_score IS NULL) = (fit_reason IS NULL)", name="fit_score_has_reason"),
        CheckConstraint("min_years_experience >= 0", name="min_years_experience_non_negative"),
        CheckConstraint("salary_min <= salary_max", name="salary_range"),
        CheckConstraint("salary_currency ~ '^[A-Z]{3}$'", name="salary_currency_format"),
        CheckConstraint("required_skills::text = lower(required_skills::text)",
                        name="required_skills_lowercase"),
        CheckConstraint("preferred_skills::text = lower(preferred_skills::text)",
                        name="preferred_skills_lowercase"),
    )

    req_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_posting.job_id", ondelete="CASCADE"), unique=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    seniority: Mapped[Seniority | None] = mapped_column(TextEnum(Seniority))
    min_years_experience: Mapped[int | None] = mapped_column(SmallInteger)
    required_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    preferred_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    timezone_offsets: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    employment_type: Mapped[EmploymentType | None] = mapped_column(TextEnum(EmploymentType))
    remote_policy: Mapped[RemotePolicy | None] = mapped_column(TextEnum(RemotePolicy))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(CHAR(3))
    extraction_status: Mapped[ExtractionStatus] = mapped_column(TextEnum(ExtractionStatus))
    fit_score: Mapped[int | None] = mapped_column(SmallInteger)
    fit_reason: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_posting: Mapped["JobPosting"] = relationship(back_populates="requirement")
