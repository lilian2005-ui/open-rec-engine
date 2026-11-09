"""Database engine, session factory and the FastAPI dependency.

Usage in an endpoint:  def handler(db: Session = Depends(get_db)): ...
"""
import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.config import settings


def get_database_url() -> str:
    """The only place that reads the database URL (postgresql+psycopg://...)."""
    url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Created on first use, so importing the models never needs DATABASE_URL."""
    return create_engine(get_database_url(), pool_pre_ping=True)


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()
