"""job_posting source_fields

Adds job_posting.source_fields (JSONB, nullable): structured fields the source
gives as-is (Himalayas salary, employment type, seniority, location and timezone
restrictions), so later stages read them instead of guessing from the text.

Revision ID: 1d0a105a4868
Revises: 5551475cdc2f
Create Date: 2026-11-08 14:42:49.615684+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1d0a105a4868'
down_revision: Union[str, Sequence[str], None] = '5551475cdc2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_posting", sa.Column("source_fields", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_posting", "source_fields")