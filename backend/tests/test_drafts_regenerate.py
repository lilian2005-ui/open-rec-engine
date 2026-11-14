"""P2-2: Regenerate a draft (new version, older versions untouched, reviewer note in
the prompt). Real PostgreSQL (rolled back after each test) with FakeLLM."""
from datetime import datetime, timezone

import pytest

from backend.db.models import AppUser
from backend.db.models.enums import DraftStatus, LeadStatus, UserRole
from backend.drafts.service import (CannotRegenerate, DraftRejected, LeadNotFound,
                                    regenerate_draft)
from backend.llm import FakeLLM, LLMError
from backend.tests.test_drafts_service import answer, drafts_of, make_lead

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

SECOND = {"subject": "A second try", "body": answer()["body"]}


def versions(db, lead):
    return sorted(drafts_of(db, lead), key=lambda d: d.version)


def with_first_draft(db, **kw):
    """A lead with draft version 1 (as P2-1 would save it)."""
    lead = make_lead(db, **kw)
    regenerate_draft(db, lead.lead_id, call=FakeLLM(answer()))      # qualified -> v1
    return lead


def reject(db, draft, comment):
    user = AppUser(email=f"reviewer{draft.draft_id}@simera.test", password_hash="$2b$12$not-a-real-hash",
                   full_name="Reviewer", role=UserRole.REVIEWER)
    db.add(user)
    db.flush()
    draft.status, draft.review_comment = DraftStatus.REJECTED, comment
    draft.reviewed_by, draft.reviewed_at = user.user_id, NOW
    draft.lead.status = LeadStatus.REJECTED
    db.flush()


def test_draft_ready_lead_gets_version_2_and_version_1_is_unchanged(db):
    lead = with_first_draft(db)
    [v1] = drafts_of(db, lead)
    before = (v1.subject, v1.body, v1.status, v1.reviewed_by)

    new = regenerate_draft(db, lead.lead_id, call=FakeLLM(SECOND))

    assert (new.version, new.status, new.subject) == (2, DraftStatus.PENDING_REVIEW, "A second try")
    assert (v1.subject, v1.body, v1.status, v1.reviewed_by) == before
    assert lead.status == LeadStatus.DRAFT_READY


def test_rejected_draft_comment_goes_to_the_llm_and_lead_is_draft_ready_again(db):
    lead = with_first_draft(db)
    [v1] = drafts_of(db, lead)
    reject(db, v1, "too formal")
    fake = FakeLLM(SECOND)

    new = regenerate_draft(db, lead.lead_id, call=fake)

    assert 'REVIEWER NOTE: "too formal"' in fake.prompts[0]
    assert new.version == 2 and lead.status == LeadStatus.DRAFT_READY
    # the rejected version keeps its review (history)
    assert (v1.status, v1.review_comment) == (DraftStatus.REJECTED, "too formal")
    assert v1.reviewed_by is not None and v1.reviewed_at == NOW


def test_a_sent_note_wins_over_the_old_comment(db):
    lead = with_first_draft(db)
    reject(db, drafts_of(db, lead)[0], "too formal")
    fake = FakeLLM(SECOND)

    regenerate_draft(db, lead.lead_id, note="mention the second role", call=fake)

    assert 'REVIEWER NOTE: "mention the second role"' in fake.prompts[0]
    assert "too formal" not in fake.prompts[0]


def test_no_note_and_no_rejection_means_no_note_line(db):
    lead = with_first_draft(db)
    fake = FakeLLM(SECOND)

    regenerate_draft(db, lead.lead_id, note="   ", call=fake)

    assert "REVIEWER NOTE:" not in fake.prompts[0]


def test_a_long_note_is_cut_to_500_characters(db):
    lead = with_first_draft(db)
    fake = FakeLLM(SECOND)

    regenerate_draft(db, lead.lead_id, note="a" * 700, call=fake)

    assert f'REVIEWER NOTE: "{"a" * 500}"' in fake.prompts[0]
    assert "a" * 501 not in fake.prompts[0]


def test_the_note_stays_in_the_prompt_when_a_check_asks_again(db):
    lead = with_first_draft(db)
    fake = FakeLLM(answer(start="Dear hiring manager,"), SECOND)

    regenerate_draft(db, lead.lead_id, note="shorter please", call=fake)

    assert fake.calls == 2
    assert 'REVIEWER NOTE: "shorter please"' in fake.prompts[1]
    assert "REJECTED because" in fake.prompts[1]


def test_regenerate_twice_gives_versions_1_2_3(db):
    lead = with_first_draft(db)

    regenerate_draft(db, lead.lead_id, call=FakeLLM(SECOND))
    regenerate_draft(db, lead.lead_id, call=FakeLLM(SECOND))

    assert [d.version for d in versions(db, lead)] == [1, 2, 3]


@pytest.mark.parametrize("status, message", [
    (LeadStatus.APPROVED, "This draft is already approved"),
    (LeadStatus.NOT_QUALIFIED, "This company has no suitable jobs"),
])
def test_approved_or_not_qualified_cannot_regenerate(db, status, message):
    lead = make_lead(db, status=status)
    fake = FakeLLM()

    with pytest.raises(CannotRegenerate, match=message):
        regenerate_draft(db, lead.lead_id, call=fake)

    assert fake.calls == 0 and drafts_of(db, lead) == []


def test_unknown_lead_is_not_found(db):
    with pytest.raises(LeadNotFound):
        regenerate_draft(db, 999_999, call=FakeLLM())


def test_llm_always_failing_changes_nothing(db):
    lead = with_first_draft(db)
    reject(db, drafts_of(db, lead)[0], "too formal")

    with pytest.raises(LLMError):
        regenerate_draft(db, lead.lead_id, call=FakeLLM(*["not json"] * 4))

    assert [d.version for d in versions(db, lead)] == [1]
    assert lead.status == LeadStatus.REJECTED


def test_every_draft_breaking_a_rule_changes_nothing(db):
    lead = with_first_draft(db)
    bad = answer(extra="See https://simera.com.")

    with pytest.raises(DraftRejected, match="link"):
        regenerate_draft(db, lead.lead_id, call=FakeLLM(bad, bad, bad))

    assert [d.version for d in versions(db, lead)] == [1]
    assert lead.status == LeadStatus.DRAFT_READY
