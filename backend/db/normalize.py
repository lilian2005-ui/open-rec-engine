"""Normalisation rules (data contract v1.1 section 7: Q2 company names, Q3 content hash).

Company names and skills reuse the rules in ``backend.schemas.common`` so there is
only one definition of each.
"""
import hashlib
import re

from backend.schemas.common import normalize_company_name
from backend.schemas.common import normalize_skills as _normalize_skills


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def company_name_key(name: str) -> str:
    """Q2: the value of ``company.normalized_name``. Trim, collapse inner spaces,
    lowercase; punctuation and Inc./Ltd. are kept so different companies are never
    merged. Same result as lower(btrim(regexp_replace(name, '\\s+', ' ', 'g'))).
    """
    return normalize_company_name(name)


def content_hash(title: str, description_text: str) -> str:
    """Q3: SHA-256 hex of the title and the cleaned description, each with whitespace
    collapsed, joined by a newline. A whitespace-only change keeps the same hash."""
    payload = _collapse(title) + "\n" + _collapse(description_text)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_skills(skills: list[str]) -> list[str]:
    """Trim, lowercase, and drop empty values and duplicates, keeping the first order."""
    return _normalize_skills(skills)
