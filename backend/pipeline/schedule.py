"""P1-7: the scheduled run.

The timer wakes up every hour and asks the database whether a run is due. The
database remembers the last run, so restarting the server never resets the count.
``run_mode = manual`` turns it off at once, without a restart.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import PipelineRun
from backend.db.models.enums import RunStatus, TriggerType
from backend.db.session import SessionLocal, get_engine
from backend.discovery.service import load_settings
from backend.pipeline.runner import run_pipeline

# uvicorn's logger, so these lines show in the server log without a logging setup
log = logging.getLogger("uvicorn.error")


def is_due(db: Session, now: datetime) -> bool:
    """True when a scheduled run should start now.

    The last run is the latest one that finished (manual or scheduled, any status).
    Never due while a run is running: a run longer than an hour would otherwise be
    closed as stuck by the next run_pipeline while it is still going.
    """
    settings = load_settings(db)
    if settings.run_mode != TriggerType.SCHEDULED:
        return False
    if db.scalar(select(PipelineRun.run_id).where(PipelineRun.status == RunStatus.RUNNING)
                 .limit(1)) is not None:
        return False
    last = db.scalar(select(PipelineRun.finished_at)
                     .where(PipelineRun.finished_at.is_not(None))
                     .order_by(PipelineRun.finished_at.desc()).limit(1))
    return last is None or now - last >= timedelta(hours=settings.run_interval_hours)


def scheduled_tick(*, db: Session | None = None, now: datetime | None = None) -> None:
    """One wake-up of the timer. Never raises, so the next tick always runs.
    ``db`` and ``now`` are for tests only."""
    own = db is None
    if own:
        db = SessionLocal(bind=get_engine())
    try:
        if not is_due(db, now or datetime.now(timezone.utc)):
            return
        outcome = run_pipeline(db, started_by=None, trigger_type=TriggerType.SCHEDULED)
        if outcome.run_id is None:
            log.info("Scheduled run skipped: %s", outcome.message)
        else:
            log.info("Scheduled run %s finished: %s", outcome.run_id, outcome.status.value)
    except Exception:
        log.exception("Scheduled tick failed")
    finally:
        if own:
            db.close()


def start_scheduler() -> BackgroundScheduler:
    """Start the hourly timer. Called by the app's lifespan, never by tests."""
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(scheduled_tick, "interval", hours=1, max_instances=1, coalesce=True)
    scheduler.start()
    log.info("Scheduler started: checks every hour whether a scheduled run is due")
    return scheduler
