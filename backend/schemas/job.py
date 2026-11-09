"""Stages 1-3: JobPosting, JobRequirements, FitOutput (data contract 4)."""
import re
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from .common import LLMOutput, Schema, normalize_skills, to_utc
from .enums import EmploymentType, ExtractionStatus, RemotePolicy, SalaryPeriod, Seniority, Source

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class JobPosting(Schema):
    """Stage 1 output: one posting after it has been mapped from the source format."""

    source: Source
    external_id: str = Field(min_length=1)          # Himalayas guid / Remotive id
    url: str = Field(min_length=1)                  # Himalayas applicationLink / Remotive url
    title: str = Field(min_length=1, max_length=300)
    company_name: str = Field(min_length=1, max_length=200)
    description_raw: str | None = None              # original HTML
    description_text: str = Field(min_length=1)     # cleaned text
    content_hash: str                               # SHA-256 of title + description_text (Q3)
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    source_fields: dict[str, Any] | None = None    # structured source data, as given

    @field_validator("external_id", mode="before")
    @classmethod
    def _id_to_str(cls, v):
        return str(v) if isinstance(v, int) else v  # Remotive ids are numbers

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("content_hash")
    @classmethod
    def _hash(cls, v: str) -> str:
        v = v.lower()
        if not SHA256.match(v):
            raise ValueError("content_hash must be a 64-character SHA-256 hex string")
        return v

    @field_validator("posted_at", "expires_at", mode="before")
    @classmethod
    def _utc(cls, v):
        return to_utc(v)


class JobRequirements(LLMOutput):
    """Stage 2 LLM output. Values not stated in the posting stay null (FR-09)."""

    title: str = Field(min_length=1, max_length=300)
    seniority: Seniority | None = None
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    timezone_offsets: list[int] = Field(default_factory=list)
    employment_type: EmploymentType | None = None
    remote_policy: RemotePolicy | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.OK
    suspicious: bool = False                        # FR-10: instruction-like text found

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        return normalize_skills(v)

    @field_validator("salary_currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("timezone_offsets")
    @classmethod
    def _offsets(cls, v: list[int]) -> list[int]:
        for o in v:
            if not -12 <= o <= 14:
                raise ValueError(f"timezone offset {o} is outside -12..14")
        return v

    @model_validator(mode="after")
    def _checks(self):
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min cannot be greater than salary_max")
        # a suspicious posting or one without skills always goes to a person (FR-10, FR-11)
        if (self.suspicious or not self.required_skills) and self.extraction_status == ExtractionStatus.OK:
            self.extraction_status = ExtractionStatus.NEEDS_REVIEW
        return self

    @property
    def flag_reason(self) -> str | None:
        """Value for job_requirement.flag_reason."""
        if self.suspicious:
            return "Instruction-like text in the posting"
        if not self.required_skills:
            return "No required skills found"
        return None


class FitOutput(LLMOutput):
    """Stage 3 LLM output: one fit score for the job against the whole mock pool."""

    fit_score: int = Field(ge=0, le=100)
    fit_reason: str = Field(min_length=1, max_length=300)
