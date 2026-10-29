"""P0-2: the models save and load, and every data contract v1.1 rule is enforced by
PostgreSQL. Each failing case asserts the name of the constraint that caught it."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from backend.db.models import (AppSetting, AppUser, Candidate, Company, JobPosting, JobRequirement,
                               Lead, LeadSnapshot, OutreachDraft, PipelineRun)
from backend.db.models.enums import (DraftStatus, ExtractionStatus, JobStatus, LeadStatus,
                                     RunStatus, SalaryPeriod, Source, TriggerType, UserRole)
from backend.db.normalize import company_name_key, content_hash

NOW = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)
TEXT = "We are looking for a Senior React Developer..."
HASH = content_hash("Senior React Developer", TEXT)
BCRYPT = "$2b$12$abcdefghijklmnopqrstuuJ1Ywq0VXq3l7qk2l3Gq3m6y6sJ3s6xW"


# ---------- builders ----------

def user(db, email="reviewer@simera.example", **over):
    data = dict(full_name="Sam Reviewer", email=email, password_hash=BCRYPT)
    data.update(over)
    u = AppUser(**data)
    db.add(u)
    db.flush()
    return u


def run(db, **over):
    data = dict(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED, started_at=NOW)
    data.update(over)
    r = PipelineRun(**data)
    db.add(r)
    db.flush()
    return r


def company(db, name="Acme Corp", **over):
    c = Company(name=name, normalized_name=company_name_key(name), **over)
    db.add(c)
    db.flush()
    return c


def job(db, comp=None, **over):
    data = dict(
        source=Source.HIMALAYAS, external_id="acme-senior-react-developer-7f3a",
        url="https://himalayas.app/companies/acme/jobs/senior-react-developer",
        title="Senior React Developer", description_raw=f"<p>{TEXT}</p>",
        description_text=TEXT, content_hash=HASH,
        posted_at=datetime(2026, 10, 18, 9, tzinfo=timezone.utc),
    )
    data.update(over)
    j = JobPosting(company=comp or company(db), **data)
    db.add(j)
    db.flush()
    return j


def requirement(db, jp=None, **over):
    data = dict(
        source_hash=HASH, title="Senior React Developer", seniority="senior",
        min_years_experience=5, required_skills=["react", "typescript", "redux"],
        preferred_skills=["graphql"], timezone_offsets=[-5, -4], employment_type="full_time",
        remote_policy="remote", extraction_status=ExtractionStatus.OK, fit_score=92,
        fit_reason="Our pool has 3 profiles with react, typescript and redux at 5+ years",
        parsed_at=NOW,
    )
    data.update(over)
    r = JobRequirement(job_posting=jp or job(db), **data)
    db.add(r)
    db.flush()
    return r


def lead(db, comp=None, **over):
    data = dict(lead_score=97, best_job_score=92, qualifying_jobs=2, status=LeadStatus.QUALIFIED,
                reason="Acme Corp has 2 open React roles that our talent pool covers well.",
                evidence={"job_ids": [12, 15]}, scored_at=NOW)
    data.update(over)
    obj = Lead(company=comp or company(db), **data)
    db.add(obj)
    db.flush()
    return obj


def snapshot(db, ld=None, rn=None, **over):
    data = dict(lead_score=97, best_job_score=92, qualifying_jobs=2, status=LeadStatus.QUALIFIED)
    data.update(over)
    s = LeadSnapshot(lead=ld or lead(db), run=rn or run(db), **data)
    db.add(s)
    db.flush()
    return s


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


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


# ---------- full chain ----------

def test_full_chain_saves_and_loads_back(db):
    reviewer = user(db)
    rn = run(db, started_by_user=reviewer, jobs_fetched=40, jobs_new=12, jobs_updated=3,
             errors={"remotive": ["timeout"]}, finished_at=NOW + timedelta(minutes=5))
    comp = company(db, website="https://acme.example")
    jp = job(db, comp, run=rn)
    req = requirement(db, jp)
    ld = lead(db, comp, run=rn, evidence={"job_ids": [jp.job_id], "matches": {"react": 3}})
    snap = snapshot(db, ld, rn)
    dr = draft(db, ld, status=DraftStatus.APPROVED, reviewer=reviewer, reviewed_at=NOW)
    ids = dict(user=reviewer.user_id, run=rn.run_id, company=comp.company_id, job=jp.job_id,
               req=req.req_id, lead=ld.lead_id, snap=snap.snapshot_id, draft=dr.draft_id)
    db.expunge_all()

    reviewer = db.get(AppUser, ids["user"])
    assert reviewer.role is UserRole.REVIEWER                # default
    assert reviewer.is_active is True                        # default
    assert reviewer.created_at is not None                   # default now()

    rn = db.get(PipelineRun, ids["run"])
    assert rn.started_by_user.user_id == ids["user"]
    assert (rn.jobs_fetched, rn.jobs_new, rn.jobs_updated) == (40, 12, 3)
    assert rn.errors == {"remotive": ["timeout"]}

    comp = db.get(Company, ids["company"])
    assert comp.normalized_name == "acme corp"
    assert comp.contact_email is None
    jp = comp.job_postings[0]
    assert jp.run.run_id == ids["run"]
    assert jp.status is JobStatus.DISCOVERED                 # default
    assert jp.discovered_at.tzinfo is not None               # default now(), TIMESTAMPTZ
    assert jp.expires_at is None and jp.updated_at is None

    req = jp.requirement
    assert req.req_id == ids["req"]
    assert req.source_hash == HASH
    assert req.required_skills == ["react", "typescript", "redux"]
    assert req.timezone_offsets == [-5, -4]
    assert req.salary_min is None and req.salary_max is None and req.salary_currency is None
    assert req.salary_period is None and req.flag_reason is None

    ld = comp.lead
    assert (ld.lead_score, ld.best_job_score, ld.qualifying_jobs) == (97, 92, 2)
    assert ld.run.run_id == ids["run"]
    assert ld.evidence == {"job_ids": [ids["job"]], "matches": {"react": 3}}
    assert [s.snapshot_id for s in ld.snapshots] == [ids["snap"]]
    assert ld.snapshots[0].created_at is not None            # default now()

    dr = ld.drafts[0]
    assert dr.draft_id == ids["draft"]
    assert dr.version == 1                                   # default
    assert dr.reviewer.user_id == ids["user"]
    assert dr.created_at is not None


def test_draft_defaults(db):
    dr = draft(db)
    db.expunge_all()
    dr = db.get(OutreachDraft, dr.draft_id)
    assert dr.status is DraftStatus.PENDING_REVIEW
    assert dr.reviewed_by is None and dr.reviewed_at is None


def test_skill_arrays_default_to_empty(db):
    req = JobRequirement(job_posting=job(db), extraction_status=ExtractionStatus.NEEDS_REVIEW)
    db.add(req)
    db.flush()
    db.refresh(req)
    assert req.required_skills == [] and req.preferred_skills == []


def test_salary_period_is_stored(db):
    req = requirement(db, salary_min=Decimal("90000"), salary_max=Decimal("120000"),
                      salary_currency="USD", salary_period=SalaryPeriod.ANNUAL)
    db.expunge_all()
    assert db.get(JobRequirement, req.req_id).salary_period is SalaryPeriod.ANNUAL


def test_candidate_round_trip_with_given_id(db):
    candidate(db)
    db.expunge_all()
    c = db.get(Candidate, 101)
    assert c.years_experience == Decimal("7.0")
    assert c.skills == ["react", "typescript", "redux"]


# ---------- app_user ----------

def test_email_is_unique(db):
    user(db)
    violates(db, "uq_app_user_email", lambda: user(db))


def test_email_is_lowercase(db):
    violates(db, "ck_app_user_email_lowercase", lambda: user(db, email="Reviewer@Simera.example"))


@pytest.mark.parametrize("password_hash", ["secret123", "", "pbkdf2:sha256:abc"])
def test_password_hash_must_be_bcrypt(db, password_hash):
    violates(db, "ck_app_user_password_hash_bcrypt", lambda: user(db, password_hash=password_hash))


def test_admin_role_is_allowed(db):
    assert user(db, role=UserRole.ADMIN).role is UserRole.ADMIN


def test_user_referenced_by_a_draft_cannot_be_deleted(db):
    reviewer = user(db)
    draft(db, reviewer=reviewer, reviewed_at=NOW, status=DraftStatus.APPROVED)
    violates(db, "fk_outreach_draft_reviewed_by_app_user",
             lambda: db.execute(delete(AppUser).where(AppUser.user_id == reviewer.user_id)))


def test_user_referenced_by_a_run_cannot_be_deleted(db):
    starter = user(db)
    run(db, started_by_user=starter)
    violates(db, "fk_pipeline_run_started_by_app_user",
             lambda: db.execute(delete(AppUser).where(AppUser.user_id == starter.user_id)))


def test_user_referenced_by_a_setting_cannot_be_deleted(db):
    admin = user(db, role=UserRole.ADMIN)
    db.get(AppSetting, "lead_threshold").updated_by = admin.user_id
    db.flush()
    violates(db, "fk_app_setting_updated_by_app_user",
             lambda: db.execute(delete(AppUser).where(AppUser.user_id == admin.user_id)))


# ---------- pipeline_run (Q5) ----------

@pytest.mark.parametrize("column", ["jobs_fetched", "jobs_new", "jobs_updated"])
def test_run_counters_are_not_negative(db, column):
    violates(db, f"ck_pipeline_run_{column}_non_negative", lambda: run(db, **{column: -1}))


def test_run_counters_default_to_zero(db):
    rn = run(db)
    db.refresh(rn)
    assert (rn.jobs_fetched, rn.jobs_new, rn.jobs_updated) == (0, 0, 0)
    assert rn.started_by is None and rn.errors is None


def test_only_one_run_can_be_running(db):
    run(db, status=RunStatus.RUNNING)
    violates(db, "uq_pipeline_run_one_running", lambda: run(db, status=RunStatus.RUNNING))


def test_many_finished_runs_are_allowed(db):
    run(db, status=RunStatus.RUNNING)
    run(db, status=RunStatus.COMPLETED)
    run(db, status=RunStatus.COMPLETED)
    run(db, status=RunStatus.FAILED)
    assert count(db, PipelineRun) == 4


def test_run_with_history_cannot_be_deleted(db):
    snap = snapshot(db)
    violates(db, "fk_lead_snapshot_run_id_pipeline_run",
             lambda: db.execute(delete(PipelineRun).where(PipelineRun.run_id == snap.run_id)))


# ---------- app_setting ----------

def test_default_settings_are_seeded(db):
    rows = {s.key: s.value for s in db.scalars(select(AppSetting))}
    assert rows == {"lead_threshold": "60", "fetch_limit": "100", "himalayas_enabled": "true",
                    "remotive_enabled": "true", "run_mode": "manual", "max_retries": "3"}


def test_seeded_settings_match_the_pydantic_defaults(db):
    from backend.schemas import AppSettings
    rows = {s.key: s.value for s in db.scalars(select(AppSetting))}
    assert rows == dict(AppSettings().to_rows())
    assert AppSettings.from_rows(rows) == AppSettings()


# ---------- company (Q2) ----------

def test_normalized_name_is_unique(db):
    company(db)
    violates(db, "uq_company_normalized_name", lambda: company(db))


@pytest.mark.parametrize("variant", ["ACME  corp", " acme corp ", "Acme\tCorp"])
def test_company_name_variants_are_one_company(db, variant):
    company(db)
    violates(db, "uq_company_normalized_name", lambda: company(db, variant))


def test_company_with_legal_suffix_is_another_company(db):
    company(db)
    company(db, "Acme Corp Inc.")
    assert count(db, Company) == 2


def test_same_display_name_is_not_unique(db):
    """``name`` is the source's spelling; only normalized_name is unique."""
    db.add_all([Company(name="Acme Corp", normalized_name="acme corp"),
                Company(name="Acme Corp", normalized_name="acme corp (uk)")])
    db.flush()


