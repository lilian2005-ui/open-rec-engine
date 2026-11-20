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
from backend.pipeline.schedule import LOCAL_TZ, is_due, scheduled_tick
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


# ---------- P1-7b: every day at run_at_hour, Gaza time ----------

WINTER = (2026, 11, 20)     # Asia/Gaza = UTC+2
SUMMER = (2026, 7, 15)      # Asia/Gaza = UTC+3


def gaza(hour: int, minute: int = 0, day=WINTER) -> datetime:
    """A Gaza wall-clock time, given to is_due in UTC like the real timer does."""
    return datetime(*day, hour, minute, tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def add_started(db, started_at: datetime, trigger=TriggerType.SCHEDULED) -> PipelineRun:
    """A finished run that started at this time."""
    run = PipelineRun(trigger_type=trigger, status=RunStatus.COMPLETED, started_at=started_at,
                      finished_at=started_at + timedelta(minutes=5))
    db.add(run)
    db.flush()
    return run


@pytest.fixture
def daily(scheduled):
    set_setting(scheduled, "run_at_hour", "7")
    return scheduled


def test_daily_not_due_at_6_59(daily):
    assert is_due(daily, gaza(6, 59)) is False


def test_daily_due_at_7_05_when_no_run_today(daily):
    add_started(daily, gaza(7, 5) - timedelta(days=1))     # yesterday's run does not count
    assert is_due(daily, gaza(7, 5)) is True


def test_daily_does_not_run_again_at_9_after_a_run_at_7_05(daily):
    add_started(daily, gaza(7, 5))
    assert is_due(daily, gaza(9, 0)) is False


def test_daily_a_manual_run_at_8_counts_so_no_run_at_10(daily):
    add_started(daily, gaza(8, 0), trigger=TriggerType.MANUAL)
    assert is_due(daily, gaza(10, 0)) is False


def test_daily_server_awake_at_3_pm_runs_today(daily):
    add_started(daily, gaza(15, 0) - timedelta(days=1))
    assert is_due(daily, gaza(15, 0)) is True


def test_daily_ignores_run_interval_hours(daily):
    add_started(daily, gaza(6, 0))       # finished 1 hour before: the interval rule says no
    assert is_due(daily, gaza(7, 5)) is True


def test_daily_not_due_while_a_run_is_running(daily):
    daily.add(PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING,
                          started_at=gaza(6, 50)))
    daily.flush()
    assert is_due(daily, gaza(7, 5)) is False


def test_daily_summer_7_in_gaza_is_4_utc(daily):
    assert gaza(7, day=SUMMER).hour == 4
    assert is_due(daily, datetime(*SUMMER, 3, 59, tzinfo=timezone.utc)) is False
    assert is_due(daily, datetime(*SUMMER, 4, 5, tzinfo=timezone.utc)) is True


def test_daily_winter_7_in_gaza_is_5_utc(daily):
    assert gaza(7).hour == 5
    assert is_due(daily, datetime(*WINTER, 4, 59, tzinfo=timezone.utc)) is False
    assert is_due(daily, datetime(*WINTER, 5, 5, tzinfo=timezone.utc)) is True


def test_run_at_hour_none_keeps_the_interval_rule(scheduled):
    set_setting(scheduled, "run_at_hour", "none")
    add_run(scheduled, 5)
    assert is_due(scheduled, NOW) is False


def test_run_at_hour_none_is_due_after_the_interval(scheduled):
    set_setting(scheduled, "run_at_hour", "none")
    add_run(scheduled, 33)
    assert is_due(scheduled, NOW) is True


def test_run_at_hour_default_is_none_and_none_text_reads_as_none():
    assert AppSettings().run_at_hour is None
    assert ("run_at_hour", "none") in AppSettings().to_rows()
    assert AppSettings.from_rows({"run_at_hour": "none"}).run_at_hour is None
    assert AppSettings.from_rows({"run_at_hour": "7"}).run_at_hour == 7


@pytest.mark.parametrize("hour", [-1, 24])
def test_run_at_hour_outside_0_to_23_is_rejected(hour):
    with pytest.raises(ValidationError):
        AppSettings(run_at_hour=hour)


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
