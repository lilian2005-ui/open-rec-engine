"""All SQLAlchemy models (data contract v1.1, 10 tables). Importing this package
registers every table on ``Base.metadata`` (Alembic relies on it).

Usage:  from backend.db.models import Company, JobPosting
"""
from backend.db.base import Base
from backend.db.models.app_setting import DEFAULT_SETTINGS, AppSetting
from backend.db.models.app_user import AppUser
from backend.db.models.candidate import Candidate
from backend.db.models.company import Company
from backend.db.models.job_posting import JobPosting
from backend.db.models.job_requirement import JobRequirement
from backend.db.models.lead import Lead
from backend.db.models.lead_snapshot import LeadSnapshot
from backend.db.models.outreach_draft import OutreachDraft
from backend.db.models.pipeline_run import PipelineRun

__all__ = [
    "DEFAULT_SETTINGS", "AppSetting", "AppUser", "Base", "Candidate", "Company", "JobPosting",
    "JobRequirement", "Lead", "LeadSnapshot", "OutreachDraft", "PipelineRun",
]
