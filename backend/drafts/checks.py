"""Stage 5 checks in code (P2-1). The DraftOutput schema checks the length only;
these rules are checked here before a draft is saved. Pure functions, no database.

``check_draft`` returns the list of problems. An empty list means the draft is fine.
"""
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

LINK = re.compile(r"https?://|\bwww\.|[\w.+-]+@[\w-]+\.[a-z]{2,}", re.IGNORECASE)

PRICE = re.compile(
    r"[$€£]|\b(?:usd|eur|gbp)\b|\bper (?:hour|day|week|month|year|annum)\b"
    r"|\bhourly rate\b|/(?:hr|hour|month|year)\b",
    re.IGNORECASE,
)

PROMISE = re.compile(
    r"\bguarantee[ds]?\b|\b100\s?%|\bwithin \d+ (?:hours?|days?|weeks?)\b"
    r"|\bwithin (?:a|one) (?:day|week)\b|\bimmediately\b|\bhit the ground running\b"
    r"|\bready to (?:start|join|contribute)\b|\brisk[- ]free\b|\bno risk\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    """Lowercase with single spaces, so "Senior  React" matches "senior react"."""
    return re.sub(r"\s+", " ", text).strip().lower()


def mentions_a_role(subject: str, body: str, role_titles: Iterable[str]) -> bool:
    text = _norm(f"{subject} {body}")
    return any(_norm(t) in text for t in role_titles if t and t.strip())


def starts_with_greeting(body: str, company_name: str, first_name: str | None) -> bool:
    """No contact: "Hello <company> team". A contact: their first name in the first line."""
    first_line = _norm(body.strip().splitlines()[0]) if body.strip() else ""
    if first_name is None:
        return first_line.startswith(_norm(f"Hello {company_name} team"))
    return re.search(rf"\b{re.escape(first_name.lower())}\b", first_line) is not None


def named_candidates(text: str, candidate_names: Iterable[str]) -> list[str]:
    """Candidate names found in the text (whole words, so "Candidate 1010" is not
    "Candidate 101")."""
    found = []
    for name in candidate_names:
        name = name.strip()
        if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
            found.append(name)
    return found


def check_draft(subject: str, body: str, *, company_name: str,
                roles: Sequence[Mapping[str, Any]], first_name: str | None,
                candidate_names: Iterable[str]) -> list[str]:
    """Every rule the draft breaks, as short English messages for the run log."""
    text = f"{subject}\n{body}"
    problems = []
    if not mentions_a_role(subject, body, (r.get("title") or "" for r in roles)):
        problems.append("does not mention any of the company's open roles by title")
    if not starts_with_greeting(body, company_name, first_name):
        expected = f'"Hello {company_name} team"' if first_name is None else f"the name {first_name}"
        problems.append(f"does not start with {expected}")
    if m := LINK.search(text):
        problems.append(f"contains a link or email ({m.group(0)!r})")
    if m := PRICE.search(text):
        problems.append(f"contains a price or currency ({m.group(0)!r})")
    if m := PROMISE.search(text):
        problems.append(f"contains a promise ({m.group(0)!r})")
    if names := named_candidates(text, candidate_names):
        problems.append(f"names a candidate ({', '.join(names)})")
    return problems
