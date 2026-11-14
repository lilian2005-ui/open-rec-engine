"""P1-6: the pipeline runner. Runs on real PostgreSQL (the ``db`` fixture rolls
everything back after each test)."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

import pytest

from backend.db.models import JobPosting, Lead, OutreachDraft, PipelineRun
from backend.db.models.enums import LeadStatus, RunStatus, TriggerType
from backend.db.seed_candidates import load_profiles, seed
from backend.discovery.fetch import SourceFetchError
from backend.discovery.service import DiscoveryResult
from backend.drafts.service import DraftRunResult
from backend.fit.scorer import FakeFitScorer
from backend.fit.service import FitRunResult
from backend.leads.service import LeadRunResult
from backend.pipeline import runner
from backend.pipeline.runner import (ALREADY_RUNNING, STAGES, RunLog, close_stuck_runs,
                                     final_status, open_run, run_pipeline, run_stage,
                                     stage_errors)
from backend.understanding.service import UnderstandingResult

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class FakeStages:
    """Replaces the five stage functions inside the runner. Records the order they
    were called in and what they got. ``fail`` = names of stages that raise."""

    def __init__(self, fail=(), discovery=None):
        self.calls = []
        self.fail = set(fail)
        self.discovery = discovery or DiscoveryResult(fetched=10, new=4, updated=1, unchanged=5)

    def _step(self, name, result, **kwargs):
        self.calls.append((name, kwargs))
        if name in self.fail:
            raise RuntimeError(f"{name} broke")
        return result

    def install(self, monkeypatch):
        monkeypatch.setattr(runner, "discover",
                            lambda db, run_id, client=None, raw_jobs=None:
                            self._step("discovery", self.discovery))
        monkeypatch.setattr(runner, "understand_jobs",
                            lambda db, call, limit: self._step(
                                "understanding", UnderstandingResult(parsed=3), limit=limit))
        monkeypatch.setattr(runner, "score_parsed_jobs",
                            lambda db, scorer: self._step("fit", FitRunResult(scored=3)))
        monkeypatch.setattr(runner, "score_leads",
                            lambda db, run_id, call: self._step(
                                "leads", LeadRunResult(qualified=1, not_qualified=2)))
        monkeypatch.setattr(runner, "create_drafts",
                            lambda db, call, limit: self._step(
                                "drafts", DraftRunResult(created=1), limit=limit))
        return self


@pytest.fixture
def stages(monkeypatch):
    return FakeStages().install(monkeypatch)


def add_running(db, started_at):
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING,
                      started_at=started_at)
    db.add(run)
    db.flush()
    return run


# ---------- phase 1: open the run ----------

def test_open_run_inserts_a_running_row(db):
    run = open_run(db, None, TriggerType.SCHEDULED, NOW)

    assert run is not None
    saved = db.get(PipelineRun, run.run_id)
    assert saved.status == RunStatus.RUNNING
    assert saved.trigger_type == TriggerType.SCHEDULED
    assert saved.started_by is None
    assert saved.finished_at is None


def test_second_run_is_rejected_while_one_is_running(db):
    first = add_running(db, NOW - timedelta(minutes=5))   # recent: not stuck

    outcome = run_pipeline(db, None, now=NOW)

    assert outcome.run_id is None
    assert outcome.message == ALREADY_RUNNING
    # the first run is untouched and no second row was saved
    assert db.get(PipelineRun, first.run_id).status == RunStatus.RUNNING
    assert db.scalars(select(PipelineRun)).all() == [first]


def test_stuck_run_is_closed_as_failed(db):
    stuck = add_running(db, NOW - timedelta(hours=2))

    closed = close_stuck_runs(db, NOW)

    assert closed == 1
    assert stuck.status == RunStatus.FAILED
    assert stuck.finished_at == NOW
    assert stuck.errors["errors"][0]["stage"] == "runner"


def test_new_run_starts_after_a_stuck_run(db, stages):
    stuck = add_running(db, NOW - timedelta(hours=2))

    outcome = run_pipeline(db, None, now=NOW)

    assert outcome.message is None
    assert outcome.run_id != stuck.run_id
    assert db.get(PipelineRun, stuck.run_id).status == RunStatus.FAILED


def test_run_younger_than_one_hour_is_not_stuck(db):
    recent = add_running(db, NOW - timedelta(minutes=59))

    assert close_stuck_runs(db, NOW) == 0
    assert recent.status == RunStatus.RUNNING


# ---------- phase 2: the stages ----------

def test_run_stage_returns_the_result_and_a_summary_line(db):
    runlog = RunLog()

    result = run_stage(db, runlog, "fit", lambda: FitRunResult(scored=4, errors=["job 9: bad"]),
                       lambda r: f"{r.scored} scored")

    assert result.scored == 4
    assert runlog.stages == [{"stage": "fit", "result": "4 scored"}]
    assert runlog.errors == [{"stage": "fit", "message": "job 9: bad"}]
    assert runlog.crashed == []


def test_run_stage_catches_a_crash(db):
    runlog = RunLog()

    def boom():
        raise RuntimeError("no candidates")

    assert run_stage(db, runlog, "fit", boom, str) is None
    assert runlog.crashed == ["fit"]
    assert runlog.stages == [{"stage": "fit", "result": "crashed"}]
    assert runlog.errors == [{"stage": "fit", "message": "no candidates"}]


def test_stage_errors_gives_one_shape_for_every_stage():
    understanding = UnderstandingResult(errors=[{"stage": "understanding", "job_id": 5,
                                                 "attempts": 3, "message": "timeout"}])
    fetch_error = SourceFetchError("himalayas", 2, "http_status", 503, 3, "server error")
    discovery = DiscoveryResult(fetched=20, error=fetch_error)
    drafts = DraftRunResult(errors=["lead 7: draft rejected"])

    assert stage_errors("understanding", understanding) == [
        {"stage": "understanding", "job_id": 5, "attempts": 3, "message": "timeout"}]
    [d] = stage_errors("discovery", discovery)
    assert d["stage"] == "discovery" and d["message"] == "server error" and d["page"] == 2
    assert stage_errors("drafts", drafts) == [
        {"stage": "drafts", "message": "lead 7: draft rejected"}]


def test_five_stages_run_in_order(db, stages):
    outcome = run_pipeline(db, None, now=NOW)

    assert [name for name, _ in stages.calls] == [
        "discovery", "understanding", "fit", "leads", "drafts"]
    assert [s["stage"] for s in outcome.stages] == [
        "discovery", "understanding", "fit", "leads", "drafts"]
    assert outcome.stages[0]["result"] == "10 fetched, 4 new, 1 updated, 5 unchanged, 0 skipped"
    assert outcome.errors == []


def test_limit_goes_to_understanding_and_drafts_only(db, stages):
    run_pipeline(db, None, limit=3, now=NOW)

    kwargs = dict(stages.calls)
    assert kwargs["understanding"] == {"limit": 3}
    assert kwargs["drafts"] == {"limit": 3}


def test_discovery_counts_are_saved_on_the_run(db, stages):
    outcome = run_pipeline(db, None, now=NOW)

    run = db.get(PipelineRun, outcome.run_id)
    db.refresh(run)
    assert (run.jobs_fetched, run.jobs_new, run.jobs_updated) == (10, 4, 1)


def test_a_crashing_stage_does_not_stop_the_others(db, monkeypatch):
    fake = FakeStages(fail={"understanding"}).install(monkeypatch)

    outcome = run_pipeline(db, None, now=NOW)

    assert [name for name, _ in fake.calls] == [
        "discovery", "understanding", "fit", "leads", "drafts"]
    assert outcome.stages[1] == {"stage": "understanding", "result": "crashed"}
    assert outcome.errors == [{"stage": "understanding", "message": "understanding broke"}]


def test_discovery_error_is_recorded_and_the_run_goes_on(db, monkeypatch):
    error = SourceFetchError("himalayas", 3, "http_status", 503, 3, "server error")
    fake = FakeStages(discovery=DiscoveryResult(fetched=40, new=40, error=error))
    fake.install(monkeypatch)

    outcome = run_pipeline(db, None, now=NOW)

    assert len(fake.calls) == 5
    [err] = outcome.errors
    assert err["stage"] == "discovery" and err["message"] == "server error"
    # the pages before the failure were kept
    run = db.get(PipelineRun, outcome.run_id)
    db.refresh(run)
    assert run.jobs_fetched == 40


# ---------- phase 3: close the run ----------

def test_final_status_rules():
    assert final_status(RunLog()) == RunStatus.COMPLETED
    assert final_status(RunLog(errors=[{"stage": "fit", "message": "x"}])) == RunStatus.PARTIAL
    assert final_status(RunLog(crashed=["fit"],
                               errors=[{"stage": "fit", "message": "x"}])) == RunStatus.PARTIAL
    assert final_status(RunLog(crashed=list(STAGES),
                               errors=[{"stage": s, "message": "x"} for s in STAGES])
                        ) == RunStatus.FAILED


def saved_run(db, outcome):
    run = db.get(PipelineRun, outcome.run_id)
    db.refresh(run)
    return run


def test_clean_run_is_completed_and_saved(db, stages):
    outcome = run_pipeline(db, None, now=NOW)

    run = saved_run(db, outcome)
    assert outcome.status == run.status == RunStatus.COMPLETED
    assert run.finished_at is not None
    assert [s["stage"] for s in run.errors["stages"]] == list(STAGES)
    assert run.errors["errors"] == []


def test_a_failing_stage_makes_the_run_partial(db, monkeypatch):
    FakeStages(fail={"understanding"}).install(monkeypatch)

    outcome = run_pipeline(db, None, now=NOW)

    run = saved_run(db, outcome)
    assert run.status == RunStatus.PARTIAL
    assert run.errors["errors"] == [{"stage": "understanding", "message": "understanding broke"}]


def test_himalayas_failure_makes_the_run_partial(db, monkeypatch):
    error = SourceFetchError("himalayas", 1, "http_status", 503, 3, "server error")
    FakeStages(discovery=DiscoveryResult(error=error)).install(monkeypatch)

    outcome = run_pipeline(db, None, now=NOW)

    run = saved_run(db, outcome)
    assert run.status == RunStatus.PARTIAL
    assert run.errors["errors"][0]["stage"] == "discovery"
    assert run.finished_at is not None


def test_every_stage_crashing_makes_the_run_failed(db, monkeypatch):
    FakeStages(fail=set(STAGES)).install(monkeypatch)

    outcome = run_pipeline(db, None, now=NOW)

    run = saved_run(db, outcome)
    assert run.status == RunStatus.FAILED
    assert len(run.errors["errors"]) == 5


def test_a_new_run_can_start_after_one_finishes(db, stages):
    first = run_pipeline(db, None, now=NOW)
    second = run_pipeline(db, None, now=NOW + timedelta(minutes=1))

    assert second.message is None
    assert second.run_id != first.run_id


# ---------- phase 5: a full run with the real stages (no network) ----------

SAMPLE_FILE = Path(__file__).resolve().parents[2] / "data" / "samples" / "himalayas.json"
CANDIDATES_FILE = Path(__file__).resolve().parents[2] / "data" / "candidates.json"


class RoutingFakeLLM:
    """A fake Gemini for a whole run: it reads which stage is asking and answers
    with a valid JSON for that stage. ``fail=True`` raises on every call."""

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = {"understanding": 0, "leads": 0, "drafts": 0}

    def __call__(self, prompt, response_schema):
        if self.fail:
            raise RuntimeError("Gemini is down")
        if "You extract structured requirements" in prompt:
            self.calls["understanding"] += 1
            return json.dumps({"title": "Software Engineer", "required_skills": ["react"],
                               "seniority": "senior", "min_years_experience": 3})
        if "reason why a company" in prompt:
            self.calls["leads"] += 1
            return json.dumps({"reason": "2 suitable roles, both with fit 80."})
        self.calls["drafts"] += 1
        company = json.loads(re.search(r"^COMPANY: (.*)$", prompt, re.M).group(1))
        role = json.loads(re.search(r"^ROLES: (.*)$", prompt, re.M).group(1))[0]["title"]
        text = (f"Hello {company} team,\nI noticed you are hiring a {role}. "
                + "talent " * 140 + "Would you be open to a short call?")
        return json.dumps({"subject": f"Talent for your {role} role", "body": text})


@pytest.fixture
def seeded(db):
    seed(db, load_profiles(CANDIDATES_FILE))
    db.commit()
    return json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))["jobs"]


def test_full_run_gives_draft_ready_companies_with_drafts(db, seeded):
    llm = RoutingFakeLLM()

    outcome = run_pipeline(db, None, raw_jobs=seeded, scorer=FakeFitScorer(default_score=80),
                           call=llm)

    assert outcome.errors == [], outcome.errors
    assert outcome.status == RunStatus.COMPLETED
    run = db.get(PipelineRun, outcome.run_id)
    db.refresh(run)
    assert run.jobs_fetched == len(seeded) and run.jobs_new > 0
    leads = db.scalars(select(Lead).where(Lead.run_id == outcome.run_id)).all()
    ready = [lead for lead in leads if lead.status == LeadStatus.DRAFT_READY]
    assert ready, [lead.status for lead in leads]
    assert db.scalar(select(func.count()).select_from(OutreachDraft)) == len(ready)
    assert llm.calls["drafts"] >= len(ready)


def test_full_run_with_limit_understands_and_drafts_only_that_many(db, seeded):
    llm = RoutingFakeLLM()

    run_pipeline(db, None, limit=2, raw_jobs=seeded, scorer=FakeFitScorer(default_score=80),
                 call=llm)

    assert llm.calls["understanding"] == 2
    assert db.scalar(select(func.count()).select_from(OutreachDraft)) <= 2


def test_full_run_with_gemini_down_is_partial_and_does_not_crash(db, seeded):
    outcome = run_pipeline(db, None, raw_jobs=seeded, scorer=FakeFitScorer(default_score=80),
                           call=RoutingFakeLLM(fail=True))

    assert outcome.status == RunStatus.PARTIAL
    assert {e["stage"] for e in outcome.errors} == {"understanding"}
    # discovery still saved the jobs
    assert db.scalar(select(func.count()).select_from(JobPosting)) == len(seeded)


# ---------- a run stopped in the middle ----------

def test_ctrl_c_closes_the_run_as_failed_and_a_new_run_can_start(db, monkeypatch):
    fake = FakeStages().install(monkeypatch)

    def interrupted(db, scorer):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "score_parsed_jobs", interrupted)

    with pytest.raises(KeyboardInterrupt):
        run_pipeline(db, None, now=NOW)

    run = db.scalars(select(PipelineRun)).one()
    assert run.status == RunStatus.FAILED
    assert run.finished_at is not None
    assert [s["stage"] for s in run.errors["stages"]] == ["discovery", "understanding"]
    assert run.errors["errors"][-1]["stage"] == "runner"
    # not blocked for an hour: the next run starts right away
    fake.install(monkeypatch)
    assert run_pipeline(db, None, now=NOW).message is None