@pytest.mark.parametrize("name", [
    "Acme Corp", "ACME  corp", "  acme corp ", "Acme\tCorp\n", "Acme Corp Inc.",
    "Acme, Ltd.", "  Helix   AI  ", "Orbit\r\nTech",
])
def test_company_name_key_matches_the_contract_rule_in_sql(db, name):
    sql = db.scalar(text(r"SELECT lower(btrim(regexp_replace(:n, '\s+', ' ', 'g')))"), {"n": name})
    assert company_name_key(name) == sql


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


def test_expires_and_updated_at_are_stored(db):
    expires, updated = NOW + timedelta(days=30), NOW + timedelta(days=1)
    jp = job(db, expires_at=expires, updated_at=updated)
    db.expunge_all()
    jp = db.get(JobPosting, jp.job_id)
    assert (jp.expires_at, jp.updated_at) == (expires, updated)


def test_run_with_jobs_cannot_be_deleted(db):
    jp = job(db, run=run(db))
    violates(db, "fk_job_posting_run_id_pipeline_run",
             lambda: db.execute(delete(PipelineRun).where(PipelineRun.run_id == jp.run_id)))


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
    ("job_requirement", "remote_policy"), ("job_requirement", "salary_period"),
    ("job_requirement", "extraction_status"), ("candidate", "seniority"), ("lead", "status"),
    ("lead_snapshot", "status"), ("outreach_draft", "status"), ("pipeline_run", "status"),
    ("pipeline_run", "trigger_type"), ("app_user", "role"),
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
    requirement(db, fit_score=None, fit_reason=None, source_hash=None)


