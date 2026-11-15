"""P2-3: GET /leads, GET /leads/{lead_id}, PATCH /leads/{lead_id}/contact.
Real PostgreSQL (``db`` of conftest.py)."""
from datetime import timedelta

from backend.db.models.enums import DraftStatus, LeadStatus
from backend.tests.api_fixtures import (NOW, client, make_draft, make_job, make_lead,  # noqa: F401
                                        make_snapshot, reviewer)


def names(response) -> list[str]:
    return [item["company_name"] for item in response.json()["items"]]


# ---------- list ----------

def test_list_has_the_contract_shape(client, reviewer, db):
    lead = make_lead(db, "Acme Corp", scores=(92, 78))

    response = client.get("/leads")

    assert response.status_code == 200
    assert response.json() == {
        "items": [{
            "lead_id": lead.lead_id,
            "company_name": "Acme Corp",
            "lead_score": 97,
            "best_job_score": 92,
            "qualifying_jobs": 2,
            "status": "qualified",
            "reason": "Acme Corp has 2 suitable role(s).",
        }],
        "total": 1, "page": 1, "page_size": 20,
    }


def test_highest_score_first_then_name_and_not_qualified_last(client, reviewer, db):
    make_lead(db, "Zeta", scores=(80,))
    make_lead(db, "Aaa Not Qualified", scores=(40,), status=LeadStatus.NOT_QUALIFIED)
    make_lead(db, "Acme Corp", scores=(92, 78))
    make_lead(db, "Alpha", scores=(80,))

    assert names(client.get("/leads")) == ["Acme Corp", "Alpha", "Zeta", "Aaa Not Qualified"]


def test_not_qualified_is_last_even_with_the_same_score(client, reviewer, db):
    """With lead_threshold 0 a qualified company can score 0, like a not_qualified one;
    the not_qualified group still comes after it, whatever the names."""
    make_lead(db, "Zzz Qualified", scores=(0,))
    make_lead(db, "Bbb Not Qualified", scores=(40,), status=LeadStatus.NOT_QUALIFIED)
    make_lead(db, "Aaa Not Qualified", scores=(40,), status=LeadStatus.NOT_QUALIFIED)
    make_lead(db, "Mmm Approved", scores=(70,), status=LeadStatus.APPROVED)

    assert names(client.get("/leads")) == ["Mmm Approved", "Zzz Qualified",
                                           "Aaa Not Qualified", "Bbb Not Qualified"]


def test_status_filter_and_pages(client, reviewer, db):
    make_lead(db, "Acme Corp", scores=(92,))
    make_lead(db, "Globex", scores=(85,), status=LeadStatus.DRAFT_READY)
    make_lead(db, "Initech", scores=(70,))

    assert names(client.get("/leads", params={"status": "draft_ready"})) == ["Globex"]
    assert client.get("/leads", params={"status": "nonsense"}).status_code == 422

    body = client.get("/leads", params={"page": 2, "page_size": 2}).json()
    assert [i["company_name"] for i in body["items"]] == ["Initech"]
    assert (body["total"], body["page"], body["page_size"]) == (3, 2, 2)


# ---------- one lead ----------

def test_detail_has_the_contract_shape(client, reviewer, db):
    lead = make_lead(db, "Acme Corp", scores=(78, 92), status=LeadStatus.DRAFT_READY)
    job_78, job_92 = lead.evidence["job_ids"]
    make_job(db, lead.company, title="Not in the score", fit_score=40)
    newer = make_snapshot(db, lead, lead_score=97, created_at=NOW)
    older = make_snapshot(db, lead, lead_score=92, created_at=NOW - timedelta(days=1))
    make_draft(db, lead, version=1, status=DraftStatus.REJECTED, reviewed_by=reviewer.user_id)
    latest = make_draft(db, lead, version=2)

    response = client.get(f"/leads/{lead.lead_id}")

    assert response.status_code == 200
    assert response.json() == {
        "lead_id": lead.lead_id,
        "company_name": "Acme Corp",
        "lead_score": 97,
        "best_job_score": 92,
        "qualifying_jobs": 2,
        "status": "draft_ready",
        "reason": "Acme Corp has 2 suitable role(s).",
        "company": {"name": "Acme Corp", "website": None, "location": None,
                    "contact_name": None, "contact_title": None, "contact_email": None},
        # only the jobs of evidence, best fit first
        "jobs": [
            {"job_id": job_92, "title": "React Developer 2", "fit_score": 92,
             "fit_reason": "React Developer 2: 3 profiles cover it"},
            {"job_id": job_78, "title": "React Developer 1", "fit_score": 78,
             "fit_reason": "React Developer 1: 3 profiles cover it"},
        ],
        # oldest first
        "history": [
            {"run_id": older.run_id, "lead_score": 92, "status": "draft_ready",
             "created_at": "2026-11-13T12:00:00Z"},
            {"run_id": newer.run_id, "lead_score": 97, "status": "draft_ready",
             "created_at": "2026-11-14T12:00:00Z"},
        ],
        # the newest version, not reviewed yet
        "draft": {"draft_id": latest.draft_id, "subject": "Subject v2",
                  "body": latest.body, "word_count": 150, "version": 2,
                  "status": "pending_review", "review_comment": None, "reviewed_at": None,
                  "reviewed_by": None},
    }


