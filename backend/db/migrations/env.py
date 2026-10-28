"""Alembic environment. The URL comes from get_database_url(), never from alembic.ini.

Tests pass an open connection in ``config.attributes["connection"]`` so migrations
run against the test database.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import backend.db.models  # noqa: F401  registers every table on Base.metadata
from backend.db.base import Base
from backend.db.models.enums import TextEnum
from backend.db.session import get_database_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Render TextEnum as sa.Text(); the migration must not import model code."""
    if type_ == "type" and isinstance(obj, TextEnum):
        return "sa.Text()"
    return False


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=get_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(get_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
