"""P1-6: run all five stages in order and record the run in ``pipeline_run``.

The same function is called by the CLI (``python -m backend.pipeline.run``), by the
"Run pipeline" button (P2-3) and by the scheduler (P1-7, ``started_by=None`` and
``trigger_type=TriggerType.SCHEDULED``).
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import PipelineRun
from backend.db.models.enums import RunStatus, TriggerType
from backend.discovery.himalayas import discover
from backend.discovery.service import DiscoveryResult
from backend.drafts.service import DraftRunResult, create_drafts
from backend.fit.scorer import GeminiFitScorer
from backend.fit.service import FitRunResult, score_parsed_jobs
from backend.leads.service import LeadRunResult, score_leads
from backend.llm import call_llm as shared_call_llm
from backend.understanding.service import UnderstandingResult, understand_jobs

log = logging.getLogger(__name__)

STUCK_AFTER = timedelta(hours=1)
ALREADY_RUNNING = "A run is already in progress"
STAGES = ("discovery", "understanding", "fit", "leads", "drafts")


@dataclass
class PipelineOutcome:
    """What ``run_pipeline`` returns. ``run_id`` is None when no run was started."""
    run_id: int | None
    status: RunStatus | None
    message: str | None = None
    stages: list[dict[str, str]] = field(default_factory=list)   # one line per stage
    errors: list[dict[str, Any]] = field(default_factory=list)   # every error, with its stage


@dataclass
class RunLog:
    """What happened in each stage, while the run is going."""
    stages: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    crashed: list[str] = field(default_factory=list)   # stages that raised and did nothing


# ---------- 1. open the run ----------

def close_stuck_runs(db: Session, now: datetime) -> int:
    """Mark every ``running`` run older than one hour as ``failed``.

    A run stays ``running`` forever if the server dies in the middle of it, and the
    one-running index would then block every new run. Returns how many were closed.
    """
    stuck = db.scalars(
        select(PipelineRun).where(PipelineRun.status == RunStatus.RUNNING,
                                  PipelineRun.started_at < now - STUCK_AFTER)
    ).all()
    for run in stuck:
        run.status = RunStatus.FAILED
        run.finished_at = now
        run.errors = {"stages": [],
                      "errors": [{"stage": "runner",
                                  "message": "Closed as stuck: still running after one hour"}]}
    db.commit()
    return len(stuck)


def open_run(db: Session, started_by: int | None, trigger_type: TriggerType,
             now: datetime) -> PipelineRun | None:
    """Insert a ``running`` row. Returns None if another run is already running.

    No check is written here: the database index ``uq_pipeline_run_one_running``
    rejects the second row, even if two requests arrive at the same moment.
    """
    run = PipelineRun(status=RunStatus.RUNNING, trigger_type=trigger_type,
                      started_by=started_by, started_at=now)
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return run


# ---------- 2. the stages ----------

def stage_errors(stage: str, result: Any) -> list[dict[str, Any]]:
    """The errors of one stage result, all in one shape: ``{"stage": ..., "message": ...}``.

    Each stage reports errors its own way: discovery has one ``error`` object,
    understanding has a list of dicts, the others have a list of strings.
    """
    raw: list[Any] = list(getattr(result, "errors", []) or [])
    single = getattr(result, "error", None)
    if single is not None:
        raw.append(single.to_dict() if hasattr(single, "to_dict") else str(single))

    out = []
    for err in raw:
        if isinstance(err, dict):
            out.append({**err, "stage": stage, "message": str(err.get("message", err))})
        else:
            out.append({"stage": stage, "message": str(err)})
    return out


def run_stage(db: Session, runlog: RunLog, name: str, func: Callable[[], Any],
              summarize: Callable[[Any], str]) -> Any:
    """Run one stage. If it raises, undo its unsaved changes, record the error and
    return None, so the next stage still runs on whatever is in the database."""
    try:
        result = func()
    except Exception as exc:  # one stage failing must never stop the others
        db.rollback()
        log.exception("stage %s crashed", name)
        runlog.crashed.append(name)
        runlog.stages.append({"stage": name, "result": "crashed"})
        runlog.errors.append({"stage": name, "message": str(exc)})
        return None

    runlog.stages.append({"stage": name, "result": summarize(result)})
    runlog.errors.extend(stage_errors(name, result))
    return result


def _discover_and_save(db: Session, run_id: int, client, raw_jobs) -> DiscoveryResult:
    result = discover(db, run_id, client=client, raw_jobs=raw_jobs)
    # discover() leaves the commit to the caller. Commit even if result.error is set:
    # the pages fetched before the failure are saved and should be kept.
    db.commit()
    return result


def _discovery_line(d: DiscoveryResult) -> str:
    return (f"{d.fetched} fetched, {d.new} new, {d.updated} updated, "
            f"{d.unchanged} unchanged, {d.skipped} skipped")


def _understanding_line(u: UnderstandingResult) -> str:
    return f"{u.parsed} parsed, {u.needs_review} needs review, {u.failed} failed"


def _fit_line(f: FitRunResult) -> str:
    return f"{f.scored} scored"


def _leads_line(r: LeadRunResult) -> str:
    return f"{r.qualified} qualified, {r.not_qualified} not qualified"


def _drafts_line(r: DraftRunResult) -> str:
    return f"{r.created} created"


def run_stages(db: Session, run: PipelineRun, runlog: RunLog, limit: int | None, *,
               raw_jobs=None, client=None, scorer=None, call=None) -> None:
    """The five stages, in order. Each one runs even if the one before it failed."""
    call = call or shared_call_llm
    scorer = scorer or GeminiFitScorer(call_llm=call)

    d = run_stage(db, runlog, "discovery",
                  lambda: _discover_and_save(db, run.run_id, client, raw_jobs),
                  _discovery_line)
    if d is not None:
        run.jobs_fetched, run.jobs_new, run.jobs_updated = d.fetched, d.new, d.updated
        # saved now: a later stage may call db.rollback(), which would drop these
        db.commit()

    run_stage(db, runlog, "understanding",
              lambda: understand_jobs(db, call=call, limit=limit), _understanding_line)
    run_stage(db, runlog, "fit", lambda: score_parsed_jobs(db, scorer), _fit_line)
    run_stage(db, runlog, "leads", lambda: score_leads(db, run.run_id, call=call), _leads_line)
    run_stage(db, runlog, "drafts",
              lambda: create_drafts(db, call=call, limit=limit), _drafts_line)


# ---------- 3. close the run ----------

def final_status(runlog: RunLog) -> RunStatus:
    """completed = no errors; failed = every stage crashed; partial = anything between."""
    if len(runlog.crashed) == len(STAGES):
        return RunStatus.FAILED
    if runlog.errors:
        return RunStatus.PARTIAL
    return RunStatus.COMPLETED


def close_run(db: Session, run: PipelineRun, runlog: RunLog, now: datetime) -> None:
    """Save the status, the finish time and the run log (one line per stage + errors)."""
    run.status = final_status(runlog)
    run.finished_at = now
    run.errors = {"stages": runlog.stages, "errors": runlog.errors}
    db.commit()


def fail_run(db: Session, run: PipelineRun, runlog: RunLog, exc: BaseException) -> None:
    """The run stopped in the middle (Ctrl+C, a bug outside the stages...). Close it as
    ``failed`` now, so the next run is not blocked for an hour by a ``running`` row."""
    try:
        db.rollback()
        run.status = RunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.errors = {"stages": runlog.stages,
                      "errors": runlog.errors + [{"stage": "runner",
                                                  "message": f"Run stopped: {exc!r}"}]}
        db.commit()
    except Exception:  # never hide the original error; close_stuck_runs is the backup
        log.exception("could not close run %s as failed", run.run_id)


# ---------- the whole run ----------

def run_pipeline(db: Session, started_by: int | None,
                 trigger_type: TriggerType = TriggerType.MANUAL, limit: int | None = None,
                 *, raw_jobs=None, client=None, scorer=None, call=None,
                 now: datetime | None = None) -> PipelineOutcome:
    """Open a run, run the five stages, close the run.

    ``limit`` goes to understanding and drafts only. ``raw_jobs``, ``client``,
    ``scorer`` and ``call`` are for tests (sample jobs, FakeFitScorer, FakeLLM);
    when None, the real Himalayas API and Gemini are used.
    """
    now = now or datetime.now(timezone.utc)

    # ---- 1. open the run ----
    close_stuck_runs(db, now)
    run = open_run(db, started_by, trigger_type, now)
    if run is None:
        return PipelineOutcome(run_id=None, status=None, message=ALREADY_RUNNING)

    # ---- 2. the five stages, 3. close the run ----
    runlog = RunLog()
    try:
        run_stages(db, run, runlog, limit, raw_jobs=raw_jobs, client=client,
                   scorer=scorer, call=call)
        close_run(db, run, runlog, datetime.now(timezone.utc))
    except BaseException as exc:  # BaseException: Ctrl+C (KeyboardInterrupt) too
        fail_run(db, run, runlog, exc)
        raise
    return PipelineOutcome(run_id=run.run_id, status=run.status,
                           stages=runlog.stages, errors=runlog.errors)
