"""app_setting run_interval_hours

P1-7: adds the run_interval_hours setting (default 32). A scheduled run starts
when the last finished run is this many hours old. Data only, no schema change.

Revision ID: 7c2e9a41b3d8
Revises: 1d0a105a4868
Create Date: 2026-11-15 15:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c2e9a41b3d8'
down_revision: Union[str, Sequence[str], None] = '1d0a105a4868'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # only if missing: seed_settings may have added it already
    op.execute("INSERT INTO app_setting (key, value) VALUES ('run_interval_hours', '32') "
               "ON CONFLICT (key) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM app_setting WHERE key = 'run_interval_hours'")
