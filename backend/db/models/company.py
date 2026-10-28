"""company: one row per hiring company. A company with jobs cannot be deleted."""
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Identity, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.db.models.job_posting import JobPosting
    from backend.db.models.lead import Lead


class Company(Base):
    """A hiring company. Contact fields are optional and entered by the sales team;
    the LLM never generates them.

    Q2: names are matched case- and whitespace-insensitively (see
    ``backend.db.normalize.company_name_key``). ``uq_company_name_key`` enforces it, so
    "Acme Corp" and "ACME  corp" are one company, while "Acme Corp Inc." is another.
    """

    __tablename__ = "company"
    __table_args__ = (
        Index(
            "uq_company_name_key",
            text(r"lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))"),
            unique=True,
        ),
    )

    company_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_title: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)

    job_postings: Mapped[list["JobPosting"]] = relationship(
        back_populates="company", passive_deletes="all"
    )
    lead: Mapped["Lead | None"] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
