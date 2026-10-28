"""Database fixtures. DB tests run on real PostgreSQL (TEST_DATABASE_URL) and are
skipped when it is not set. The schema is built with the real migrations."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not be the same database as DATABASE_URL")
    engine = create_engine(url)
    with engine.begin() as conn:
        cfg = alembic_config(conn)
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A session inside a transaction that is rolled back after the test.
    A failed flush only rolls back to a savepoint, so the test can continue."""
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint",
                          expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
