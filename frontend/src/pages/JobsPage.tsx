import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as api from "../api";
import { Icon } from "../components/Icon";
import { LoadError } from "../components/PageState";
import { RunPipelineButton } from "../components/RunPipelineButton";
import { ScorePill } from "../components/Score";
import { StatusBadge } from "../components/StatusBadge";
import { timeAgo } from "../format";
import { useLoad } from "../hooks/useLoad";
import type { JobStatus } from "../types";

const PAGE_SIZE = 20;
const STATUSES: Array<[JobStatus | "", string]> = [
  ["", "All statuses"], ["scored", "Scored"], ["parsed", "Parsed"], ["needs_review", "Needs review"],
  ["failed", "Failed"], ["discovered", "Discovered"],
];

/** Job feed (FR-28): search, status filter and pages are kept in the URL, so Back works. */
export function JobsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as JobStatus | "";
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1);
  const [search, setSearch] = useState(q);

  // wait until the user stops typing for 300 ms, then search
  useEffect(() => {
    const t = setTimeout(() => {
      if (search !== q) update({ q: search, page: "1" });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) if (v) next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  }

  const { data, error, loading, reload } = useLoad(
    () => api.getJobs({ status, q, page, page_size: PAGE_SIZE }), `${status}|${q}|${page}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <div className="page-head">
        <div><h1>Jobs</h1><p className="sub">Remote job posts found by the pipeline, newest first.</p></div>
        <RunPipelineButton onFinished={reload} />
      </div>
      <div className="tools">
        <label className="search">
          <Icon name="search" />
          <input className="input" placeholder="Search by title or company" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search jobs" />
        </label>
        <select className="input" value={status} onChange={(e) => update({ status: e.target.value, page: "1" })} aria-label="Filter by status">
          {STATUSES.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select>
      </div>
      <div className="card table-card">
        {error ? <LoadError error={error} onRetry={reload} /> : (
          <>
            <div className="scroll-x"><table>
              <thead><tr><th>Title</th><th>Company</th><th>Fit score</th><th>Status</th><th className="right">Posted</th></tr></thead>
              <tbody style={{ opacity: loading ? 0.5 : 1 }}>
                {data?.items.map((job) => (
                  <tr key={job.job_id} className="clickable" onClick={() => navigate(`/jobs/${job.job_id}`)}>
                    <td><b style={{ fontWeight: 500 }}>{job.title}</b></td>
                    <td className="muted">{job.company_name}</td>
                    <td><ScorePill score={job.fit_score} /></td>
                    <td><StatusBadge status={job.status} /></td>
                    <td className="right muted">{timeAgo(job.posted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            {data && data.total === 0 && (
              <p className="empty">{q || status ? "No jobs match your search." : "No jobs yet. Run the pipeline."}</p>
            )}
            {!data && loading && <p className="empty">Loading…</p>}
            {data && data.total > 0 && (
              <div className="pager">
                <span>{data.total} jobs · page {page} of {pages}</span>
                <span className="row">
                  <button className="btn" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}><Icon name="chevronLeft" />Previous</button>
                  <button className="btn" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>Next<Icon name="chevronRight" /></button>
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