def test_detail_shows_who_rejected_the_draft_when_and_why(client, reviewer, db):
    lead = make_lead(db, status=LeadStatus.REJECTED)
    draft = make_draft(db, lead, status=DraftStatus.REJECTED, reviewed_by=reviewer.user_id)
    draft.review_comment = "Too generic"
    db.flush()

    shown = client.get(f"/leads/{lead.lead_id}").json()["draft"]

    assert shown["reviewed_by"] == reviewer.full_name
    assert shown["reviewed_at"] == "2026-11-14T12:00:00Z"
    assert shown["review_comment"] == "Too generic"


def test_history_has_the_status_of_each_run(client, reviewer, db):
    lead = make_lead(db, status=LeadStatus.QUALIFIED)
    make_snapshot(db, lead, lead_score=92, created_at=NOW - timedelta(days=1))
    lead.status = LeadStatus.DRAFT_READY                   # the status at the second run
    make_snapshot(db, lead, lead_score=97, created_at=NOW)

    history = client.get(f"/leads/{lead.lead_id}").json()["history"]

    assert [h["status"] for h in history] == ["qualified", "draft_ready"]


def test_detail_without_draft_or_history(client, reviewer, db):
    lead = make_lead(db)

    body = client.get(f"/leads/{lead.lead_id}").json()

    assert body["draft"] is None
    assert body["history"] == []


def test_unknown_lead_is_404(client, reviewer, db):
    for response in (client.get("/leads/999999"),
                     client.patch("/leads/999999/contact", json={"contact_name": "Dana"})):
        assert response.status_code == 404
        assert response.json() == {"detail": "Lead not found"}


# ---------- contact ----------

def test_contact_is_saved_on_the_company(client, reviewer, db):
    lead = make_lead(db, "Acme Corp")

    response = client.patch(f"/leads/{lead.lead_id}/contact", json={
        "contact_name": "  Dana Lee ", "contact_title": "CTO",
        "contact_email": "dana@example.com"})

    assert response.status_code == 200
    assert response.json() == {"name": "Acme Corp", "website": None, "location": None,
                               "contact_name": "Dana Lee", "contact_title": "CTO",
                               "contact_email": "dana@example.com"}
    assert lead.company.contact_email == "dana@example.com"


def test_only_sent_fields_change_and_empty_becomes_null(client, reviewer, db):
    lead = make_lead(db)
    client.patch(f"/leads/{lead.lead_id}/contact", json={
        "contact_name": "Dana Lee", "contact_title": "CTO",
        "contact_email": "dana@example.com"})

    body = client.patch(f"/leads/{lead.lead_id}/contact", json={"contact_title": "  "}).json()

    assert body["contact_title"] is None
    assert (body["contact_name"], body["contact_email"]) == ("Dana Lee", "dana@example.com")


def test_bad_contact_is_422(client, reviewer, db):
    lead = make_lead(db)
    url = f"/leads/{lead.lead_id}/contact"

    assert client.patch(url, json={"contact_email": "not-an-email"}).status_code == 422
    assert client.patch(url, json={"website": "https://acme.example"}).status_code == 422
    assert lead.company.contact_email is None
