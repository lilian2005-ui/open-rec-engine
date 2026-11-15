"""P1-6: the command ``python -m backend.pipeline.run`` (arguments and printed report)."""
from datetime import datetime, timezone

import pytest

from backend.db.models import Company, Lead, PipelineRun
from backend.db.models.enums import LeadStatus, RunStatus, TriggerType
from backend.db.normalize import company_name_key
from backend.pipeline.run import count_leads, format_report, parse_args, ranked_leads
from backend.pipeline.runner import ALREADY_RUNNING, PipelineOutcome

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def make_lead(name, score, status=LeadStatus.QUALIFIED, reason="3 profiles cover react",
              best=None):
    return Lead(company=Company(name=name, normalized_name=company_name_key(name)),
                lead_score=score, best_job_score=score if best is None else best, qualifying_jobs=1, status=status,
                reason=reason, evidence={"job_ids": []}, scored_at=NOW)


# ---------- arguments ----------

def test_limit_is_optional():
    assert parse_args([]).limit is None
    assert parse_args(["--limit", "3"]).limit == 3


def test_limit_must_be_positive():
    with pytest.raises(SystemExit):
        parse_args(["--limit", "0"])


# ---------- report ----------

def test_report_when_a_run_is_already_in_progress():
    outcome = PipelineOutcome(run_id=None, status=None, message=ALREADY_RUNNING)

    assert format_report(outcome, []) == ALREADY_RUNNING


def test_report_lists_stages_errors_and_companies():
    outcome = PipelineOutcome(
        run_id=7, status=RunStatus.PARTIAL,
        stages=[{"stage": "discovery", "result": "100 fetched, 12 new"},
                {"stage": "understanding", "result": "crashed"}],
        errors=[{"stage": "understanding", "message": "Gemini quota exceeded"}])
    leads = [make_lead("Acme Corp", 97, LeadStatus.DRAFT_READY),
             make_lead("Helix AI", 86)]

    report = format_report(outcome, leads, total=217)

    assert report.startswith("Run 7: partial")
    assert "Top 2 of 217 companies:" in report
    assert "discovery      100 fetched, 12 new" in report
    assert "[understanding] Gemini quota exceeded" in report
    assert " 1. Acme Corp" in report and "draft_ready" in report
    assert " 2. Helix AI" in report


def test_report_says_when_no_company_was_scored():
    outcome = PipelineOutcome(run_id=8, status=RunStatus.COMPLETED)

    assert "No companies were scored in this run." in format_report(outcome, [])


def test_long_reasons_are_cut():
    outcome = PipelineOutcome(run_id=9, status=RunStatus.COMPLETED)
    report = format_report(outcome, [make_lead("Acme", 90, reason="word " * 40)])

    assert "..." in report


# ---------- ranking (database) ----------

def test_ranked_leads_are_this_runs_companies_best_first(db):
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED,
                      started_at=NOW, finished_at=NOW)
    other = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED,
                        started_at=NOW, finished_at=NOW)
    db.add_all([run, other])
    db.flush()
    low, high, top = make_lead("Low Co", 40), make_lead("High Co", 90), make_lead("Old Co", 99)
    low.run_id, high.run_id, top.run_id = run.run_id, run.run_id, other.run_id
    db.add_all([low, high, top])
    db.flush()

    leads = ranked_leads(db, run.run_id, top=10)

    assert [lead.company.name for lead in leads] == ["High Co", "Low Co"]
    assert len(ranked_leads(db, run.run_id, top=1)) == 1


def test_same_lead_score_puts_the_higher_fit_first(db):
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED,
                      started_at=NOW, finished_at=NOW)
    db.add(run)
    db.flush()
    unscored, scored = make_lead("Unscored Co", 0, best=0), make_lead("Scored Co", 0, best=40)
    unscored.run_id = scored.run_id = run.run_id
    db.add_all([unscored, scored])     # unscored first: a lower lead_id
    db.flush()

    assert [lead.company.name for lead in ranked_leads(db, run.run_id, top=10)] == [
        "Scored Co", "Unscored Co"]
    assert count_leads(db, run.run_id) == 2
