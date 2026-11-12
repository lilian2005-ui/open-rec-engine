"""P1-5: lead scoring per company. Runs on real PostgreSQL (the ``db`` fixture
rolls everything back after each test) with FakeLLM (no network)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.db.models import (AppSetting, Company, JobPosting, JobRequirement, Lead,
                               LeadSnapshot, PipelineRun)
from backend.db.models.enums import (ExtractionStatus, JobStatus, LeadStatus, RunStatus, Source,
                                     TriggerType)
from backend.db.normalize import company_name_key, content_hash
from backend.leads.reason import NOT_QUALIFIED_REASON, NOT_SCORED_REASON
from backend.leads.service import score_leads
from backend.llm import FakeLLM

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
TEXT = "Job description..."


# ---------- builders ----------

def make_run(db):
    # completed: the database allows only one running run at a time
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED,
                      started_at=NOW, finished_at=NOW)
    db.add(run)
    db.flush()
    return run.run_id


def make_company(db, name="Acme Corp"):
    comp = Company(name=name, normalized_name=company_name_key(name))
    db.add(comp)
    db.flush()
    return comp


_n = 0


def make_job(db, company, fit_score, status=JobStatus.SCORED, expires_at=None, title=None):
    global _n
    _n += 1
    title = title or f"Job {_n}"
    job = JobPosting(
        company=company, source=Source.HIMALAYAS, external_id=f"job-{_n}",
        url=f"https://himalayas.app/jobs/{_n}", title=title, description_text=TEXT,
        content_hash=content_hash(title, TEXT), status=status, expires_at=expires_at,
    )
    db.add(job)
    db.flush()
    db.add(JobRequirement(
        job_posting=job, source_hash=job.content_hash, title=title,
        required_skills=["react"], extraction_status=ExtractionStatus.OK,
        fit_score=fit_score, fit_reason=f"reason {fit_score}" if fit_score is not None else None,
    ))
    db.flush()
    return job


def reasons(n):
    """n valid LLM answers."""
    return FakeLLM(*[{"reason": f"LLM reason {i}"} for i in range(n)])


def lead_of(db, company):
    return db.scalar(select(Lead).where(Lead.company_id == company.company_id))


# ---------- the score ----------

def test_one_job_of_95_gives_95(db):
    acme = make_company(db)
    job = make_job(db, acme, 95)

    result = score_leads(db, make_run(db), call=reasons(1), now=NOW)

    lead = lead_of(db, acme)
    assert (lead.lead_score, lead.best_job_score, lead.qualifying_jobs) == (95, 95, 1)
    assert lead.status == LeadStatus.QUALIFIED
    assert lead.evidence == {"job_ids": [job.job_id]}
    assert lead.reason == "LLM reason 0"
    assert lead.scored_at == NOW
    assert (result.qualified, result.not_qualified, result.failed) == (1, 0, 0)


def test_jobs_65_63_62_give_75(db):
    acme = make_company(db)
    for s in (65, 63, 62):
        make_job(db, acme, s)

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    lead = lead_of(db, acme)
    assert (lead.lead_score, lead.best_job_score, lead.qualifying_jobs) == (75, 65, 3)


def test_guide_example_four_companies(db):
    acme, helix, orbit, brightly = (make_company(db, n) for n in
                                    ("Acme Corp", "Helix AI", "Orbit Tech", "Brightly"))
    make_job(db, acme, 92); make_job(db, acme, 78)
    make_job(db, helix, 81); make_job(db, helix, 65); make_job(db, helix, 20)
    make_job(db, orbit, 74)
    make_job(db, brightly, 45)

    score_leads(db, make_run(db), call=reasons(3), now=NOW)

    got = {c.name: (lead_of(db, c).lead_score, lead_of(db, c).status)
           for c in (acme, helix, orbit, brightly)}
    assert got == {
        "Acme Corp": (97, LeadStatus.QUALIFIED),
        "Helix AI": (86, LeadStatus.QUALIFIED),
        "Orbit Tech": (74, LeadStatus.QUALIFIED),
        "Brightly": (0, LeadStatus.NOT_QUALIFIED),
    }


def test_score_is_capped_at_100(db):
    acme = make_company(db)
    for s in (98, 90, 90, 90):
        make_job(db, acme, s)

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    assert lead_of(db, acme).lead_score == 100


# ---------- which jobs count ----------

def test_expired_job_does_not_count(db):
    acme = make_company(db)
    make_job(db, acme, 70, expires_at=NOW - timedelta(days=1))
    fake = reasons(0)

    score_leads(db, make_run(db), call=fake, now=NOW)

    lead = lead_of(db, acme)
    assert (lead.lead_score, lead.qualifying_jobs) == (0, 0)
    assert lead.status == LeadStatus.NOT_QUALIFIED
    assert lead.reason == NOT_QUALIFIED_REASON
    assert fake.calls == 0                          # no LLM for a not qualified company


def test_job_expiring_later_counts(db):
    acme = make_company(db)
    make_job(db, acme, 70, expires_at=NOW + timedelta(days=1))

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    assert lead_of(db, acme).lead_score == 70


def test_parsed_job_does_not_count(db):
    acme = make_company(db)
    make_job(db, acme, None, status=JobStatus.PARSED)
    make_job(db, acme, 90, status=JobStatus.DISCOVERED)   # changed posting, waits to be re-scored

    score_leads(db, make_run(db), call=reasons(0), now=NOW)

    assert lead_of(db, acme).status == LeadStatus.NOT_QUALIFIED


def test_score_exactly_at_threshold_counts(db):
    acme = make_company(db)
    make_job(db, acme, 60)
    make_job(db, acme, 59)

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    assert (lead_of(db, acme).lead_score, lead_of(db, acme).qualifying_jobs) == (60, 1)


def test_raising_the_threshold_to_80_qualifies_fewer_companies(db):
    acme, helix = make_company(db, "Acme Corp"), make_company(db, "Helix AI")
    make_job(db, acme, 92)
    make_job(db, helix, 75)
    db.get(AppSetting, "lead_threshold").value = "80"
    db.flush()

    result = score_leads(db, make_run(db), call=reasons(1), now=NOW)

    assert lead_of(db, acme).status == LeadStatus.QUALIFIED
    assert lead_of(db, helix).status == LeadStatus.NOT_QUALIFIED
    assert (result.qualified, result.not_qualified) == (1, 1)


def test_prompt_holds_only_the_suitable_jobs(db):
    acme = make_company(db)
    make_job(db, acme, 92, title="Senior React Developer")
    make_job(db, acme, 20, title="Office Manager")
    fake = reasons(1)

    score_leads(db, make_run(db), call=fake, now=NOW)

    assert "Senior React Developer" in fake.prompts[0]
    assert "Office Manager" not in fake.prompts[0]


# ---------- history and re-runs ----------

def test_two_runs_give_one_lead_and_two_snapshots(db):
    acme = make_company(db)
    make_job(db, acme, 80)
    run1, run2 = make_run(db), make_run(db)

    score_leads(db, run1, call=reasons(1), now=NOW)
    score_leads(db, run2, call=reasons(1), now=NOW)

    lead = lead_of(db, acme)
    assert db.scalar(select(func.count()).select_from(Lead)) == 1
    snaps = db.scalars(select(LeadSnapshot).where(LeadSnapshot.lead_id == lead.lead_id)
                       .order_by(LeadSnapshot.run_id)).all()
    assert [s.run_id for s in snaps] == [run1, run2]
    assert all(s.lead_score == 80 and s.status == LeadStatus.QUALIFIED for s in snaps)
    assert lead.run_id == run2


def test_same_run_twice_keeps_one_snapshot(db):
    acme = make_company(db)
    make_job(db, acme, 80)
    run = make_run(db)

    score_leads(db, run, call=reasons(1), now=NOW)
    score_leads(db, run, call=reasons(1), now=NOW)

    assert db.scalar(select(func.count()).select_from(LeadSnapshot)) == 1


def test_lead_is_updated_when_scores_change(db):
    acme = make_company(db)
    job = make_job(db, acme, 90)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    job.requirement.fit_score, job.requirement.fit_reason = 40, "now weak"
    db.flush()
    score_leads(db, make_run(db), call=reasons(0), now=NOW)

    lead = lead_of(db, acme)
    assert (lead.lead_score, lead.status, lead.evidence) == (
        0, LeadStatus.NOT_QUALIFIED, {"job_ids": []})


# ---------- status of reviewed leads (open decision: keep it) ----------

def test_approved_lead_stays_approved_when_its_score_changes(db):
    acme = make_company(db)
    make_job(db, acme, 70)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)
    lead_of(db, acme).status = LeadStatus.APPROVED
    db.flush()
    make_job(db, acme, 90)

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    lead = lead_of(db, acme)
    assert lead.status == LeadStatus.APPROVED
    assert lead.lead_score == 95


def test_approved_lead_with_no_suitable_job_becomes_not_qualified(db):
    acme = make_company(db)
    job = make_job(db, acme, 70)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)
    lead_of(db, acme).status = LeadStatus.APPROVED
    job.expires_at = NOW - timedelta(hours=1)
    db.flush()

    score_leads(db, make_run(db), call=reasons(0), now=NOW)

    assert lead_of(db, acme).status == LeadStatus.NOT_QUALIFIED


def test_not_qualified_lead_becomes_qualified_again(db):
    acme = make_company(db)
    make_job(db, acme, 40)
    score_leads(db, make_run(db), call=reasons(0), now=NOW)
    make_job(db, acme, 85)

    score_leads(db, make_run(db), call=reasons(1), now=NOW)

    assert lead_of(db, acme).status == LeadStatus.QUALIFIED


# ---------- failures ----------

def test_llm_failure_saves_the_fallback_reason_and_the_run_continues(db):
    acme, helix = make_company(db, "Acme Corp"), make_company(db, "Helix AI")
    make_job(db, acme, 92); make_job(db, acme, 78)
    make_job(db, helix, 81)
    # Acme: 4 broken answers (all attempts fail). Helix: a valid answer.
    fake = FakeLLM("not json", "not json", "not json", "not json", {"reason": "Helix reason"})

    result = score_leads(db, make_run(db), call=fake, now=NOW)

    assert lead_of(db, acme).reason == (
        "2 suitable jobs; the best fit score is 92, which gives a lead score of 97.")
    assert lead_of(db, helix).reason == "Helix reason"
    assert (result.qualified, result.fallback_reasons, result.failed) == (2, 1, 0)


def test_company_with_no_scored_job_gets_the_not_scored_reason(db):
    acme = make_company(db)
    make_job(db, acme, None, status=JobStatus.NEEDS_REVIEW)
    make_job(db, acme, None, status=JobStatus.PARSED)

    score_leads(db, make_run(db), call=reasons(0), now=NOW)

    lead = lead_of(db, acme)
    assert lead.status == LeadStatus.NOT_QUALIFIED
    assert lead.reason == NOT_SCORED_REASON


def test_company_with_a_low_scored_job_keeps_the_below_threshold_reason(db):
    acme = make_company(db)
    make_job(db, acme, 30)
    make_job(db, acme, None, status=JobStatus.PARSED)

    score_leads(db, make_run(db), call=reasons(0), now=NOW)

    assert lead_of(db, acme).reason == NOT_QUALIFIED_REASON


# ---------- reason reuse (no LLM call when nothing changed) ----------

LATER = NOW + timedelta(days=1)


def test_unchanged_company_reuses_the_last_reason_without_calling_the_llm(db):
    acme = make_company(db)
    make_job(db, acme, 92); make_job(db, acme, 78)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)
    fake = reasons(0)                    # any call would fail the test

    run2 = make_run(db)
    result = score_leads(db, run2, call=fake, now=LATER)

    lead = lead_of(db, acme)
    assert fake.calls == 0
    assert lead.reason == "LLM reason 0"
    assert (lead.lead_score, lead.run_id, lead.scored_at) == (97, run2, LATER)
    assert result.reused_reasons == 1
    assert db.scalar(select(func.count()).select_from(LeadSnapshot)) == 2   # history still saved


def test_new_suitable_job_asks_the_llm_again(db):
    acme = make_company(db)
    make_job(db, acme, 92)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)
    make_job(db, acme, 80)
    fake = FakeLLM({"reason": "new reason"})

    result = score_leads(db, make_run(db), call=fake, now=LATER)

    assert fake.calls == 1
    assert lead_of(db, acme).reason == "new reason"
    assert result.reused_reasons == 0


def test_rescored_job_with_the_same_lead_score_asks_the_llm_again(db):
    # 92 + 78 -> 97, then 92 + 80 -> still 97: the old reason says 78, so it is stale
    acme = make_company(db)
    make_job(db, acme, 92)
    job = make_job(db, acme, 78)
    score_leads(db, make_run(db), call=reasons(1), now=NOW)
    job.requirement.fit_score, job.requirement.fit_reason = 80, "re-scored"
    job.updated_at = NOW + timedelta(hours=1)          # the posting changed (Q1)
    db.flush()
    fake = FakeLLM({"reason": "fresh reason"})

    score_leads(db, make_run(db), call=fake, now=LATER)

    lead = lead_of(db, acme)
    assert lead.lead_score == 97
    assert fake.calls == 1
    assert lead.reason == "fresh reason"


def test_fallback_reason_is_not_reused_the_llm_is_tried_again(db):
    acme = make_company(db)
    make_job(db, acme, 92)
    score_leads(db, make_run(db), call=FakeLLM(*["not json"] * 4), now=NOW)
    fake = FakeLLM({"reason": "real reason"})

    score_leads(db, make_run(db), call=fake, now=LATER)

    assert fake.calls == 1
    assert lead_of(db, acme).reason == "real reason"


def test_company_without_jobs_gets_no_lead(db):
    make_company(db, "Empty Co")

    result = score_leads(db, make_run(db), call=reasons(0), now=NOW)

    assert db.scalar(select(func.count()).select_from(Lead)) == 0
    assert (result.qualified, result.not_qualified) == (0, 0)
