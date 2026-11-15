"""Draft review routes (P2-5): edit, approve, reject. Nothing is ever sent (FR-25)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user
from backend.api.schemas import DraftEdit, DraftOut, RejectIn
from backend.db.models import AppUser, Lead, OutreachDraft
from backend.db.session import get_db
from backend.drafts.service import CANNOT_REGENERATE_MESSAGE, latest_draft
from backend.schemas.draft import count_words
from backend.schemas.enums import DraftStatus, LeadStatus

router = APIRouter(prefix="/drafts", tags=["drafts"])

DECIDED = (DraftStatus.APPROVED, DraftStatus.REJECTED)
NOT_QUALIFIED_MESSAGE = CANNOT_REGENERATE_MESSAGE[LeadStatus.NOT_QUALIFIED]


def _reviewable(db: Session, draft_id: int) -> OutreachDraft:
    """The draft, locked, if a decision can still be made on it.

    The lead row is locked the same way ``save_draft`` (Regenerate) locks it, so two
    decisions, or a decision and a new version, happen one after the other. The
    draft and the lead are read again after the lock: what we read before it may
    have been changed by the request we waited for.
    """
    draft = db.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    db.execute(select(Lead.lead_id).where(Lead.lead_id == draft.lead_id).with_for_update())
    db.refresh(draft)
    db.refresh(draft.lead)

    latest = latest_draft(db, draft.lead)
    if latest.draft_id != draft.draft_id:
        raise HTTPException(409, "Only the latest draft version can be reviewed")
    if draft.status in DECIDED:
        raise HTTPException(409, "This draft is already decided")
    return draft


def _record(draft: OutreachDraft, user: AppUser, status: DraftStatus) -> None:
    """Who decided and when: always both (database rule review_complete)."""
    draft.status = status
    draft.reviewed_by = user.user_id
    draft.reviewed_at = datetime.now(timezone.utc)


def _decide(db: Session, draft: OutreachDraft, user: AppUser, status: DraftStatus,
            lead_status: LeadStatus) -> OutreachDraft:
    """Approve or reject: the draft and its company get the decision."""
    if draft.lead.status == LeadStatus.NOT_QUALIFIED:
        # database rule: a lead with no qualifying job is not_qualified and nothing else.
        # Nothing was changed; the lock ends when the request's session is closed.
        raise HTTPException(409, NOT_QUALIFIED_MESSAGE)
    _record(draft, user, status)
    draft.lead.status = lead_status
    db.commit()
    return draft


@router.patch("/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: int, body: DraftEdit, db: Session = Depends(get_db),
               user: AppUser = Depends(get_current_user)):
    draft = _reviewable(db, draft_id)
    draft.subject = body.subject
    draft.body = body.body
    draft.word_count = count_words(body.body)
    _record(draft, user, DraftStatus.EDITED)
    db.commit()
    return draft


@router.post("/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, db: Session = Depends(get_db),
                  user: AppUser = Depends(get_current_user)):
    return _decide(db, _reviewable(db, draft_id), user, DraftStatus.APPROVED,
                   LeadStatus.APPROVED)


@router.post("/{draft_id}/reject", response_model=DraftOut)
def reject_draft(draft_id: int, body: RejectIn, db: Session = Depends(get_db),
                 user: AppUser = Depends(get_current_user)):
    draft = _reviewable(db, draft_id)
    draft.review_comment = body.review_comment
    return _decide(db, draft, user, DraftStatus.REJECTED, LeadStatus.REJECTED)
