"""P2-3 fix: POST /pipeline/run, GET /pipeline/runs, GET /pipeline/runs/{run_id},
and execute_run (the background part). Real PostgreSQL (``db`` of conftest.py);
never Himalayas or Gemini."""
from datetime import timedelta

from sqlalchemy import select

from backend.api.main import app
from backend.api.routes.pipeline import get_run_executor
from backend.db.models import PipelineRun
from backend.db.models.enums import RunStatus, TriggerType
from backend.fit.scorer import FakeFitScorer
from backend.pipeline.runner import STAGES, execute_run, open_run
from backend.tests.api_fixtures import NOW, admin, client, reviewer  # noqa: F401
from backend.tests.test_pipeline_runner import RoutingFakeLLM, seeded  # noqa: F401

RUN_KEYS = {"run_id", "status", "trigger_type", "started_by", "started_at", "finished_at",
            "jobs_fetched", "jobs_new", "jobs_updated", "errors"}


def use_executor() -> list[int]:
    """Instead of the real run, remember which run_id would have been executed."""
    started: list[int] = []
    app.dependency_overrides[get_run_executor] = lambda: started.append
    return started


def add_run(db, started_at, status=RunStatus.COMPLETED, by=None) -> PipelineRun:
    run = PipelineRun(trigger_type=TriggerType.MANUAL if by else TriggerType.SCHEDULED,
                      status=status, started_by=by.user_id if by else None,
                      started_at=started_at,
                      finished_at=None if status == RunStatus.RUNNING else started_at,
                      errors=None if status == RunStatus.RUNNING
                      else {"stages": [{"stage": "discovery", "result": "0 fetched"}],
                            "errors": []})
    db.add(run)
    db.flush()
    return run


# ---------- POST /pipeline/run ----------

def test_admin_starts_a_run_and_gets_202_at_once(client, admin, db):
    started = use_executor()

    response = client.post("/pipeline/run")

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert response.json() == {"run_id": run_id}
    run = db.get(PipelineRun, run_id)
    assert (run.status, run.trigger_type, run.started_by) == (
        RunStatus.RUNNING, TriggerType.MANUAL, admin.user_id)
    assert started == [run_id]                     # handed to the background task


def test_reviewer_cannot_start_a_run(client, reviewer, db):
    started = use_executor()

    assert client.post("/pipeline/run").status_code == 403
    assert started == [] and db.scalars(select(PipelineRun)).all() == []


def test_second_run_while_one_is_running_is_409(client, admin, db):
    started = use_executor()
    assert client.post("/pipeline/run").status_code == 202

    response = client.post("/pipeline/run")

    assert response.status_code == 409
    assert response.json() == {"detail": "A run is already in progress"}
    assert len(started) == 1


# ---------- GET /pipeline/runs ----------

def test_runs_newest_first_with_the_contract_shape(client, admin, db):
    old = add_run(db, NOW - timedelta(days=2))
    new = add_run(db, NOW, by=admin)

    response = client.get("/pipeline/runs")

    assert response.status_code == 200
    runs = response.json()
    assert [r["run_id"] for r in runs] == [new.run_id, old.run_id]
    assert set(runs[0]) == RUN_KEYS
    assert runs[0]["started_by"] == admin.full_name          # the name, not the id
    assert runs[1]["started_by"] is None                     # scheduled
    assert runs[0]["started_at"] == "2026-11-14T12:00:00Z"
    assert runs[0]["errors"] == {"stages": [{"stage": "discovery", "result": "0 fetched"}],
                                 "errors": []}


def test_runs_limit(client, reviewer, db):
    for days in range(5):
        add_run(db, NOW - timedelta(days=days))

    assert len(client.get("/pipeline/runs?limit=3").json()) == 3
    assert client.get("/pipeline/runs?limit=0").status_code == 422
    assert client.get("/pipeline/runs?limit=101").status_code == 422


# ---------- GET /pipeline/runs/{run_id} ----------

def test_one_run_while_it_is_running(client, reviewer, db):
    run = add_run(db, NOW, status=RunStatus.RUNNING)

    body = client.get(f"/pipeline/runs/{run.run_id}").json()

    assert (body["status"], body["finished_at"], body["errors"]) == ("running", None, None)


def test_unknown_run_is_404(client, reviewer, db):
    response = client.get("/pipeline/runs/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


# ---------- execute_run (the background part) ----------

def test_execute_run_runs_the_stages_and_closes_the_run(db, seeded):  # noqa: F811
    run = open_run(db, None, TriggerType.MANUAL, NOW)

    execute_run(run.run_id, db=db, raw_jobs=seeded, scorer=FakeFitScorer(default_score=80),
                call=RoutingFakeLLM())

    db.refresh(run)
    assert run.status != RunStatus.RUNNING and run.finished_at is not None
    assert [s["stage"] for s in run.errors["stages"]] == list(STAGES)
    assert run.jobs_fetched == len(seeded)


def test_execute_run_with_gemini_down_still_closes_the_run(db, seeded):  # noqa: F811
    run = open_run(db, None, TriggerType.MANUAL, NOW)

    execute_run(run.run_id, db=db, raw_jobs=seeded, scorer=FakeFitScorer(default_score=80),
                call=RoutingFakeLLM(fail=True))

    db.refresh(run)
    assert run.status == RunStatus.PARTIAL and "stages" in run.errors


def test_execute_run_ignores_a_run_that_is_not_running(db):
    run = add_run(db, NOW)                         # already completed

    execute_run(run.run_id, db=db)                 # no stage runs, no network

    db.refresh(run)
    assert run.status == RunStatus.COMPLETED
