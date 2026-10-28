"""All SQLAlchemy models. Importing this package registers every table on
``Base.metadata`` (Alembic relies on it).

Usage:  from backend.db.models import Company, JobPosting
"""
from backend.db.base import Base
from backend.db.models.candidate import Candidate
from backend.db.models.company import Company
from backend.db.models.job_posting import JobPosting
from backend.db.models.job_requirement import JobRequirement
from backend.db.models.lead import Lead
from backend.db.models.outreach_draft import OutreachDraft

__all__ = ["Base", "Candidate", "Company", "JobPosting", "JobRequirement", "Lead", "OutreachDraft"]