def test_source_hash_must_be_64_characters(db):
    violates(db, "ck_job_requirement_source_hash_length", lambda: requirement(db, source_hash="9f2c"))


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
    assert count(db, JobRequirement) == 0


# ---------- candidate ----------

def test_candidate_years_experience_is_not_negative(db):
    violates(db, "ck_candidate_years_experience_non_negative",
             lambda: candidate(db, years_experience=Decimal("-1")))


def test_candidate_skills_are_lowercase(db):
    violates(db, "ck_candidate_skills_lowercase", lambda: candidate(db, skills=["React"]))


# ---------- lead ----------

def test_lead_reason_is_not_empty(db):
    violates(db, "ck_lead_reason_not_empty", lambda: lead(db, reason=""))


@pytest.mark.parametrize("score", [-1, 101])
def test_lead_score_range(db, score):
    violates(db, "ck_lead_lead_score_range", lambda: lead(db, lead_score=score))


@pytest.mark.parametrize("score", [-1, 101])
def test_best_job_score_range(db, score):
    violates(db, "ck_lead_best_job_score_range", lambda: lead(db, best_job_score=score))


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
    lead(db, status=LeadStatus.NOT_QUALIFIED, qualifying_jobs=0, lead_score=0, best_job_score=0,
         evidence={"job_ids": []})


