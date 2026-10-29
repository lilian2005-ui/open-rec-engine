"""data contract v1.1: 4 new tables and the column changes to the first 6

Adds app_user, pipeline_run (with the Q5 one-running index), app_setting (seeded
with the defaults) and lead_snapshot, and moves company, job_posting,
job_requirement, lead and outreach_draft to the v1.1 columns and checks.

Existing companies get normalized_name from the Q2 rule. The lead table must be
empty: v1 lead scores (a sum) and text reviewers cannot be converted to v1.1
without guessing, so leads are rebuilt by the next run instead.

Revision ID: 5551475cdc2f
Revises: d9f3fd46c517
Create Date: 2026-10-28 18:09:31.326852+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Default settings (data contract v1.1). Written out here, not imported from the
# models, so this migration never changes when the code does.
DEFAULT_SETTINGS = [
    {"key": "lead_threshold", "value": "60"},
    {"key": "fetch_limit", "value": "100"},
    {"key": "himalayas_enabled", "value": "true"},
    {"key": "remotive_enabled", "value": "true"},
    {"key": "run_mode", "value": "manual"},
    {"key": "max_retries", "value": "3"},
]

# Q2 rule, the same as backend.db.normalize.company_name_key
NORMALIZED_NAME = r"lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))"

# revision identifiers, used by Alembic.
revision: str = '5551475cdc2f'
down_revision: Union[str, Sequence[str], None] = 'd9f3fd46c517'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_no_leads() -> None:
    leads = op.get_bind().scalar(sa.text("SELECT count(*) FROM lead"))
    if leads:
        raise RuntimeError(
            f"lead has {leads} rows. v1 lead scores and text reviewers cannot be converted "
            "to data contract v1.1; delete the leads (their drafts go with them) and run "
            "stage 4 again after upgrading."
        )


def upgrade() -> None:
    _require_no_leads()

    # ---- new tables ----
    op.create_table('app_user',
    sa.Column('user_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), server_default=sa.text("'reviewer'"), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    # hand-fixed: autogenerate wrote '$2%%', which PostgreSQL stores literally
    sa.CheckConstraint("password_hash LIKE '$2%'", name=op.f('ck_app_user_password_hash_bcrypt')),
    sa.CheckConstraint("role IN ('reviewer', 'admin')", name=op.f('ck_app_user_role_enum')),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_app_user_email_lowercase')),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_app_user')),
    sa.UniqueConstraint('email', name=op.f('uq_app_user_email'))
    )
    op.create_table('app_setting',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('updated_by', sa.BigInteger(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['updated_by'], ['app_user.user_id'], name=op.f('fk_app_setting_updated_by_app_user')),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_setting'))
    )
    op.create_index(op.f('ix_app_setting_updated_by'), 'app_setting', ['updated_by'], unique=False)
    op.create_table('pipeline_run',
    sa.Column('run_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('started_by', sa.BigInteger(), nullable=True),
    sa.Column('trigger_type', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('jobs_fetched', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('jobs_new', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('jobs_updated', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("status IN ('running', 'completed', 'partial', 'failed')", name=op.f('ck_pipeline_run_status_enum')),
    sa.CheckConstraint("trigger_type IN ('manual', 'scheduled')", name=op.f('ck_pipeline_run_trigger_type_enum')),
    sa.CheckConstraint('jobs_fetched >= 0', name=op.f('ck_pipeline_run_jobs_fetched_non_negative')),
    sa.CheckConstraint('jobs_new >= 0', name=op.f('ck_pipeline_run_jobs_new_non_negative')),
    sa.CheckConstraint('jobs_updated >= 0', name=op.f('ck_pipeline_run_jobs_updated_non_negative')),
    sa.ForeignKeyConstraint(['started_by'], ['app_user.user_id'], name=op.f('fk_pipeline_run_started_by_app_user')),
    sa.PrimaryKeyConstraint('run_id', name=op.f('pk_pipeline_run'))
    )
    op.create_index(op.f('ix_pipeline_run_started_by'), 'pipeline_run', ['started_by'], unique=False)
    # Q5: at most one run with status 'running'
    op.create_index('uq_pipeline_run_one_running', 'pipeline_run', ['status'], unique=True, postgresql_where=sa.text("status = 'running'"))
    op.create_table('lead_snapshot',
    sa.Column('snapshot_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('lead_id', sa.BigInteger(), nullable=False),
    sa.Column('run_id', sa.BigInteger(), nullable=False),
    sa.Column('lead_score', sa.SmallInteger(), nullable=False),
    sa.Column('best_job_score', sa.SmallInteger(), nullable=False),
    sa.Column('qualifying_jobs', sa.SmallInteger(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('qualified', 'not_qualified', 'draft_ready', 'approved', 'rejected')", name=op.f('ck_lead_snapshot_status_enum')),
    sa.CheckConstraint('best_job_score BETWEEN 0 AND 100', name=op.f('ck_lead_snapshot_best_job_score_range')),
    sa.CheckConstraint('lead_score BETWEEN 0 AND 100', name=op.f('ck_lead_snapshot_lead_score_range')),
    sa.CheckConstraint('qualifying_jobs >= 0', name=op.f('ck_lead_snapshot_qualifying_jobs_non_negative')),
    sa.ForeignKeyConstraint(['lead_id'], ['lead.lead_id'], name=op.f('fk_lead_snapshot_lead_id_lead'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_run.run_id'], name=op.f('fk_lead_snapshot_run_id_pipeline_run')),
    sa.PrimaryKeyConstraint('snapshot_id', name=op.f('pk_lead_snapshot')),
    sa.UniqueConstraint('lead_id', 'run_id', name=op.f('uq_lead_snapshot_lead_id_run_id'))
    )
    op.create_index(op.f('ix_lead_snapshot_run_id'), 'lead_snapshot', ['run_id'], unique=False)

    # data migration: seed the default settings
    app_setting = sa.table('app_setting', sa.column('key', sa.Text()), sa.column('value', sa.Text()))
    op.bulk_insert(app_setting, DEFAULT_SETTINGS)

    # ---- company: normalized_name replaces UNIQUE name and uq_company_name_key ----
    op.add_column('company', sa.Column('normalized_name', sa.Text(), nullable=True))
    # uq_company_name_key enforced this same expression, so the backfill is unique
    op.execute(f"UPDATE company SET normalized_name = {NORMALIZED_NAME}")
    op.alter_column('company', 'normalized_name', existing_type=sa.Text(), nullable=False)
    op.drop_index('uq_company_name_key', table_name='company')
    op.drop_constraint(op.f('uq_company_name'), 'company', type_='unique')
    op.create_unique_constraint(op.f('uq_company_normalized_name'), 'company', ['normalized_name'])

    # ---- job_posting ----
    op.add_column('job_posting', sa.Column('run_id', sa.BigInteger(), nullable=True))
    op.add_column('job_posting', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_job_posting_run_id'), 'job_posting', ['run_id'], unique=False)
    op.create_foreign_key(op.f('fk_job_posting_run_id_pipeline_run'), 'job_posting', 'pipeline_run', ['run_id'], ['run_id'])

    # ---- job_requirement ----
    op.add_column('job_requirement', sa.Column('source_hash', sa.CHAR(length=64), nullable=True))
    op.add_column('job_requirement', sa.Column('salary_period', sa.Text(), nullable=True))
    op.add_column('job_requirement', sa.Column('flag_reason', sa.Text(), nullable=True))
    op.create_check_constraint(op.f('ck_job_requirement_source_hash_length'), 'job_requirement',
                               'char_length(source_hash) = 64')
    op.create_check_constraint(op.f('ck_job_requirement_salary_period_enum'), 'job_requirement',
                               "salary_period IN ('hourly', 'weekly', 'fortnightly', 'monthly', 'annual')")

    # ---- lead (empty, see _require_no_leads) ----
    op.add_column('lead', sa.Column('run_id', sa.BigInteger(), nullable=True))
    op.add_column('lead', sa.Column('best_job_score', sa.SmallInteger(), nullable=False))
    op.alter_column('lead', 'lead_score', existing_type=sa.INTEGER(), type_=sa.SmallInteger(),
                    existing_nullable=False)
    op.drop_constraint(op.f('ck_lead_lead_score_non_negative'), 'lead', type_='check')
    op.create_check_constraint(op.f('ck_lead_lead_score_range'), 'lead', 'lead_score BETWEEN 0 AND 100')
    op.create_check_constraint(op.f('ck_lead_best_job_score_range'), 'lead', 'best_job_score BETWEEN 0 AND 100')
    op.create_index(op.f('ix_lead_run_id'), 'lead', ['run_id'], unique=False)
    op.create_foreign_key(op.f('fk_lead_run_id_pipeline_run'), 'lead', 'pipeline_run', ['run_id'], ['run_id'])

    # ---- outreach_draft: reviewed_by becomes a user id (empty, drafts need a lead) ----
    op.alter_column('outreach_draft', 'reviewed_by', existing_type=sa.TEXT(), type_=sa.BigInteger(),
                    existing_nullable=True, postgresql_using='reviewed_by::bigint')
    op.create_index(op.f('ix_outreach_draft_reviewed_by'), 'outreach_draft', ['reviewed_by'], unique=False)
    op.create_foreign_key(op.f('fk_outreach_draft_reviewed_by_app_user'), 'outreach_draft', 'app_user', ['reviewed_by'], ['user_id'])


def downgrade() -> None:
    _require_no_leads()

    # ---- outreach_draft ----
    op.drop_constraint(op.f('fk_outreach_draft_reviewed_by_app_user'), 'outreach_draft', type_='foreignkey')
    op.drop_index(op.f('ix_outreach_draft_reviewed_by'), table_name='outreach_draft')
    op.alter_column('outreach_draft', 'reviewed_by', existing_type=sa.BigInteger(), type_=sa.TEXT(),
                    existing_nullable=True, postgresql_using='reviewed_by::text')

    # ---- lead ----
    op.drop_constraint(op.f('fk_lead_run_id_pipeline_run'), 'lead', type_='foreignkey')
    op.drop_index(op.f('ix_lead_run_id'), table_name='lead')
    op.drop_constraint(op.f('ck_lead_best_job_score_range'), 'lead', type_='check')
    op.drop_constraint(op.f('ck_lead_lead_score_range'), 'lead', type_='check')
    op.create_check_constraint(op.f('ck_lead_lead_score_non_negative'), 'lead', 'lead_score >= 0')
    op.alter_column('lead', 'lead_score', existing_type=sa.SmallInteger(), type_=sa.INTEGER(),
                    existing_nullable=False)
    op.drop_column('lead', 'best_job_score')
    op.drop_column('lead', 'run_id')

    # ---- job_requirement ----
    op.drop_constraint(op.f('ck_job_requirement_salary_period_enum'), 'job_requirement', type_='check')
    op.drop_constraint(op.f('ck_job_requirement_source_hash_length'), 'job_requirement', type_='check')
    op.drop_column('job_requirement', 'flag_reason')
    op.drop_column('job_requirement', 'salary_period')
    op.drop_column('job_requirement', 'source_hash')

    # ---- job_posting ----
    op.drop_constraint(op.f('fk_job_posting_run_id_pipeline_run'), 'job_posting', type_='foreignkey')
    op.drop_index(op.f('ix_job_posting_run_id'), table_name='job_posting')
    op.drop_column('job_posting', 'updated_at')
    op.drop_column('job_posting', 'run_id')

    # ---- company (fails if two companies now share a name) ----
    op.drop_constraint(op.f('uq_company_normalized_name'), 'company', type_='unique')
    op.create_unique_constraint(op.f('uq_company_name'), 'company', ['name'])
    op.create_index('uq_company_name_key', 'company', [sa.literal_column(NORMALIZED_NAME)], unique=True)
    op.drop_column('company', 'normalized_name')

    # ---- new tables (dropping app_setting removes the seeded rows) ----
    op.drop_index(op.f('ix_lead_snapshot_run_id'), table_name='lead_snapshot')
    op.drop_table('lead_snapshot')
    op.drop_index('uq_pipeline_run_one_running', table_name='pipeline_run', postgresql_where=sa.text("status = 'running'"))
    op.drop_index(op.f('ix_pipeline_run_started_by'), table_name='pipeline_run')
    op.drop_table('pipeline_run')
    op.drop_index(op.f('ix_app_setting_updated_by'), table_name='app_setting')
    op.drop_table('app_setting')
    op.drop_table('app_user')
