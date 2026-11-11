"""Shared helpers and base models used by every schema."""
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base for data passed between stages: trims text, rejects unknown fields."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class LLMOutput(Schema):
    """Base for LLM outputs. Unknown fields are rejected, so a manipulated or
    malformed answer fails validation instead of being stored (FR-09, FR-10)."""


def to_utc(value: Any) -> Any:
    """Accept ISO strings, datetimes or Unix seconds (Himalayas) and return an
    aware UTC datetime. A time without a zone is treated as UTC (Remotive)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def normalize_skill(name: str) -> str:
    """One standard name per skill: lowercase, single spaces ("React" -> "react")."""
    return re.sub(r"\s+", " ", name).strip().lower()


def normalize_skills(values: list[str]) -> list[str]:
    """Normalise every skill, drop empty ones and duplicates, keep the order."""
    seen: list[str] = []
    for v in values:
        s = normalize_skill(v)
        if s and s not in seen:
            seen.append(s)
    return seen


def normalize_company_name(name: str) -> str:
    """Company dedupe rule (Q2): trim, collapse inner spaces, lowercase.
    Legal suffixes (Inc., Ltd.) are kept so different companies are never merged."""
    return re.sub(r"\s+", " ", name).strip().lower()


def gemini_schema(model: type[BaseModel]) -> dict:
    """JSON schema to send to Gemini as the response schema.

    Our LLM models reject unknown fields (extra="forbid"), which adds
    "additionalProperties": false to the schema. Some Gemini SDK versions do not
    accept that keyword, so it is removed here. Strict checking still happens
    afterwards in our code with Model.model_validate_json(response.text).
    """
    def clean(node, in_properties=False):
        if isinstance(node, dict):
            if in_properties:   # keys here are field names (e.g. "title"): keep them all
                return {k: clean(v) for k, v in node.items()}
            return {k: clean(v, in_properties=(k == "properties"))
                    for k, v in node.items() if k not in ("additionalProperties", "title")}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node
    return clean(model.model_json_schema())