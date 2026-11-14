"""P2-1: outreach drafts for qualified leads. Runs on real PostgreSQL (the ``db``
fixture rolls everything back after each test) with FakeLLM (no network)."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from backend.db.models import (Candidate, Company, JobPosting, JobRequirement, Lead,
                               OutreachDraft)
from backend.db.models.enums import (DraftStatus, ExtractionStatus, JobStatus, LeadStatus,
                                     Seniority, Source)
from backend.db.normalize import company_name_key, content_hash
from backend.drafts.service import create_drafts
from backend.llm import FakeLLM

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
TEXT = "Job description..."


# ---------- builders ----------

_n = 0


def make_lead(db, name="Acme Corp", scores=(92,), status=LeadStatus.QUALIFIED,
              contact_name=None, contact_email=None, title="Senior React Developer"):
    """A company, its scored jobs and its lead (as P1-5 would save them)."""
    global _n
    comp = Company(name=name, normalized_name=company_name_key(name),
                   contact_name=contact_name, contact_title="CTO" if contact_name else None,
                   contact_email=contact_email)
    db.add(comp)
    db.flush()
    job_ids = []
    for s in scores:
        _n += 1
        t = title if not job_ids else f"{title} {_n}"
        job = JobPosting(company=comp, source=Source.HIMALAYAS, external_id=f"d-{_n}",
                         url=f"https://himalayas.app/jobs/d-{_n}", title=t,
                         description_text=TEXT, content_hash=content_hash(t, TEXT),
                         status=JobStatus.SCORED)
        db.add(job)
        db.flush()
        db.add(JobRequirement(job_posting=job, source_hash=job.content_hash, title=t,
                              extraction_status=ExtractionStatus.OK,
                              fit_score=s, fit_reason=f"{t}: 3 profiles cover it"))
        job_ids.append(job.job_id)
    qualified = status != LeadStatus.NOT_QUALIFIED
    lead = Lead(company=comp, lead_score=max(scores) if qualified else 0,
                best_job_score=max(scores) if qualified else 0,
                qualifying_jobs=len(job_ids) if qualified else 0, status=status,
                reason="reason", evidence={"job_ids": job_ids if qualified else []},
                scored_at=NOW)
    db.add(lead)
    db.flush()
    return lead


def make_candidate(db, name="Candidate 101"):
    db.add(Candidate(candidate_id=int(name.split()[-1]), display_name=name, skills=["react"],
                     years_experience=Decimal("6"), seniority=Seniority.SENIOR,
                     timezone_offsets=[-5]))
    db.flush()


def body(start="Hello Acme Corp team,", role="Senior React Developer", extra="", words=150):
    text = f"{start}\nI noticed you are hiring a {role}. {extra}".strip()
    closing = "Would you be open to a call?"
    text += " " + " ".join(["talent"] * (words - len(text.split()) - len(closing.split())))
    return f"{text} {closing}"


def answer(**kw):
    return {"subject": "React talent for your team", "body": body(**kw)}


def drafts_of(db, lead):
    return db.scalars(select(OutreachDraft).where(OutreachDraft.lead_id == lead.lead_id)).all()


# ---------- tests ----------

def test_qualified_lead_gets_a_pending_draft_and_becomes_draft_ready(db):
    lead = make_lead(db)
    fake = FakeLLM(answer())

    result = create_drafts(db, call=fake)

    [draft] = drafts_of(db, lead)
    assert (draft.version, draft.status) == (1, DraftStatus.PENDING_REVIEW)
    assert draft.word_count == 150 and draft.body.startswith("Hello Acme Corp team")
    assert (draft.reviewed_by, draft.reviewed_at) == (None, None)
    assert lead.status == LeadStatus.DRAFT_READY
    assert (result.created, result.failed) == (1, 0)


def test_draft_ready_lead_gets_no_new_draft(db):
    lead = make_lead(db)
    create_drafts(db, call=FakeLLM(answer()))
    fake = FakeLLM()                            # any call would fail the test

    result = create_drafts(db, call=fake)

    assert lead.status == LeadStatus.DRAFT_READY
    assert fake.calls == 0 and len(drafts_of(db, lead)) == 1
    assert result.created == 0


def test_lead_that_came_back_qualified_gets_version_2(db):
    # draft_ready -> not_qualified (jobs expired) -> qualified (a new job), by P1-5
    lead = make_lead(db)
    create_drafts(db, call=FakeLLM(answer()))
    lead.status = LeadStatus.QUALIFIED
    db.flush()

    result = create_drafts(db, call=FakeLLM(answer()))

    drafts = sorted(drafts_of(db, lead), key=lambda d: d.version)
    assert [d.version for d in drafts] == [1, 2]
    assert all(d.status == DraftStatus.PENDING_REVIEW for d in drafts)
    assert lead.status == LeadStatus.DRAFT_READY and result.created == 1


def test_not_qualified_and_reviewed_leads_get_no_draft(db):
    make_lead(db, "Brightly", status=LeadStatus.NOT_QUALIFIED)
    make_lead(db, "Helix AI", status=LeadStatus.APPROVED)
    fake = FakeLLM()

    create_drafts(db, call=fake)

    assert fake.calls == 0
    assert db.scalar(select(func.count()).select_from(OutreachDraft)) == 0


def test_prompt_has_the_suitable_roles_and_no_contact(db):
    make_lead(db, scores=(92, 78))
    fake = FakeLLM(answer())

    create_drafts(db, call=fake)

    prompt = fake.prompts[0]
    assert "Senior React Developer" in prompt and "3 profiles cover it" in prompt
    assert "CONTACT: null" in prompt


def test_contact_first_name_is_used_and_the_email_never_reaches_the_llm(db):
    lead = make_lead(db, contact_name="Sara Haddad", contact_email="sara@acme.com")
    fake = FakeLLM(answer(start="Hi Sara,"))

    create_drafts(db, call=fake)

    assert '"name": "Sara Haddad"' in fake.prompts[0]
    assert "sara@acme.com" not in fake.prompts[0]
    assert drafts_of(db, lead)[0].body.startswith("Hi Sara,")


def test_wrong_greeting_is_rejected_and_asked_again(db):
    lead = make_lead(db)
    fake = FakeLLM(answer(start="Dear hiring manager,"), answer())

    create_drafts(db, call=fake)

    assert fake.calls == 2
    assert drafts_of(db, lead)[0].body.startswith("Hello Acme Corp team")
    # the second prompt tells the LLM why the first draft was rejected
    assert "REJECTED" not in fake.prompts[0]
    assert 'REJECTED because it does not start with "Hello Acme Corp team"' in fake.prompts[1]


def test_draft_of_90_words_is_rejected_and_asked_again(db):
    lead = make_lead(db)
    fake = FakeLLM(answer(words=90), answer())

    create_drafts(db, call=fake)

    assert fake.calls == 2
    assert drafts_of(db, lead)[0].word_count == 150


def test_draft_with_link_price_candidate_or_no_role_is_rejected_and_asked_again(db):
    make_candidate(db, "Candidate 101")
    lead = make_lead(db)
    fake = FakeLLM(answer(extra="See https://simera.com."), answer(extra="Only $40."),
                   answer(extra="Candidate 101 fits."), answer())

    result = create_drafts(db, call=fake)

    # 1 + 2 retries = 3 tries: the 4th (good) answer is never asked for
    assert fake.calls == 3
    assert drafts_of(db, lead) == []
    assert lead.status == LeadStatus.QUALIFIED
    assert "names a candidate" in result.errors[0]


def test_draft_that_mentions_no_role_is_rejected(db):
    lead = make_lead(db)
    fake = FakeLLM(answer(role="engineer"), answer())

    create_drafts(db, call=fake)

    assert fake.calls == 2 and len(drafts_of(db, lead)) == 1


def test_llm_always_failing_leaves_the_lead_qualified_and_others_continue(db):
    acme = make_lead(db, "Acme Corp", scores=(97,))
    helix = make_lead(db, "Helix AI", scores=(86,))
    # Acme first (higher score): 4 broken answers. Then Helix: a good one.
    fake = FakeLLM("not json", "not json", "not json", "not json",
                   answer(start="Hello Helix AI team,"))

    result = create_drafts(db, call=fake)

    assert acme.status == LeadStatus.QUALIFIED and drafts_of(db, acme) == []
    assert helix.status == LeadStatus.DRAFT_READY and len(drafts_of(db, helix)) == 1
    assert (result.created, result.failed) == (1, 1)
    assert "Acme Corp" in result.errors[0]


def test_limit_takes_only_the_best_leads(db):
    make_lead(db, "Low Co", scores=(65,))
    best = make_lead(db, "Acme Corp", scores=(95,))
    fake = FakeLLM(answer())

    result = create_drafts(db, call=fake, limit=1)

    assert result.created == 1 and fake.calls == 1
    assert best.status == LeadStatus.DRAFT_READY
