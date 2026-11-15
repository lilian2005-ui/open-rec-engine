import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import { Icon } from "../components/Icon";
import { LoadError, Loading } from "../components/PageState";
import { ScoreRing } from "../components/Score";
import { StatusBadge } from "../components/StatusBadge";
import { errorText, formatSalary, formatTimezones, label } from "../format";
import { useLoad } from "../hooks/useLoad";
import type { EmploymentType, JobRequirements, RemotePolicy, RequirementsUpdate, SalaryPeriod, Seniority } from "../types";
import { parseList, parseOffsets, requirementsProblems } from "../validation";

/** A value or "Not stated". Never "0" or empty: what the posting does not say stays empty. */
function Value({ children }: { children: ReactNode }) {
  return children == null || children === "" || children === false ? <span className="not-stated">Not stated</span> : <>{children}</>;
}

/** Job detail (FR-11, FR-12): the original posting next to what the AI extracted. */
export function JobDetailPage() {
  const jobId = Number(useParams().jobId);
  const { data: job, setData, error, loading, reload } = useLoad(() => api.getJob(jobId), String(jobId));
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);

  if (loading && !job) return <Loading />;
  if (error) {
    const notFound = error instanceof api.ApiError && error.status === 404;
    return notFound
      ? <div className="state"><p style={{ marginBottom: 12 }}>Job not found</p><Link to="/jobs">Back to jobs</Link></div>
      : <LoadError error={error} onRetry={reload} />;
  }
  if (!job) return null;
  const r = job.requirements;

  return (
    <>
      <Link className="crumb" to="/jobs">Jobs ›</Link>
      <div className="page-head" style={{ alignItems: "center" }}>
        <div><h1 style={{ margin: 0 }}>{job.title} <span className="muted" style={{ fontWeight: 400 }}>· {job.company_name}</span></h1></div>
        <StatusBadge status={job.status} />
      </div>

      {r?.flag_reason && (
        <div className="notice warn"><Icon name="alert" /><div><b>Flagged for human review</b><p>{r.flag_reason}. Check the posting and correct the fields with Edit fields.</p></div></div>
      )}
      {saved && <div className="notice success"><Icon name="check" />Saved. The job will be scored again in the next run.</div>}

      <div className="two-cols">
        <div className="card">
          <div className="card-title"><h2><Icon name="file" />Job description</h2></div>
          <p className="description">{job.description_text || "No description."}</p>
          <p className="divider"><a href={job.url} target="_blank" rel="noreferrer">View original on Himalayas <Icon name="external" className="icon" /></a></p>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-title"><h2><Icon name="gauge" />Fit</h2></div>
            {r?.fit_score != null ? (
              <div className="row" style={{ alignItems: "center" }}>
                <ScoreRing score={r.fit_score} size={86} caption="of 100" />
                <p style={{ color: "var(--text-2)" }}>{r.fit_reason}</p>
              </div>
            ) : (
              <p className="muted">
                {job.status === "needs_review" || job.status === "failed"
                  ? "Not scored. Jobs that need review or failed are not counted for any lead."
                  : "Not scored yet. It will be scored in the next run."}
              </p>
            )}
          </div>

          <div className="card">
            {!r ? (
              <>
                <div className="card-title"><h2><Icon name="list" />Extracted requirements</h2></div>
                <p className="muted">{job.status === "failed" ? "The AI could not read this posting. It will be tried again in the next run." : "Not analysed yet. It will be analysed in the next run."}</p>
              </>
            ) : editing ? (
              <RequirementsForm requirements={r} onCancel={() => setEditing(false)} onSave={async (changes) => {
                const updated = await api.updateRequirements(job.job_id, changes);
                setData(updated);
                setEditing(false);
                setSaved(true);
              }} />
            ) : (
              <>
                <div className="card-title">
                  <h2><Icon name="list" />Extracted requirements</h2>
                  <button className="btn" onClick={() => { setEditing(true); setSaved(false); }}><Icon name="edit" />Edit fields</button>
                </div>
                <div className="kv">
                  <div><small>Title</small><Value>{r.title ?? job.title}</Value></div>
                  <div><small>Seniority</small><Value>{r.seniority && label(r.seniority)}</Value></div>
                  <div><small>Min years experience</small><Value>{r.min_years_experience != null && `${r.min_years_experience}+ years`}</Value></div>
                  <div><small>Timezone</small><Value>{formatTimezones(r.timezone_offsets)}</Value></div>
                  <div><small>Employment type</small><Value>{r.employment_type && label(r.employment_type)}</Value></div>
                  <div><small>Remote policy</small><Value>{r.remote_policy && label(r.remote_policy)}</Value></div>
                  <div><small>Salary</small><Value>{formatSalary(r)}</Value></div>
                </div>
                <div className="divider">
                  <small className="muted">Required skills</small>
                  <div style={{ marginTop: 6 }}>{r.required_skills.length ? r.required_skills.map((s) => <span className="chip" key={s}>{s}</span>) : <p className="not-stated" style={{ marginBottom: 8 }}>Not stated</p>}</div>
                  <small className="muted">Nice-to-have skills</small>
                  <div style={{ marginTop: 6 }}>{r.preferred_skills.length ? r.preferred_skills.map((s) => <span className="chip outline" key={s}>{s}</span>) : <p className="not-stated">Not stated</p>}</div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

const SENIORITY: Seniority[] = ["entry", "mid", "senior", "lead"];
const EMPLOYMENT: EmploymentType[] = ["full_time", "part_time", "contractor", "other"];
const REMOTE: RemotePolicy[] = ["remote", "hybrid", "onsite"];
const PERIOD: SalaryPeriod[] = ["hourly", "weekly", "fortnightly", "monthly", "annual"];

function Choice<T extends string>({ id, value, options, onChange }: { id: string; value: T | null; options: T[]; onChange: (v: T | null) => void }) {
  return (
    <select id={id} className="input" value={value ?? ""} onChange={(e) => onChange((e.target.value || null) as T | null)}>
      <option value="">Not stated</option>
      {options.map((o) => <option key={o} value={o}>{label(o)}</option>)}
    </select>
  );
}

/** Edit what the AI extracted. Checked in the browser with the backend limits before saving. */
function RequirementsForm({ requirements: r, onSave, onCancel }: {
  requirements: JobRequirements; onSave: (c: RequirementsUpdate) => Promise<void>; onCancel: () => void;
}) {
  const [f, setF] = useState({
    required: r.required_skills.join(", "), preferred: r.preferred_skills.join(", "),
    seniority: r.seniority, years: r.min_years_experience?.toString() ?? "",
    offsets: (r.timezone_offsets ?? []).join(", "), employment: r.employment_type, remote: r.remote_policy,
    salaryMin: r.salary_min?.toString() ?? "", salaryMax: r.salary_max?.toString() ?? "",
    currency: r.salary_currency ?? "", period: r.salary_period,
  });
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const num = (text: string) => (text.trim() === "" ? null : Number(text));

  async function save() {
    const offsets = parseOffsets(f.offsets);
    const changes: RequirementsUpdate = {
      required_skills: parseList(f.required), preferred_skills: parseList(f.preferred),
      seniority: f.seniority, min_years_experience: num(f.years), timezone_offsets: offsets ?? [],
      employment_type: f.employment, remote_policy: f.remote,
      salary_min: num(f.salaryMin), salary_max: num(f.salaryMax),
      salary_currency: f.currency.trim() ? f.currency.trim().toUpperCase() : null, salary_period: f.period,
    };
    const found = requirementsProblems(changes);
    if (offsets === null) found.push("Timezones must be whole hours from -12 to 14, for example -5, -4");
    setProblems(found);
    if (found.length) return;
    setBusy(true);
    try {
      await onSave(changes);
    } catch (e) {
      setProblems([errorText(e)]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card-title"><h2><Icon name="edit" />Edit requirements</h2></div>
      {problems.length > 0 && <div className="notice error" role="alert"><div>{problems.map((p) => <p key={p}>{p}</p>)}</div></div>}
      <div className="field"><label htmlFor="req">Required skills (comma separated)</label><input id="req" className="input" value={f.required} onChange={(e) => setF({ ...f, required: e.target.value })} /></div>
      <div className="field"><label htmlFor="pref">Nice-to-have skills</label><input id="pref" className="input" value={f.preferred} onChange={(e) => setF({ ...f, preferred: e.target.value })} /></div>
      <div className="row">
        <div className="field grow"><label htmlFor="sen">Seniority</label><Choice id="sen" value={f.seniority} options={SENIORITY} onChange={(v) => setF({ ...f, seniority: v })} /></div>
        <div className="field grow"><label htmlFor="yrs">Min years</label><input id="yrs" className="input" type="number" min={0} max={50} value={f.years} onChange={(e) => setF({ ...f, years: e.target.value })} /></div>
      </div>
      <div className="row">
        <div className="field grow"><label htmlFor="emp">Employment type</label><Choice id="emp" value={f.employment} options={EMPLOYMENT} onChange={(v) => setF({ ...f, employment: v })} /></div>
        <div className="field grow"><label htmlFor="rem">Remote policy</label><Choice id="rem" value={f.remote} options={REMOTE} onChange={(v) => setF({ ...f, remote: v })} /></div>
      </div>
      <div className="field"><label htmlFor="tz">Timezones (UTC offsets)</label><input id="tz" className="input" placeholder="-5, -4" value={f.offsets} onChange={(e) => setF({ ...f, offsets: e.target.value })} /></div>
      <div className="row">
        <div className="field grow"><label htmlFor="smin">Salary min</label><input id="smin" className="input" type="number" min={0} value={f.salaryMin} onChange={(e) => setF({ ...f, salaryMin: e.target.value })} /></div>
        <div className="field grow"><label htmlFor="smax">Salary max</label><input id="smax" className="input" type="number" min={0} value={f.salaryMax} onChange={(e) => setF({ ...f, salaryMax: e.target.value })} /></div>
      </div>
      <div className="row">
        <div className="field grow"><label htmlFor="cur">Currency</label><input id="cur" className="input" placeholder="USD" maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })} /></div>
        <div className="field grow"><label htmlFor="per">Period</label><Choice id="per" value={f.period} options={PERIOD} onChange={(v) => setF({ ...f, period: v })} /></div>
      </div>
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
      <p className="hint">After saving, the job goes back to Parsed and is scored again in the next run.</p>
    </>
  );
}
