"""Allowed values (data contract, section 11).

Stored in lowercase in the database; the UI shows them in capitals with spaces
(for example ``draft_ready`` is shown as ``DRAFT READY``).
"""
from enum import Enum


class Source(str, Enum):
    HIMALAYAS = "himalayas"
    REMOTIVE = "remotive"


class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    NEEDS_REVIEW = "needs_review"
    SCORED = "scored"
    FAILED = "failed"


class LeadStatus(str, Enum):
    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"
    DRAFT_READY = "draft_ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class DraftStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class TriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class UserRole(str, Enum):
    REVIEWER = "reviewer"
    ADMIN = "admin"


class Seniority(str, Enum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACTOR = "contractor"
    OTHER = "other"


class RemotePolicy(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class SalaryPeriod(str, Enum):
    HOURLY = "hourly"
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class ExtractionStatus(str, Enum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


def display(value: Enum) -> str:
    """Status as shown in the UI and the report: ``draft_ready`` -> ``DRAFT READY``."""
    return value.value.replace("_", " ").upper()
