"""Pipeline routes (P2-3): the "Run pipeline" button and the run log."""
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.api.deps import get_current_user, require_admin
from backend.api.schemas import PipelineRunOut, RunStarted
from backend.db.models import AppUser, PipelineRun
from backend.db.models.enums import TriggerType
from backend.db.session import get_db
from backend.pipeline.runner import ALREADY_RUNNING, close_stuck_runs, execute_run, open_run

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_run_executor() -> Callable[[int], None]:
    """What runs the stages in the background. Tests replace it through
    app.dependency_overrides, so they never call Himalayas or Gemini."""
    return execute_run


@router.post("/run", response_model=RunStarted, status_code=202)
def start_run(background: BackgroundTasks, db: Session = Depends(get_db),
              user: AppUser = Depends(require_admin),
              executor: Callable[[int], None] = Depends(get_run_executor)):
    """Open a run and answer at once: a run takes minutes. The page then asks
    GET /pipeline/runs/{run_id} until it is no longer running."""
    now = datetime.now(timezone.utc)
    close_stuck_runs(db, now)
    run = open_run(db, user.user_id, TriggerType.MANUAL, now)
    if run is None:
        raise HTTPException(409, ALREADY_RUNNING)
    background.add_task(executor, run.run_id)
    return RunStarted(run_id=run.run_id)


@router.get("/runs", response_model=list[PipelineRunOut],
            dependencies=[Depends(get_current_user)])
def list_runs(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """The latest runs, newest first."""
    return db.scalars(
        select(PipelineRun).options(selectinload(PipelineRun.started_by_user))
        .order_by(PipelineRun.started_at.desc(), PipelineRun.run_id.desc())
        .limit(limit)
    ).all()


@router.get("/runs/{run_id}", response_model=PipelineRunOut,
            dependencies=[Depends(get_current_user)])
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run
