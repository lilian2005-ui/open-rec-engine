"""Stage 5 and review: the LLM draft, the stored draft and the reviewer's decision."""
from datetime import datetime
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator

from .common import LLMOutput, Schema, to_utc
from .enums import DraftStatus

MIN_WORDS, MAX_WORDS = 120, 180


def count_words(text: str) -> int:
    return len(text.split())


class DraftOutput(LLMOutput):
    """Stage 5 LLM output. A body outside 120-180 words is rejected (FR-20)."""

    subject: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def _length(cls, v: str) -> str:
        n = count_words(v)
        if not MIN_WORDS <= n <= MAX_WORDS:
            raise ValueError(f"body has {n} words; it must have {MIN_WORDS}-{MAX_WORDS}")
        return v

    @computed_field
    @property
    def word_count(self) -> int:
        return count_words(self.body)


class OutreachDraft(Schema):
    """A draft as stored in outreach_draft, including the review decision."""

    lead_id: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1)
    word_count: int = Field(ge=0)
    version: int = Field(default=1, ge=1)
    status: DraftStatus = DraftStatus.PENDING_REVIEW
    reviewed_by: int | None = None                  # app_user.user_id
    reviewed_at: datetime | None = None
    review_comment: str | None = None

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def _utc(cls, v):
        return to_utc(v)

    @model_validator(mode="after")
    def _review(self):
        reviewed = self.status != DraftStatus.PENDING_REVIEW
        if reviewed and (self.reviewed_by is None or self.reviewed_at is None):
            raise ValueError("a reviewed draft needs reviewed_by and reviewed_at")
        if not reviewed and (self.reviewed_by is not None or self.reviewed_at is not None):
            raise ValueError("a pending draft cannot have a reviewer yet")
        return self


class ReviewDecisionIn(Schema):
    """API input when a reviewer approves, edits or rejects a draft (FR-24).
    The reviewer is taken from the login token, never from the request body."""

    decision: Literal["approved", "edited", "rejected"]
    comment: str | None = Field(default=None, max_length=1000)
    subject: str | None = Field(default=None, max_length=150)   # only for "edited"
    body: str | None = None                                     # only for "edited"

    @model_validator(mode="after")
    def _edited(self):
        if self.decision == "edited" and not (self.subject or self.body):
            raise ValueError("an edited decision must include the new subject or body")
        if self.decision != "edited" and (self.subject or self.body):
            raise ValueError("subject and body can only be sent with an edited decision")
        return self