@pytest.mark.parametrize("evidence", [{}, {"jobs": [12]}, {"job_ids": 12}, {"job_ids": None}])
def test_lead_evidence_has_a_job_ids_array(db, evidence):
    violates(db, "ck_lead_evidence_has_job_ids", lambda: lead(db, evidence=evidence))


def test_one_lead_per_company(db):
    comp = company(db)
    lead(db, comp)
    violates(db, "uq_lead_company_id", lambda: lead(db, comp))


def test_deleting_a_company_deletes_its_lead_drafts_and_snapshots(db):
    dr = draft(db)
    snapshot(db, dr.lead)
    db.execute(delete(Company).where(Company.company_id == dr.lead.company_id))
    assert count(db, Lead) == count(db, OutreachDraft) == count(db, LeadSnapshot) == 0


# ---------- lead_snapshot ----------

def test_one_snapshot_per_lead_per_run(db):
    snap = snapshot(db)
    violates(db, "uq_lead_snapshot_lead_id_run_id", lambda: snapshot(db, snap.lead, snap.run))


def test_same_lead_in_another_run_is_allowed(db):
    snap = snapshot(db)
    snapshot(db, snap.lead, run(db))
    assert count(db, LeadSnapshot) == 2


@pytest.mark.parametrize("column", ["lead_score", "best_job_score"])
def test_snapshot_scores_are_in_range(db, column):
    violates(db, f"ck_lead_snapshot_{column}_range", lambda: snapshot(db, **{column: 101}))


def test_deleting_a_lead_deletes_its_snapshots(db):
    snap = snapshot(db)
    db.execute(delete(Lead).where(Lead.lead_id == snap.lead_id))
    assert count(db, LeadSnapshot) == 0


# ---------- outreach_draft ----------

def test_draft_version_is_at_least_one(db):
    violates(db, "ck_outreach_draft_version_positive", lambda: draft(db, version=0))


def test_draft_word_count_is_not_negative(db):
    violates(db, "ck_outreach_draft_word_count_non_negative", lambda: draft(db, word_count=-1))


def test_reviewer_needs_a_review_time(db):
    reviewer = user(db)
    violates(db, "ck_outreach_draft_review_complete", lambda: draft(db, reviewer=reviewer))


def test_review_time_needs_a_reviewer(db):
    violates(db, "ck_outreach_draft_review_complete", lambda: draft(db, reviewed_at=NOW))


def test_reviewer_must_be_a_user(db):
    violates(db, "fk_outreach_draft_reviewed_by_app_user",
             lambda: draft(db, reviewed_by=999_999, reviewed_at=NOW))


def test_word_range_is_not_enforced_by_the_database(db):
    """120-180 words is checked by Pydantic, so a reviewer's short edit still saves."""
    draft(db, status=DraftStatus.EDITED, body="Short edit.", word_count=2,
          reviewer=user(db), reviewed_at=NOW)


def test_deleting_a_lead_deletes_its_drafts(db):
    dr = draft(db)
    draft(db, dr.lead, version=2)
    db.execute(delete(Lead).where(Lead.lead_id == dr.lead_id))
    assert count(db, OutreachDraft) == 0
