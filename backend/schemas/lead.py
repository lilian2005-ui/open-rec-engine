"""Stage 4: lead score (computed in code) and the lead reason (written by the LLM)."""
from pydantic import Field, model_validator

from .common import LLMOutput, Schema
from .enums import LeadStatus


class LeadEvidence(Schema):
    job_ids: list[int] = Field(default_factory=list)


class LeadReasonOutput(LLMOutput):
    """Stage 4 LLM output: words only, never numbers that change the score."""

    reason: str = Field(min_length=1, max_length=400)


class LeadResult(Schema):
    """Stage 4 result saved to lead and lead_snapshot (FR-17, FR-18, FR-19)."""

    company_id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    lead_score: int = Field(ge=0, le=100)
    best_job_score: int = Field(ge=0, le=100)
    qualifying_jobs: int = Field(ge=0)
    status: LeadStatus
    reason: str = Field(min_length=1)
    evidence: LeadEvidence

    @model_validator(mode="after")
    def _consistent(self):
        if len(self.evidence.job_ids) != self.qualifying_jobs:
            raise ValueError("evidence.job_ids must list exactly the qualifying jobs")
        if self.qualifying_jobs == 0:
            if self.lead_score != 0 or self.status != LeadStatus.NOT_QUALIFIED:
                raise ValueError("a lead with no suitable job has score 0 and status not_qualified")
        else:
            if self.status == LeadStatus.NOT_QUALIFIED:
                raise ValueError("a lead with suitable jobs cannot be not_qualified")
            expected = min(100, self.best_job_score + 5 * (self.qualifying_jobs - 1))
            if self.lead_score != expected:
                raise ValueError(f"lead_score must be {expected} (best job + 5 per extra job, max 100)")
        return self


def compute_lead_score(fits: list[int]) -> tuple[int, int, int]:
    """Lead score rule (FR-18). ``fits`` are the fit scores of the suitable jobs only.
    Returns (lead_score, best_job_score, qualifying_jobs)."""
    if not fits:
        return 0, 0, 0
    best = max(fits)
    return min(100, best + 5 * (len(fits) - 1)), best, len(fits)
