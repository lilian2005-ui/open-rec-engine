"""P2-3: two requests on the same lead at the same time, each with its own session
and connection (like two reviewers). Runs on the test database (``engine`` of
conftest.py). The rows are committed, because the second session must see them,
so every test deletes what it created at the end.

How a test works: session A takes the lead lock and keeps it; request B starts in
a thread; the test asks PostgreSQL (pg_blocking_pids) until B is really waiting on
A's lock, and only then lets A commit. So B always reads after A's change, and
without the lock B would not wait and the test fails. No fixed sleep decides it.
"""
import threading
import time
import uuid
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from backend.api.routes.drafts import _decide, _reviewable, approve_draft
from backend.db.models import (AppUser, Company, JobPosting, JobRequirement, Lead,
                               OutreachDraft)
from backend.db.models.enums import DraftStatus, LeadStatus, UserRole
from backend.drafts.service import CannotRegenerate, regenerate_draft
from backend.llm import FakeLLM
from backend.tests.test_drafts_service import answer
from backend.tests.test_drafts_service import make_lead as make_scored_lead

TIMEOUT = 10        # seconds; waiting longer than this means B never got there


@pytest.fixture
def world(engine):
    """A reviewer and a draft_ready lead with draft version 1, committed."""
    name = f"Lock Test {uuid.uuid4().hex[:8]}"
    with Session(engine, expire_on_commit=False) as db:
        user = AppUser(full_name="Reviewer", email=f"{uuid.uuid4().hex[:8]}@example.com",
                       password_hash="$2b$12$" + "x" * 53, role=UserRole.REVIEWER)
        db.add(user)
        lead = make_scored_lead(db, name=name, status=LeadStatus.DRAFT_READY)
        draft = OutreachDraft(lead=lead, subject="Subject v1",
                              body=answer(start=f"Hello {name} team,")["body"],
                              word_count=150, version=1, status=DraftStatus.PENDING_REVIEW)
        db.add(draft)
        db.commit()
        ids = {"user": user.user_id, "lead": lead.lead_id, "draft": draft.draft_id,
               "company": lead.company_id, "name": name}
    yield ids
    with Session(engine) as db:
        job_ids = [j for j, in db.query(JobPosting.job_id)
                   .filter(JobPosting.company_id == ids["company"])]
        db.execute(delete(OutreachDraft).where(OutreachDraft.lead_id == ids["lead"]))
        db.execute(delete(Lead).where(Lead.lead_id == ids["lead"]))
        db.execute(delete(JobRequirement).where(JobRequirement.job_id.in_(job_ids)))
        db.execute(delete(JobPosting).where(JobPosting.job_id.in_(job_ids)))
        db.execute(delete(Company).where(Company.company_id == ids["company"]))
        db.execute(delete(AppUser).where(AppUser.user_id == ids["user"]))
        db.commit()


def backend_pid(db: Session) -> int:
    """The PostgreSQL connection of this session (it keeps it for the transaction)."""
    return db.execute(text("select pg_backend_pid()")).scalar()


@contextmanager
def b_waits_for(engine, a: Session, work):
    """Start ``work(session)`` in a thread with its own session, and return only
    once that session is blocked by session A's lock. Yields a dict that gets
    ``result`` or ``error`` when B ends (after the ``with`` block)."""
    a_pid = backend_pid(a)
    out: dict = {}
    started = threading.Event()

    def target():
        with Session(engine, expire_on_commit=False) as db:
            out["pid"] = backend_pid(db)
            started.set()
            try:
                out["result"] = work(db)
            except Exception as exc:  # the test checks which one it was
                out["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    try:
        assert started.wait(TIMEOUT), "B did not start"
        deadline = time.monotonic() + TIMEOUT
        with engine.connect() as watcher:
            while a_pid not in watcher.execute(text("select pg_blocking_pids(:pid)"),
                                               {"pid": out["pid"]}).scalar():
                assert thread.is_alive(), f"B finished without waiting for A's lock: {out}"
                assert time.monotonic() < deadline, "B never waited for A's lock"
                time.sleep(0.01)                 # poll again; not a fixed wait
        yield out
    finally:
        thread.join(TIMEOUT)
        assert not thread.is_alive(), "B never finished (deadlock?)"


def read(engine, ids):
    with Session(engine) as db:
        lead = db.get(Lead, ids["lead"])
        drafts = sorted((d.version, d.status) for d in lead.drafts)
        return lead.status, drafts


def test_two_decisions_at_the_same_time_only_the_first_wins(engine, world):
    with Session(engine, expire_on_commit=False) as a:
        user = a.get(AppUser, world["user"])
        draft = _reviewable(a, world["draft"])                  # A holds the lock

        def b_approves(db):
            return approve_draft(world["draft"], db=db, user=db.get(AppUser, world["user"]))

        with b_waits_for(engine, a, b_approves) as out:
            draft.review_comment = "Too generic"
            _decide(a, draft, user, DraftStatus.REJECTED, LeadStatus.REJECTED)   # A commits

    assert isinstance(out.get("error"), HTTPException), out
    assert (out["error"].status_code, out["error"].detail) == (409, "This draft is already decided")
    assert read(engine, world) == (LeadStatus.REJECTED, [(1, DraftStatus.REJECTED)])


def test_a_decision_waits_for_a_new_version_and_then_refuses_the_old_one(engine, world):
    with Session(engine, expire_on_commit=False) as a:
        # A saves version 2 the way save_draft does: lead locked, row added, commit
        _reviewable(a, world["draft"])
        lead = a.get(Lead, world["lead"])
        a.add(OutreachDraft(lead=lead, subject="Subject v2", body="New text", word_count=2,
                            version=2, status=DraftStatus.PENDING_REVIEW))
        a.flush()

        def b_approves_v1(db):
            return approve_draft(world["draft"], db=db, user=db.get(AppUser, world["user"]))

        with b_waits_for(engine, a, b_approves_v1) as out:
            a.commit()

    assert isinstance(out.get("error"), HTTPException), out
    assert (out["error"].status_code, out["error"].detail) == (
        409, "Only the latest draft version can be reviewed")
    assert read(engine, world) == (LeadStatus.DRAFT_READY,
                                   [(1, DraftStatus.PENDING_REVIEW), (2, DraftStatus.PENDING_REVIEW)])


def test_regenerate_does_not_overwrite_an_approval_made_while_the_llm_wrote(engine, world):
    """Regenerate checks the status before the LLM call; an approval can land during
    that call. The service must check again under the lock."""
    fake = FakeLLM(answer(start=f"Hello {world['name']} team,"))

    with Session(engine, expire_on_commit=False) as a:
        user = a.get(AppUser, world["user"])
        draft = _reviewable(a, world["draft"])                  # A holds the lock

        def b_regenerates(db):
            return regenerate_draft(db, world["lead"], call=fake)

        with b_waits_for(engine, a, b_regenerates) as out:
            assert fake.calls == 1, "B waits after the LLM call, just before saving"
            _decide(a, draft, user, DraftStatus.APPROVED, LeadStatus.APPROVED)   # A commits

    assert isinstance(out.get("error"), CannotRegenerate), out
    assert str(out["error"]) == "This draft is already approved"
    assert read(engine, world) == (LeadStatus.APPROVED, [(1, DraftStatus.APPROVED)])
