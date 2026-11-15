"""Run the whole pipeline once from the terminal (P1-6).

    python -m backend.pipeline.run              # all jobs
    python -m backend.pipeline.run --limit 3    # small run: at most 3 jobs understood
                                                # and 3 drafts (saves Gemini requests)
"""
import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.config import settings  # noqa: F401 — triggers .env load
from backend.db.models import Lead
from backend.db.models.enums import RunStatus, TriggerType
from backend.db.session import SessionLocal, get_engine
from backend.pipeline.runner import PipelineOutcome, run_pipeline

REASON_WIDTH = 50


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all five pipeline stages once.")
    parser.add_argument("--limit", type=int, default=None,
                        help="at most this many jobs understood and drafts written")
    parser.add_argument("--top", type=int, default=10,
                        help="how many companies to print (default 10)")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be 1 or more")
    return args


def ranked_leads(db: Session, run_id: int, top: int) -> list[Lead]:
    """The companies scored in this run, best first. Same lead score -> the one with
    the higher best fit first (so scored companies come before unscored ones)."""
    return list(db.scalars(
        select(Lead)
        .where(Lead.run_id == run_id)
        .options(selectinload(Lead.company))
        .order_by(Lead.lead_score.desc(), Lead.best_job_score.desc(), Lead.lead_id)
        .limit(top)
    ).all())


def count_leads(db: Session, run_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Lead).where(Lead.run_id == run_id))


def short(text: str, width: int = REASON_WIDTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def format_report(outcome: PipelineOutcome, leads: list[Lead], total: int | None = None) -> str:
    """The text printed after a run: status, one line per stage, errors, companies."""
    if outcome.run_id is None:
        return outcome.message or "The run did not start."

    lines = [f"Run {outcome.run_id}: {outcome.status.value}", ""]
    for stage in outcome.stages:
        lines.append(f"  {stage['stage']:<14} {stage['result']}")

    if outcome.errors:
        lines += ["", f"Errors ({len(outcome.errors)}):"]
        for err in outcome.errors:
            lines.append(f"  [{err['stage']}] {short(err['message'], 80)}")

    lines.append("")
    if not leads:
        lines.append("No companies were scored in this run.")
    else:
        lines.append(f"Top {len(leads)} of {total if total is not None else len(leads)} companies:")
    for i, lead in enumerate(leads, start=1):
        lines.append(f"{i:>2}. {short(lead.company.name, 24):<24} {lead.lead_score:>3}  "
                     f"{lead.status.value:<13} \"{short(lead.reason)}\"")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db = SessionLocal(bind=get_engine())
    try:
        outcome = run_pipeline(db, started_by=None, trigger_type=TriggerType.MANUAL,
                               limit=args.limit)
        leads = ranked_leads(db, outcome.run_id, args.top) if outcome.run_id else []
        total = count_leads(db, outcome.run_id) if outcome.run_id else 0
        print(format_report(outcome, leads, total))
    finally:
        db.close()

    if outcome.run_id is None or outcome.status == RunStatus.FAILED:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
