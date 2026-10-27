"""Mock candidate profile (data contract 4, seed file data/candidates.json)."""
from pydantic import Field, field_validator

from .common import Schema, normalize_skills
from .enums import Seniority


class CandidateProfile(Schema):
    candidate_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=100)
    headline: str | None = Field(default=None, max_length=150)
    years_experience: float = Field(ge=0, le=50)
    seniority: Seniority
    skills: list[str] = Field(min_length=1)
    timezone_offsets: list[int] = Field(default_factory=list)
    availability: str | None = None
    summary: str | None = None

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        return normalize_skills(v)

    @field_validator("timezone_offsets")
    @classmethod
    def _offsets(cls, v: list[int]) -> list[int]:
        for o in v:
            if not -12 <= o <= 14:
                raise ValueError(f"timezone offset {o} is outside -12..14")
        return v
