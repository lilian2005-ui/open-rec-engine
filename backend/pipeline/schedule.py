"""P1-7: the scheduled run.

The timer wakes up every 15 minutes and asks the database whether a run is due. The
database remembers the last run, so restarting the server never resets the count.
``run_mode = manual`` turns it off at once, without a restart.

P1-7b: with ``run_at_hour`` set, the run starts once a day at that hour, Gaza time,
instead of every ``run_interval_hours``.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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

# run_at_hour is Gaza time, so 7 stays 7 in summer (UTC+3) and winter (UTC+2)
LOCAL_TZ = ZoneInfo("Asia/Gaza")


def is_due(db: Session, now: datetime) -> bool:
    """True when a scheduled run should start now.

    The last run is the latest one that finished (manual or scheduled, any status).
    Never due while a run is running: a run longer than an hour would otherwise be
    closed as stuck by the next run_pipeline while it is still going.
    With ``run_at_hour`` set, the daily rule decides and run_interval_hours is ignored.
    """
    settings = load_settings(db)
    if settings.run_mode != TriggerType.SCHEDULED:
        return False
    if db.scalar(select(PipelineRun.run_id).where(PipelineRun.status == RunStatus.RUNNING)
                 .limit(1)) is not None:
        return False
    if settings.run_at_hour is not None:
        return daily_run_is_due(db, now, settings.run_at_hour)
    last =db.scalar(select(PipelineRun.finished_at)
                     .where(PipelineRun.finished_at.is_not(None))
                     .order_by(PipelineRun.finished_at.desc()).limit(1))
    return last is None or now - last >= timedelta(hours=settings.run_interval_hours)


def daily_run_is_due(db: Session, now: datetime, hour: int) -> bool:
    """Due once the clock in Gaza has passed today's hour, if no run (manual or
    scheduled) has started since then. A server that wakes up late still runs today."""
    slot = now.astimezone(LOCAL_TZ).replace(hour=hour, minute=0, second=0, microsecond=0)
    if now < slot:
        return False
    started_since = db.scalar(select(PipelineRun.run_id)
                              .where(PipelineRun.started_at >= slot).limit(1))
    return started_since is None


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
    """Start the 15-minute timer. Called by the app's lifespan, never by tests."""
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(scheduled_tick, "interval", minutes=15, max_instances=1, coalesce=True)
    scheduler.start()
    log.info("Scheduler started: checks every 15 minutes whether a scheduled run is due")
    return scheduler
