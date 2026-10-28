"""The 8 enums of data contract section 7, and how they are stored.

The enum classes come from ``backend.schemas.enums`` (one definition for the API
and the database). Values are stored as TEXT, not a native PostgreSQL ENUM, with a
CHECK constraint per column that lists the allowed values.
"""
from enum import Enum

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.types import TypeDecorator

from backend.schemas.enums import (DraftStatus, EmploymentType, ExtractionStatus, JobStatus,
                                   LeadStatus, RemotePolicy, Seniority, Source)

__all__ = [
    "DraftStatus", "EmploymentType", "ExtractionStatus", "JobStatus", "LeadStatus",
    "RemotePolicy", "Seniority", "Source", "TextEnum", "enum_check",
]


class TextEnum(TypeDecorator):
    """A str-based Enum stored as TEXT. Raises ValueError on an unknown value,
    both when saving and when loading."""

    impl = Text
    cache_ok = True

    def __init__(self, enum_class: type[Enum]):
        super().__init__()
        self.enum_class = enum_class

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return self.enum_class(value).value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.enum_class(value)

    def copy(self, **kw):
        return TextEnum(self.enum_class)


def enum_check(column: str, enum_class: type[Enum]) -> CheckConstraint:
    """CHECK (<column> IN (...)) named ck_<table>_<column>_enum."""
    values = ", ".join(f"'{member.value}'" for member in enum_class)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_enum")
