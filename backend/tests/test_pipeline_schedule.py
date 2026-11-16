"""P1-7: the scheduled run. Real PostgreSQL (the ``db`` fixture rolls everything back).
The timer itself never starts here: is_due and scheduled_tick are called directly,
with ``now`` as an argument, so nothing waits."""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from backend.api.main import app
from backend.db.models import AppSetting, PipelineRun
from backend.db.models.enums import RunStatus, TriggerType
from backend.discovery.service import DiscoveryResult
from backend.drafts.service import DraftRunResult
from backend.fit.service import FitRunResult
from backend.leads.service import LeadRunResult
from backend.pipeline import runner, schedule
from backend.pipeline.schedule import is_due, scheduled_tick
from backend.schemas.settings import AppSettings
from backend.understanding.service import UnderstandingResult

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def set_setting(db, key: str, value: str) -> None:
    db.merge(AppSetting(key=key, value=value))
    db.flush()


def add_run(db, finished_hours_ago: float | None, status=RunStatus.COMPLETED,
            trigger=TriggerType.MANUAL) -> PipelineRun:
    """A run that finished this many hours before NOW (None = still running)."""
    if finished_hours_ago is None:
        run = PipelineRun(trigger_type=trigger, status=RunStatus.RUNNING,
                          started_at=NOW - timedelta(minutes=10))
    else:
        finished = NOW - timedelta(hours=finished_hours_ago)
        run = PipelineRun(trigger_type=trigger, status=status,
                          started_at=finished - timedelta(minutes=5), finished_at=finished)
    db.add(run)
    db.flush()
    return run


@pytest.fixture
def scheduled(db):
    set_setting(db, "run_mode", "scheduled")
    return db


@pytest.fixture
def no_stages(monkeypatch):
    """The five stages do nothing: no Himalayas, no Gemini."""
    monkeypatch.setattr(runner, "discover", lambda db, run_id, client=None, raw_jobs=None:
                        DiscoveryResult())
    monkeypatch.setattr(runner, "understand_jobs", lambda db, call, limit: UnderstandingResult())
    monkeypatch.setattr(runner, "score_parsed_jobs", lambda db, scorer: FitRunResult())
    monkeypatch.setattr(runner, "score_leads", lambda db, run_id, call: LeadRunResult())
    monkeypatch.setattr(runner, "create_drafts", lambda db, call, limit: DraftRunResult())
    monkeypatch.setattr(runner, "GeminiFitScorer", lambda call_llm: None)


def runs(db) -> list[PipelineRun]:
    return list(db.scalars(select(PipelineRun).order_by(PipelineRun.run_id)))


# ---------- is_due ----------

def test_manual_mode_is_never_due(db):
    add_run(db, 100)
    assert is_due(db, NOW) is False


def test_due_when_the_last_run_finished_33_hours_ago(scheduled):
    add_run(scheduled, 33)
    assert is_due(scheduled, NOW) is True


def test_not_due_when_the_last_run_finished_5_hours_ago(scheduled):
    add_run(scheduled, 5)
    assert is_due(scheduled, NOW) is False


def test_due_when_there_was_no_run_before(scheduled):
    assert is_due(scheduled, NOW) is True


def test_the_latest_finished_run_counts_manual_or_failed(scheduled):
    add_run(scheduled, 100, trigger=TriggerType.SCHEDULED)
    add_run(scheduled, 2, status=RunStatus.FAILED, trigger=TriggerType.MANUAL)
    assert is_due(scheduled, NOW) is False


def test_not_due_while_a_run_is_running(scheduled):
    add_run(scheduled, 40)
    add_run(scheduled, None)
    assert is_due(scheduled, NOW) is False


def test_interval_24_changes_the_result_without_code_changes(scheduled):
    add_run(scheduled, 25)
    assert is_due(scheduled, NOW) is False          # default 32
    set_setting(scheduled, "run_interval_hours", "24")
    assert is_due(scheduled, NOW) is True


def test_exactly_the_interval_is_due(scheduled):
    add_run(scheduled, 32)
    assert is_due(scheduled, NOW) is True


# ---------- the setting ----------

def test_interval_default_is_32():
    assert AppSettings().run_interval_hours == 32


@pytest.mark.parametrize("hours", [0, 169])
def test_interval_outside_1_to_168_is_rejected(hours):
    with pytest.raises(ValidationError):
        AppSettings(run_interval_hours=hours)


# ---------- scheduled_tick ----------

def test_tick_starts_a_scheduled_run_with_no_user(scheduled, no_stages):
    old = add_run(scheduled, 33)

    scheduled_tick(db=scheduled, now=NOW)

    new = [r for r in runs(scheduled) if r.run_id != old.run_id]
    assert len(new) == 1
    assert new[0].trigger_type == TriggerType.SCHEDULED
    assert new[0].started_by is None
    assert new[0].status == RunStatus.COMPLETED


def test_tick_does_nothing_when_not_due(scheduled, no_stages):
    add_run(scheduled, 5)
    scheduled_tick(db=scheduled, now=NOW)
    assert len(runs(scheduled)) == 1


def test_tick_does_not_start_a_second_run_and_does_not_raise(scheduled, no_stages):
    add_run(scheduled, 40)
    running = add_run(scheduled, None)

    scheduled_tick(db=scheduled, now=NOW)

    assert len(runs(scheduled)) == 2
    assert scheduled.get(PipelineRun, running.run_id).status == RunStatus.RUNNING


def test_tick_logs_a_skipped_run_as_info(scheduled, monkeypatch, caplog):
    """is_due said yes, but another run started in between: run_pipeline answers
    run_id None. That is info, not an error."""
    monkeypatch.setattr(schedule, "run_pipeline", lambda db, started_by, trigger_type:
                        runner.PipelineOutcome(run_id=None, status=None,
                                               message=runner.ALREADY_RUNNING))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        scheduled_tick(db=scheduled, now=NOW)

    [record] = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert record.levelno == logging.INFO
    assert runner.ALREADY_RUNNING in record.getMessage()


def test_an_unexpected_error_is_logged_and_the_next_tick_still_runs(scheduled, monkeypatch,
                                                                    caplog):
    calls = []

    def broken(db, started_by, trigger_type):
        calls.append(trigger_type)
        raise RuntimeError("database went away")

    monkeypatch.setattr(schedule, "run_pipeline", broken)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        scheduled_tick(db=scheduled, now=NOW)       # does not raise
        scheduled_tick(db=scheduled, now=NOW)

    assert calls == [TriggerType.SCHEDULED, TriggerType.SCHEDULED]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2
    assert all(r.exc_info for r in errors)          # with the traceback


# ---------- the timer never starts in tests ----------

def test_testclient_without_with_does_not_start_the_scheduler(monkeypatch):
    started = []
    monkeypatch.setattr(schedule, "start_scheduler", lambda: started.append(1))

    TestClient(app).get("/openapi.json")             # how every API test builds its client

    assert started == []
