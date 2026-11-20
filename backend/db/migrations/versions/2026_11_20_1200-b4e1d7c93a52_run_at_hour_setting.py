"""app_setting run_at_hour

P1-7b: adds the run_at_hour setting (default "none" = no fixed hour). When it is
0-23, the scheduled run starts once a day at that hour, Gaza time. Data only, no
schema change.

Revision ID: b4e1d7c93a52
Revises: 7c2e9a41b3d8
Create Date: 2026-11-20 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b4e1d7c93a52'
down_revision: Union[str, Sequence[str], None] = '7c2e9a41b3d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # only if missing: seed_settings may have added it already
    op.execute("INSERT INTO app_setting (key, value) VALUES ('run_at_hour', 'none') "
               "ON CONFLICT (key) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM app_setting WHERE key = 'run_at_hour'")
