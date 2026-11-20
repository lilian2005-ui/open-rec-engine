"""Shapes the API returns and accepts, exactly as in Open_Rec_API_Contract_v1.md.
Field names are the ones of the data contract and the database."""
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.schemas.common import Schema, normalize_skills, to_utc
from backend.schemas.enums import (DraftStatus, EmploymentType, JobStatus, LeadStatus,
                                   RemotePolicy, RunStatus, SalaryPeriod, Seniority, Source,
                                   TriggerType)

# Always UTC in the JSON ("...Z"), whatever time zone the database session uses.
UtcDatetime = Annotated[datetime, AfterValidator(to_utc)]


class Out(BaseModel):
    """Base for responses: can be built from a database row."""

    model_config = ConfigDict(from_attributes=True)


# ---------- jobs ----------

class JobListItem(Out):
    job_id: int
    title: str
    company_name: str
    source: Source
    posted_at: UtcDatetime | None
    status: JobStatus
    fit_score: int | None


class RequirementsOut(Out):
    required_skills: list[str]
    preferred_skills: list[str]
    seniority: Seniority | None
    min_years_experience: int | None
    timezone_offsets: list[int] | None
    employment_type: EmploymentType | None
    remote_policy: RemotePolicy | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    fit_score: int | None
    fit_reason: str | None
    flag_reason: str | None


class RequirementsEdit(Schema):
    """PATCH /jobs/{job_id}/requirements (FR-12): a person corrects what stage 2
    extracted. Only the fields that are sent change. Same limits as JobRequirements."""

    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    seniority: Seniority | None = None
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    timezone_offsets: list[int] | None = None
    employment_type: EmploymentType | None = None
    remote_policy: RemotePolicy | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalize_skills(v)

    @field_validator("salary_currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("timezone_offsets")
    @classmethod
    def _offsets(cls, v: list[int] | None) -> list[int] | None:
        for o in v or []:
            if not -12 <= o <= 14:
                raise ValueError(f"timezone offset {o} is outside -12..14")
        return v


class JobDetail(JobListItem):
    url: str
    description_text: str | None
    expires_at: UtcDatetime | None
    requirements: RequirementsOut | None    # null while the job is still discovered


# ---------- leads ----------

class LeadListItem(Out):
    lead_id: int
    company_name: str
    lead_score: int
    best_job_score: int
    qualifying_jobs: int
    status: LeadStatus
    reason: str


class CompanyOut(Out):
    name: str
    website: str | None
    location: str | None
    contact_name: str | None
    contact_title: str | None
    contact_email: str | None


class LeadJobOut(Out):
    job_id: int
    title: str
    fit_score: int | None
    fit_reason: str | None


class LeadHistoryOut(Out):
    run_id: int
    lead_score: int
    status: LeadStatus
    created_at: UtcDatetime


class DraftOut(Out):
    draft_id: int
    subject: str
    body: str
    word_count: int
    version: int
    status: DraftStatus
    review_comment: str | None
    reviewed_at: UtcDatetime | None
    # the reviewer's full name, not the user id that the database column holds
    reviewed_by: str | None = Field(default=None, validation_alias="reviewer_name")


class LeadDetail(LeadListItem):
    company: CompanyOut
    jobs: list[LeadJobOut]
    history: list[LeadHistoryOut]
    draft: DraftOut | None                  # null while the lead has no draft


class ContactUpdate(Schema):
    """PATCH /leads/{lead_id}/contact. Only the fields that are sent change."""

    contact_name: str | None = None
    contact_title: str | None = None
    contact_email: EmailStr | None = None

    @field_validator("contact_name", "contact_title", "contact_email", mode="before")
    @classmethod
    def _empty_is_null(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


# ---------- drafts ----------

class DraftEdit(Schema):
    """PATCH /drafts/{draft_id}. A person's edit: no 120-180 word rule."""

    subject: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1)


class RejectIn(Schema):
    review_comment: str = Field(min_length=1, max_length=1000)


# ---------- pipeline ----------

class RunStarted(BaseModel):
    run_id: int


class PipelineRunOut(Out):
    run_id: int
    status: RunStatus
    trigger_type: TriggerType
    # the full name of who pressed "Run pipeline"; null for a scheduled run
    started_by: str | None = Field(default=None, validation_alias="started_by_name")
    started_at: UtcDatetime
    finished_at: UtcDatetime | None
    jobs_fetched: int
    jobs_new: int
    jobs_updated: int
    # as saved by the runner (P1-6): {"stages": [...], "errors": [...]}; null while running
    errors: dict[str, Any] | None


# ---------- settings ----------

class SettingsOut(Out):
    """No remotive_enabled (Himalayas is the only source), no secrets (FR-32)."""

    lead_threshold: int
    fetch_limit: int
    himalayas_enabled: bool
    run_mode: TriggerType
    max_retries: int
    run_interval_hours: int
    run_at_hour: int | None


class SettingsUpdate(Schema):
    """PUT /settings. Only the fields that are sent change; the limits are checked
    by AppSettings."""

    lead_threshold: int | None = None
    fetch_limit: int | None = None
    himalayas_enabled: bool | None = None
    run_mode: TriggerType | None = None
    max_retries: int | None = None
    run_interval_hours: int | None = None
    run_at_hour: int | None = None
