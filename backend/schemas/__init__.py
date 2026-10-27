"""Pydantic schemas for Open Rec. One model per JSON shape in the data contract.

Usage:  from backend.schemas import JobPosting, FitOutput, LeadResult
"""
from .auth import TokenOut, UserLogin, UserOut, UserRegister
from .candidate import CandidateProfile
from .common import gemini_schema, normalize_company_name, normalize_skill, to_utc
from .draft import DraftOutput, OutreachDraft, ReviewDecisionIn, count_words
from .enums import (DraftStatus, EmploymentType, ExtractionStatus, JobStatus, LeadStatus,
                    RemotePolicy, RunStatus, SalaryPeriod, Seniority, Source, TriggerType,
                    UserRole, display)
from .job import FitOutput, JobPosting, JobRequirements
from .lead import LeadEvidence, LeadReasonOutput, LeadResult, compute_lead_score
from .settings import AppSettings

__all__ = [
    "AppSettings", "CandidateProfile", "DraftOutput", "DraftStatus", "EmploymentType",
    "ExtractionStatus", "FitOutput", "JobPosting", "JobRequirements", "JobStatus",
    "LeadEvidence", "LeadReasonOutput", "LeadResult", "LeadStatus", "OutreachDraft",
    "RemotePolicy", "ReviewDecisionIn", "RunStatus", "SalaryPeriod", "Seniority", "Source",
    "TokenOut", "TriggerType", "UserLogin", "UserOut", "UserRegister", "UserRole",
    "compute_lead_score", "count_words", "display", "gemini_schema", "normalize_company_name",
    "normalize_skill", "to_utc",
]
