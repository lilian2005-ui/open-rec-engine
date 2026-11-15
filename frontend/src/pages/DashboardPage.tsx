import { Fragment } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Icon, type IconName } from "../components/Icon";
import { LoadError, Loading } from "../components/PageState";
import { RunPipelineButton } from "../components/RunPipelineButton";
import { ScoreRing } from "../components/Score";
import { StatusBadge } from "../components/StatusBadge";
import { loadDashboard } from "../dashboard";
import { duration, formatDate, label, runErrors } from "../format";
import { useLoad } from "../hooks/useLoad";
import type { LeadListItem, PipelineRun } from "../types";

/** The five stages and the human step at the end, as on the design. */
const FLOW: Array<[IconName, string]> = [
  ["search", "Discovery"], ["file", "Understanding"], ["gauge", "Fit scoring"],
  ["leads", "Lead scoring"], ["bulb", "Draft"], ["user", "Human review"],
];

/** First screen after login: where the pipeline stands, the last run, and the best companies. */
export function DashboardPage() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(loadDashboard, "dashboard");

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error} onRetry={reload} />;

  const stats: Array<[string, number, IconName]> = [
    ["Jobs discovered", data.discovered, "jobs"],
    ["Jobs scored", data.scored, "gauge"],
    ["Qualified leads", data.qualified, "leads"],
    ["Drafts waiting for review", data.draftsWaiting, "mail"],
  ];

  return (
    <>
      <div className="page-head">
        <div><h1>Dashboard</h1><p className="sub">How the pipeline is doing and which companies to look at first.</p></div>
        <RunPipelineButton onFinished={reload} />
      </div>

      <div className="grid-4">
        {stats.map(([name, value, icon]) => (
          <div className="card stat" key={name}>
            <div className="stat-head"><span className="label">{name}</span><span className="stat-icon"><Icon name={icon} /></span></div>
            <div className="num">{value}</div>
          </div>
        ))}
      </div>

      {data.needsReview > 0 && (
        <div className="card needs-review">
          <Icon name="alert" />
          <span>Needs review</span>
          <b>{data.needsReview}</b>
          <button className="link-plain" onClick={() => navigate("/jobs?status=needs_review")}>
            View jobs <Icon name="arrowRight" />
          </button>
        </div>
      )}

      <div className="card flow dash-flow">
        {FLOW.map(([icon, name], i) => (
          <Fragment key={name}>
            {i > 0 && <Icon name="arrowRight" />}
            <span><Icon name={icon} />{name}{i === FLOW.length - 1 && <Icon name="check" />}</span>
          </Fragment>
        ))}
      </div>

      <div className="two-cols reverse">
        <div className="card">
          <div className="card-title">
            <h2><Icon name="activity" />Last pipeline run</h2>
            {data.lastRun && <StatusBadge status={data.lastRun.status} />}
          </div>
          {data.lastRun ? <LastRun run={data.lastRun} /> : <p className="empty">No runs yet. Press Run pipeline.</p>}
        </div>

        <div className="card">
          <div className="card-title">
            <h2><Icon name="leads" />Top leads</h2>
            <Link to="/leads">All leads</Link>
          </div>
          {data.topLeads.length === 0
            ? <p className="empty">No qualified companies yet.</p>
            : data.topLeads.map((lead) => <TopLead key={lead.lead_id} lead={lead} onOpen={() => navigate(`/leads/${lead.lead_id}`)} />)}
        </div>
      </div>
    </>
  );
}

function LastRun({ run }: { run: PipelineRun }) {
  const errors = runErrors(run);
  return (
    <div className="kv">
      <div><small>Run</small>#{run.run_id}</div>
      <div><small>Trigger</small>{label(run.trigger_type)}</div>
      <div><small>Started</small>{formatDate(run.started_at)}</div>
      <div>{run.started_by && <><small>Started by</small>{run.started_by}</>}</div>
      <div><small>New jobs</small>{run.jobs_new}</div>
      <div><small>Updated jobs</small>{run.jobs_updated}</div>
      <div><small>Duration</small>{duration(run.started_at, run.finished_at)}</div>
      <div><small>Errors</small>{errors.length}</div>
    </div>
  );
}

function TopLead({ lead, onOpen }: { lead: LeadListItem; onOpen: () => void }) {
  return (
    <div className="top-lead">
      <ScoreRing score={lead.lead_score} size={48} />
      <div className="grow">
        <div className="name">{lead.company_name}</div>
        <div className="muted small">{lead.qualifying_jobs} qualifying job{lead.qualifying_jobs === 1 ? "" : "s"}</div>
      </div>
      <StatusBadge status={lead.status} />
      <button className="btn" onClick={onOpen}>Open <Icon name="chevronRight" /></button>
    </div>
  );
}