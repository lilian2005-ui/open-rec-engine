"""P2-3: PATCH /drafts/{draft_id}, approve, reject. Real PostgreSQL (``db`` of
conftest.py). No LLM: these routes only record a person's decision."""
import pytest

from backend.db.models.enums import DraftStatus, LeadStatus
from backend.tests.api_fixtures import client, make_draft, make_lead, reviewer  # noqa: F401


def ready_lead(db, **kw):
    """A lead with a draft waiting for review (as P2-1 leaves it)."""
    lead = make_lead(db, status=LeadStatus.DRAFT_READY, **kw)
    return lead, make_draft(db, lead)


# ---------- edit ----------

def test_edit_saves_the_text_and_counts_the_words_again(client, reviewer, db):
    lead, draft = ready_lead(db)

    response = client.patch(f"/drafts/{draft.draft_id}",
                            json={"subject": "A new subject", "body": "Only five words here now"})

    assert response.status_code == 200
    assert response.json() == {
        "draft_id": draft.draft_id, "subject": "A new subject",
        "body": "Only five words here now", "word_count": 5,   # no 120-180 rule for a person
        "version": 1, "status": "edited"}
    assert draft.reviewed_by == reviewer.user_id
    assert draft.reviewed_at is not None
    assert lead.status == LeadStatus.DRAFT_READY


@pytest.mark.parametrize("body", [
    {"subject": "Subject", "body": "   "},
    {"subject": "", "body": "Some text"},
    {"subject": "x" * 151, "body": "Some text"},
    {"subject": "Subject"},
])
def test_bad_edit_is_422_and_changes_nothing(client, reviewer, db, body):
    _, draft = ready_lead(db)

    assert client.patch(f"/drafts/{draft.draft_id}", json=body).status_code == 422
    assert (draft.subject, draft.status) == ("Subject v1", DraftStatus.PENDING_REVIEW)
    assert draft.reviewed_by is None


# ---------- approve ----------

def test_approve_marks_the_draft_and_the_lead_and_records_who_and_when(client, reviewer, db):
    lead, draft = ready_lead(db)

    response = client.post(f"/drafts/{draft.draft_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert set(response.json()) == {"draft_id", "subject", "body", "word_count", "version",
                                    "status"}
    assert draft.status == DraftStatus.APPROVED
    assert lead.status == LeadStatus.APPROVED
    assert draft.reviewed_by == reviewer.user_id
    assert draft.reviewed_at is not None


def test_a_second_decision_is_409(client, reviewer, db):
    _, draft = ready_lead(db)
    client.post(f"/drafts/{draft.draft_id}/approve")

    answers = [client.post(f"/drafts/{draft.draft_id}/approve"),
               client.post(f"/drafts/{draft.draft_id}/reject", json={"review_comment": "No"}),
               client.patch(f"/drafts/{draft.draft_id}", json={"subject": "S", "body": "B"})]

    for response in answers:
        assert response.status_code == 409
        assert response.json() == {"detail": "This draft is already decided"}
    assert draft.status == DraftStatus.APPROVED


def test_an_edited_draft_can_still_be_approved(client, reviewer, db):
    lead, draft = ready_lead(db)
    client.patch(f"/drafts/{draft.draft_id}", json={"subject": "S", "body": "Edited text"})

    assert client.post(f"/drafts/{draft.draft_id}/approve").status_code == 200
    assert (draft.status, draft.body) == (DraftStatus.APPROVED, "Edited text")
    assert lead.status == LeadStatus.APPROVED


# ---------- reject ----------

def test_reject_needs_a_comment(client, reviewer, db):
    lead, draft = ready_lead(db)
    url = f"/drafts/{draft.draft_id}/reject"

    assert client.post(url).status_code == 422
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"review_comment": "  "}).status_code == 422
    assert draft.status == DraftStatus.PENDING_REVIEW
    assert lead.status == LeadStatus.DRAFT_READY


def test_reject_saves_the_comment_and_marks_the_draft_and_the_lead(client, reviewer, db):
    lead, draft = ready_lead(db)

    response = client.post(f"/drafts/{draft.draft_id}/reject",
                           json={"review_comment": "Too generic"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert (draft.status, draft.review_comment) == (DraftStatus.REJECTED, "Too generic")
    assert lead.status == LeadStatus.REJECTED
    assert draft.reviewed_by == reviewer.user_id
    assert draft.reviewed_at is not None


# ---------- which draft can be decided ----------

def test_only_the_latest_version_can_be_decided(client, reviewer, db):
    lead, old = ready_lead(db)
    make_draft(db, lead, version=2)

    answers = [client.post(f"/drafts/{old.draft_id}/approve"),
               client.post(f"/drafts/{old.draft_id}/reject", json={"review_comment": "No"}),
               client.patch(f"/drafts/{old.draft_id}", json={"subject": "S", "body": "B"})]

    for response in answers:
        assert response.status_code == 409
        assert response.json() == {"detail": "Only the latest draft version can be reviewed"}
    assert old.status == DraftStatus.PENDING_REVIEW
    assert lead.status == LeadStatus.DRAFT_READY


def test_a_lead_that_is_no_longer_qualified_cannot_be_decided(client, reviewer, db):
    lead = make_lead(db, status=LeadStatus.NOT_QUALIFIED)
    draft = make_draft(db, lead)

    for response in (client.post(f"/drafts/{draft.draft_id}/approve"),
                     client.post(f"/drafts/{draft.draft_id}/reject",
                                 json={"review_comment": "No"})):
        assert response.status_code == 409
        assert response.json() == {"detail": "This lead is no longer qualified"}
    assert draft.status == DraftStatus.PENDING_REVIEW
    assert draft.reviewed_by is None
    assert lead.status == LeadStatus.NOT_QUALIFIED


def test_unknown_draft_is_404(client, reviewer, db):
    answers = [client.post("/drafts/999999/approve"),
               client.post("/drafts/999999/reject", json={"review_comment": "No"}),
               client.patch("/drafts/999999", json={"subject": "S", "body": "B"})]

    for response in answers:
        assert response.status_code == 404
        assert response.json() == {"detail": "Draft not found"}
