import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { Icon } from "../components/Icon";
import { LoadError, Loading } from "../components/PageState";
import { ScoreRing } from "../components/Score";
import { StatusBadge } from "../components/StatusBadge";
import { useLoad } from "../hooks/useLoad";
import type { LeadListItem, LeadStatus } from "../types";

const STATUSES: Array<[LeadStatus | "", string]> = [
  ["", "All statuses"], ["qualified", "Qualified"], ["draft_ready", "Draft ready"],
  ["approved", "Approved"], ["rejected", "Rejected"],
];

async function loadLeads() {
  // 100 is the biggest page the backend gives; filtering and search happen here
  const [leads, settings] = await Promise.all([api.getLeads({ page_size: 100 }), api.getSettings().catch(() => null)]);
  return { leads: leads.items, threshold: settings?.lead_threshold ?? 60 };
}

/** Leads (FR-17, FR-18): companies best first, with the reason in one line. */
export function LeadsPage() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(loadLeads, "leads");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<LeadStatus | "">("");
  const [order, setOrder] = useState<"high" | "low">("high");
  const [showNotQualified, setShowNotQualified] = useState(false);

  const { shown, notQualified } = useMemo(() => {
    const text = search.trim().toLowerCase();
    const match = (l: LeadListItem) => !text || l.company_name.toLowerCase().includes(text);
    const all = (data?.leads ?? []).filter(match);
    const sorted = all
      .filter((l) => l.status !== "not_qualified" && (!status || l.status === status))
      .sort((a, b) => (order === "high" ? b.lead_score - a.lead_score : a.lead_score - b.lead_score));
    return { shown: sorted, notQualified: all.filter((l) => l.status === "not_qualified") };
  }, [data, search, status, order]);

  if (loading && !data) return <Loading />;
  if (error) return <LoadError error={error} onRetry={reload} />;

  return (
    <>
      <div className="page-head"><div><h1>Leads</h1><p className="sub">Companies hiring roles Simera talent can fill, best first.</p></div></div>
      <div className="notice info"><Icon name="info" /><span>Lead score = best suitable job + 5 per extra suitable job (max 100). A job is suitable when its fit score ≥ <b>{data?.threshold}</b>.</span></div>
      <div className="tools">
        <label className="search"><Icon name="search" /><input className="input" placeholder="Search by company" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search leads" /></label>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as LeadStatus | "")} aria-label="Filter by status">
          {STATUSES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
        </select>
        <select className="input" value={order} onChange={(e) => setOrder(e.target.value as "high" | "low")} aria-label="Order">
          <option value="high">Lead score: high to low</option>
          <option value="low">Lead score: low to high</option>
        </select>
      </div>

      {shown.length === 0 && <div className="card empty">{search || status ? "No companies match your search." : "No qualified companies yet. Run the pipeline."}</div>}
      {shown.map((l, i) => (
        <div className="card lead-item" key={l.lead_id} onClick={() => navigate(`/leads/${l.lead_id}`)}>
          <span className="rank">{i + 1}</span>
          <div className="grow">
            <div className="name">{l.company_name}</div>
            <div className="muted small">{l.qualifying_jobs} qualifying job{l.qualifying_jobs === 1 ? "" : "s"} · best job {l.best_job_score}</div>
            <p className="why"><b>Why:</b> {l.reason}</p>
          </div>
          <ScoreRing score={l.lead_score} />
          <StatusBadge status={l.status} />
          <button className="btn">Open <Icon name="chevronRight" /></button>
        </div>
      ))}

      {notQualified.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <button className="link-btn muted" style={{ color: "var(--muted)" }} onClick={() => setShowNotQualified(!showNotQualified)}>
            <Icon name={showNotQualified ? "chevronDown" : "chevronRight"} /> Not qualified ({notQualified.length})
          </button>
          {showNotQualified && (
            <div className="card table-card" style={{ marginTop: 10 }}>
              <table><tbody>
                {notQualified.map((l) => (
                  <tr key={l.lead_id} className="clickable" onClick={() => navigate(`/leads/${l.lead_id}`)}>
                    <td style={{ width: 240 }}><b style={{ fontWeight: 500 }}>{l.company_name}</b></td>
                    <td className="muted">{l.reason}</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          )}
        </div>
      )}
    </>
  );
}
