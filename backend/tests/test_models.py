"""P0-2: the models save and load, and every data contract rule is enforced by
PostgreSQL. Each failing case asserts the name of the constraint that caught it."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from backend.db.models import Candidate, Company, JobPosting, JobRequirement, Lead, OutreachDraft
from backend.db.models.enums import DraftStatus, ExtractionStatus, JobStatus, LeadStatus, Source
from backend.db.normalize import content_hash

NOW = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)
TEXT = "We are looking for a Senior React Developer..."


# ---------- builders ----------

def company(db, name="Acme Corp", **over):
    c = Company(name=name, **over)
    db.add(c)
    db.flush()
    return c


def job(db, comp=None, **over):
    data = dict(
        source=Source.HIMALAYAS, external_id="acme-senior-react-developer",
        url="https://himalayas.app/companies/acme/jobs/senior-react-developer",
        title="Senior React Developer", description_raw=f"<p>{TEXT}</p>",
        description_text=TEXT, content_hash=content_hash("Senior React Developer", TEXT),
        posted_at=datetime(2026, 10, 18, 9, tzinfo=timezone.utc),
    )
    data.update(over)
    j = JobPosting(company=comp or company(db), **data)
    db.add(j)
    db.flush()
    return j


def requirement(db, jp=None, **over):
    data = dict(
        title="Senior React Developer", seniority="senior", min_years_experience=5,
        required_skills=["react", "typescript", "redux"], preferred_skills=["graphql"],
        timezone_offsets=[-5, -4], employment_type="full_time", remote_policy="remote",
        extraction_status=ExtractionStatus.OK, fit_score=92,
        fit_reason="Our pool has 3 profiles with react, typescript and redux at 5+ years",
        parsed_at=NOW,
    )
    data.update(over)
    r = JobRequirement(job_posting=jp or job(db), **data)
    db.add(r)
    db.flush()
    return r


def lead(db, comp=None, **over):
    data = dict(lead_score=170, qualifying_jobs=2, status=LeadStatus.QUALIFIED,
                reason="Acme Corp has 2 open React roles that our talent pool covers well.",
                evidence={"job_ids": [12, 15]}, scored_at=NOW)
    data.update(over)
    obj = Lead(company=comp or company(db), **data)
    db.add(obj)
    db.flush()
    return obj


def draft(db, ld=None, **over):
    data = dict(subject="Senior React talent available for Acme Corp",
                body="Hello Acme Corp team, I noticed you are hiring a Senior React Developer...",
                word_count=148)
    data.update(over)
    d = OutreachDraft(lead=ld or lead(db), **data)
    db.add(d)
    db.flush()
    return d


def candidate(db, **over):
    data = dict(candidate_id=101, display_name="Candidate 101", headline="Senior Frontend Engineer",
                years_experience=Decimal("7.0"), seniority="senior",
                skills=["react", "typescript", "redux"], timezone_offsets=[-5],
                availability="available in 2 weeks", summary="Frontend engineer...")
    data.update(over)
    c = Candidate(**data)
    db.add(c)
    db.flush()
    return c


def violates(db, constraint, build):
    """``build`` must fail on flush with ``constraint``; the session is reset after."""
    with pytest.raises(IntegrityError) as err:
        build()
        db.flush()
    db.rollback()
    assert err.value.orig.diag.constraint_name == constraint


# ---------- full chain ----------

def test_full_chain_saves_and_loads_back(db):
    comp = company(db, website="https://acme.example")
    jp = job(db, comp)
    req = requirement(db, jp)
    ld = lead(db, comp, evidence={"job_ids": [jp.job_id], "matches": {"react": 3}})
    dr = draft(db, ld)
    ids = (comp.company_id, jp.job_id, req.req_id, ld.lead_id, dr.draft_id)
    db.expunge_all()

    comp = db.get(Company, ids[0])
    assert comp.contact_email is None
    jp = comp.job_postings[0]
    assert jp.job_id == ids[1]
    assert jp.status is JobStatus.DISCOVERED                # default
    assert jp.discovered_at.tzinfo is not None              # default now(), TIMESTAMPTZ
    assert jp.expires_at is None

    req = jp.requirement
    assert req.req_id == ids[2]
    assert req.required_skills == ["react", "typescript", "redux"]
    assert req.timezone_offsets == [-5, -4]
    assert req.salary_min is None and req.salary_max is None and req.salary_currency is None

    ld = comp.lead
    assert ld.evidence == {"job_ids": [ids[1]], "matches": {"react": 3}}
    dr = ld.drafts[0]
    assert dr.draft_id == ids[4]
    assert dr.version == 1                                  # default
    assert dr.status is DraftStatus.PENDING_REVIEW          # default
    assert dr.created_at is not None
    assert dr.reviewed_by is None and dr.reviewed_at is None


def test_skill_arrays_default_to_empty(db):
    req = JobRequirement(job_posting=job(db), extraction_status=ExtractionStatus.NEEDS_REVIEW)
    db.add(req)
    db.flush()
    db.refresh(req)
    assert req.required_skills == [] and req.preferred_skills == []


def test_candidate_round_trip_with_given_id(db):
    candidate(db)
    db.expunge_all()
    c = db.get(Candidate, 101)
    assert c.years_experience == Decimal("7.0")
    assert c.skills == ["react", "typescript", "redux"]


# ---------- company (Q2) ----------

def test_company_name_is_unique(db):
    company(db)
    violates(db, "uq_company_name", lambda: db.add(Company(name="Acme Corp")))


@pytest.mark.parametrize("variant", ["ACME  corp", " acme corp ", "Acme\tCorp"])
def test_company_name_variants_are_one_company(db, variant):
    company(db)
    violates(db, "uq_company_name_key", lambda: db.add(Company(name=variant)))


def test_company_with_legal_suffix_is_another_company(db):
    company(db)
    company(db, "Acme Corp Inc.")
    assert db.scalar(select(func.count()).select_from(Company)) == 2


def test_company_with_jobs_cannot_be_deleted(db):
    jp = job(db)
    violates(db, "fk_job_posting_company_id_company",
             lambda: db.execute(delete(Company).where(Company.company_id == jp.company_id)))


# ---------- job_posting ----------

def test_source_and_external_id_are_unique(db):
    comp = company(db)
    job(db, comp)
    violates(db, "uq_job_posting_source_external_id", lambda: job(db, comp))


def test_same_external_id_from_another_source_is_allowed(db):
    comp = company(db)
    job(db, comp)
    job(db, comp, source=Source.REMOTIVE)


def test_content_hash_must_be_64_characters(db):
    violates(db, "ck_job_posting_content_hash_length", lambda: job(db, content_hash="abc"))


def test_expires_at_is_stored(db):
    expires = NOW + timedelta(days=30)
    jp = job(db, expires_at=expires)
    db.expunge_all()
    assert db.get(JobPosting, jp.job_id).expires_at == expires


def test_unknown_enum_value_is_rejected_by_the_model(db):
    with pytest.raises(StatementError) as err:
        job(db, status="open")
    db.rollback()
    assert isinstance(err.value.orig, ValueError)


def test_unknown_enum_value_is_rejected_by_the_database(db):
    jp = job(db)
    violates(db, "ck_job_posting_status_enum", lambda: db.execute(
        text("UPDATE job_posting SET status = 'open' WHERE job_id = :id"), {"id": jp.job_id}))


@pytest.mark.parametrize("table, column", [
    ("job_posting", "source"), ("job_posting", "status"),
    ("job_requirement", "seniority"), ("job_requirement", "employment_type"),
    ("job_requirement", "remote_policy"), ("job_requirement", "extraction_status"),
    ("candidate", "seniority"), ("lead", "status"), ("outreach_draft", "status"),
])
def test_enum_columns_are_text(db, table, column):
    data_type = db.scalar(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"), {"t": table, "c": column})
    assert data_type == "text"


# ---------- job_requirement ----------

@pytest.mark.parametrize("score", [-1, 101])
def test_fit_score_range(db, score):
    violates(db, "ck_job_requirement_fit_score_range", lambda: requirement(db, fit_score=score))


def test_fit_score_bounds_are_allowed(db):
    req = requirement(db, fit_score=0)
    requirement(db, job(db, req.job_posting.company, external_id="other"), fit_score=100)


@pytest.mark.parametrize("over", [{"fit_reason": None}, {"fit_score": None}])
def test_fit_score_and_reason_come_together(db, over):
    violates(db, "ck_job_requirement_fit_score_has_reason", lambda: requirement(db, **over))


def test_unscored_requirement_is_allowed(db):
    requirement(db, fit_score=None, fit_reason=None)


def test_min_years_experience_is_not_negative(db):
    violates(db, "ck_job_requirement_min_years_experience_non_negative",
             lambda: requirement(db, min_years_experience=-1))


def test_salary_min_not_above_max(db):
    violates(db, "ck_job_requirement_salary_range",
             lambda: requirement(db, salary_min=Decimal("120000"), salary_max=Decimal("90000")))


def test_salary_with_one_side_is_allowed(db):
    requirement(db, salary_min=Decimal("90000"), salary_currency="USD")


@pytest.mark.parametrize("currency", ["usd", "US1"])
def test_salary_currency_is_three_capitals(db, currency):
    violates(db, "ck_job_requirement_salary_currency_format",
             lambda: requirement(db, salary_currency=currency))


@pytest.mark.parametrize("column", ["required_skills", "preferred_skills"])
def test_requirement_skills_are_lowercase(db, column):
    violates(db, f"ck_job_requirement_{column}_lowercase",
             lambda: requirement(db, **{column: ["react", "TypeScript"]}))


def test_one_requirement_per_job(db):
    jp = job(db)
    requirement(db, jp)
    violates(db, "uq_job_requirement_job_id", lambda: requirement(db, jp))


def test_deleting_a_job_deletes_its_requirement(db):
    req = requirement(db)
    db.execute(delete(JobPosting).where(JobPosting.job_id == req.job_id))
    assert db.scalar(select(func.count()).select_from(JobRequirement)) == 0


# ---------- candidate ----------

def test_candidate_years_experience_is_not_negative(db):
    violates(db, "ck_candidate_years_experience_non_negative",
             lambda: candidate(db, years_experience=Decimal("-1")))


def test_candidate_skills_are_lowercase(db):
    violates(db, "ck_candidate_skills_lowercase", lambda: candidate(db, skills=["React"]))


# ---------- lead ----------

def test_lead_reason_is_not_empty(db):
    violates(db, "ck_lead_reason_not_empty", lambda: lead(db, reason=""))


def test_lead_score_is_not_negative(db):
    violates(db, "ck_lead_lead_score_non_negative", lambda: lead(db, lead_score=-1))


def test_qualifying_jobs_is_not_negative(db):
    violates(db, "ck_lead_qualifying_jobs_non_negative",
             lambda: lead(db, qualifying_jobs=-1, status=LeadStatus.QUALIFIED))


def test_not_qualified_lead_has_no_jobs(db):
    violates(db, "ck_lead_not_qualified_iff_no_jobs",
             lambda: lead(db, status=LeadStatus.NOT_QUALIFIED, qualifying_jobs=2))


def test_qualified_lead_has_jobs(db):
    violates(db, "ck_lead_not_qualified_iff_no_jobs",
             lambda: lead(db, status=LeadStatus.QUALIFIED, qualifying_jobs=0))


def test_not_qualified_lead_without_jobs_is_allowed(db):
    lead(db, status=LeadStatus.NOT_QUALIFIED, qualifying_jobs=0, lead_score=0,
         evidence={"job_ids": []})


@pytest.mark.parametrize("evidence", [{}, {"jobs": [12]}, {"job_ids": 12}, {"job_ids": None}])
def test_lead_evidence_has_a_job_ids_array(db, evidence):
    violates(db, "ck_lead_evidence_has_job_ids", lambda: lead(db, evidence=evidence))


def test_one_lead_per_company(db):
    comp = company(db)
    lead(db, comp)
    violates(db, "uq_lead_company_id", lambda: lead(db, comp))


def test_deleting_a_company_deletes_its_lead_and_drafts(db):
    dr = draft(db)
    company_id = dr.lead.company_id
    db.execute(delete(Company).where(Company.company_id == company_id))
    assert db.scalar(select(func.count()).select_from(Lead)) == 0
    assert db.scalar(select(func.count()).select_from(OutreachDraft)) == 0


# ---------- outreach_draft ----------

def test_draft_version_is_at_least_one(db):
    violates(db, "ck_outreach_draft_version_positive", lambda: draft(db, version=0))


def test_draft_word_count_is_not_negative(db):
    violates(db, "ck_outreach_draft_word_count_non_negative", lambda: draft(db, word_count=-1))


@pytest.mark.parametrize("over", [{"reviewed_by": "reviewer@simera"}, {"reviewed_at": NOW}])
def test_review_has_reviewer_and_time(db, over):
    violates(db, "ck_outreach_draft_review_complete", lambda: draft(db, **over))


def test_reviewed_draft_is_allowed(db):
    draft(db, status=DraftStatus.APPROVED, reviewed_by="reviewer@simera", reviewed_at=NOW)


def test_word_range_is_not_enforced_by_the_database(db):
    """120-180 words is checked by Pydantic, so a reviewer's short edit still saves."""
    draft(db, status=DraftStatus.EDITED, body="Short edit.", word_count=2,
          reviewed_by="reviewer@simera", reviewed_at=NOW)


def test_deleting_a_lead_deletes_its_drafts(db):
    dr = draft(db)
    draft(db, dr.lead, version=2)
    db.execute(delete(Lead).where(Lead.lead_id == dr.lead_id))
    assert db.scalar(select(func.count()).select_from(OutreachDraft)) == 0
