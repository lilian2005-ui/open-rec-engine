import { Fragment, useState } from "react";
import * as api from "../api";
import { Icon } from "../components/Icon";
import { LoadError, Loading } from "../components/PageState";
import { RunPipelineButton } from "../components/RunPipelineButton";
import { StatusBadge } from "../components/StatusBadge";
import { duration, errorText, formatDate, label, runErrors, runStages } from "../format";
import { useLoad } from "../hooks/useLoad";
import type { PipelineRun, Settings } from "../types";

/** Settings and run log (FR-06, FR-29 to FR-32). Admins only; API keys stay in .env, never here. */
export function SettingsPage() {
  const settings = useLoad(() => api.getSettings(), "settings");
  const runs = useLoad(() => api.getRuns(10), "runs");

  return (
    <>
      <div className="page-head">
        <div><h1>Settings</h1><p className="sub">Tune the pipeline and review past runs. Admins only.</p></div>
      </div>
      <div className="row wrap-mobile" style={{ alignItems: "flex-start" }}>
        <div className="card fixed-340">
          <div className="card-title"><h2><Icon name="sliders" />Pipeline settings</h2></div>
          {settings.loading && !settings.data ? <Loading /> : settings.error ? <LoadError error={settings.error} onRetry={settings.reload} />
            : settings.data && <SettingsForm initial={settings.data} onSaved={settings.setData} lastRun={runs.data?.[0] ?? null} />}
        </div>
        <div className="card table-card grow">
          <div className="card-title" style={{ padding: "18px 20px 6px" }}>
            <h2><Icon name="history" />Run log</h2>
            <RunPipelineButton onFinished={runs.reload} />
          </div>
          {runs.loading && !runs.data ? <Loading /> : runs.error ? <LoadError error={runs.error} onRetry={runs.reload} />
            : <div className="scroll-x"><RunLog runs={runs.data ?? []} /></div>}
        </div>
      </div>
    </>
  );
}

function SettingsForm({ initial, onSaved, lastRun }: { initial: Settings; onSaved: (s: Settings) => void; lastRun: PipelineRun | null }) {
  const [form, setForm] = useState(initial);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const changed = (Object.keys(form) as Array<keyof Settings>).filter((k) => form[k] !== initial[k]);
  const problem = api.settingsProblem(form);
  const numberField = (key: "lead_threshold" | "fetch_limit" | "max_retries" | "run_interval_hours") => ({
    type: "number", className: "input", value: Number.isNaN(form[key]) ? "" : (form[key] ?? ""),
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value === "" ? NaN : Number(e.target.value) }),
  });

  async function save() {
    if (problem) return setMessage({ ok: false, text: problem });
    const changes = Object.fromEntries(changed.map((k) => [k, form[k]])) as Partial<Settings>;
    setBusy(true);
    try {
      const saved = await api.updateSettings(changes);
      onSaved(saved);
      setMessage({ ok: true, text: "Saved" });
    } catch (e) {
      setMessage({ ok: false, text: errorText(e) }); // the values stay in the form
    } finally {
      setBusy(false);
    }
  }

  const nextRun = form.run_mode === "scheduled" && lastRun?.finished_at && form.run_interval_hours
    ? new Date(new Date(lastRun.finished_at).getTime() + form.run_interval_hours * 3_600_000).toISOString() : null;

  return (
    <>
      {message && <div className={`notice ${message.ok ? "success" : "error"}`} role="status">{message.text}</div>}
      <div className="field">
        <label className="toggle"><span>Himalayas source</span>
          <input type="checkbox" checked={form.himalayas_enabled} onChange={(e) => setForm({ ...form, himalayas_enabled: e.target.checked })} aria-label="Himalayas source" />
        </label>
        <p className="hint">The only job source.</p>
      </div>
      <div className="field"><label htmlFor="thr">Lead threshold (0–100)</label><input id="thr" min={0} max={100} {...numberField("lead_threshold")} /><p className="hint">Changing it affects the next run.</p></div>
      <div className="field"><label htmlFor="lim">Jobs per run (1–500)</label><input id="lim" min={1} max={500} {...numberField("fetch_limit")} /></div>
      <div className="field">
        <label htmlFor="mode">Run mode</label>
        <select id="mode" className="input" value={form.run_mode} onChange={(e) => setForm({ ...form, run_mode: e.target.value as Settings["run_mode"] })}>
          <option value="manual">Manual (Run pipeline button)</option>
          <option value="scheduled">Scheduled</option>
        </select>
      </div>
      {form.run_mode === "scheduled" && form.run_interval_hours !== undefined && (
        <div className="field">
          <label htmlFor="every">Run every (hours)</label><input id="every" min={1} max={168} {...numberField("run_interval_hours")} />
          {nextRun && <p className="hint">Next run: about {formatDate(nextRun)}</p>}
        </div>
      )}
      <div className="field"><label htmlFor="ret">Retries on error (0–5)</label><input id="ret" min={0} max={5} {...numberField("max_retries")} /></div>
      <button className="btn btn-primary btn-block" onClick={save} disabled={busy || changed.length === 0}>{busy ? "Saving…" : "Save"}</button>
    </>
  );
}

function RunLog({ runs }: { runs: PipelineRun[] }) {
  const [open, setOpen] = useState<number | null>(runs[0]?.run_id ?? null);
  if (runs.length === 0) return <p className="empty">No runs yet. Press Run pipeline.</p>;
  return (
    <table className="runlog">
      <thead><tr><th>Run</th><th>Trigger</th><th>Status</th><th>Started</th><th>Duration</th><th className="right">New jobs</th><th className="right">Errors</th></tr></thead>
      <tbody>
        {runs.map((run) => {
          const isOpen = open === run.run_id;
          const stages = runStages(run);
          const errors = runErrors(run);
          return (
            <Fragment key={run.run_id}>
              <tr className={`clickable${isOpen ? " run-open" : ""}`} onClick={() => setOpen(isOpen ? null : run.run_id)}>
                <td><Icon name={isOpen ? "chevronDown" : "chevronRight"} /> #{run.run_id}</td>
                <td>{run.trigger_type === "scheduled" ? "Scheduled" : `${label(run.trigger_type)}${run.started_by ? ` · ${run.started_by.split(" ")[0]}` : ""}`}</td>
                <td><StatusBadge status={run.status} /></td>
                <td className="muted">{formatDate(run.started_at)}</td>
                <td className="muted">{duration(run.started_at, run.finished_at)}</td>
                <td className="right">{run.jobs_new}</td>
                <td className="right">{errors.length}</td>
              </tr>
              {isOpen && (
                <tr><td colSpan={7} style={{ padding: 0 }}>
                  {stages.length > 0 ? (
                    <table className="stages"><tbody>
                      {stages.map((s) => <tr key={s.stage}><td>{s.stage}</td><td>{s.result}</td></tr>)}
                    </tbody></table>
                  ) : (
                    <p className="muted small" style={{ padding: "10px 20px" }}>{run.jobs_fetched} fetched, {run.jobs_new} new, {run.jobs_updated} updated.</p>
                  )}
                  {errors.map((e, i) => <p className="run-error" key={i}>✕ {e.stage ? `${e.stage}: ` : ""}{e.message}</p>)}
                  <p className="muted small" style={{ padding: "4px 20px 12px" }}>One failed job or stage never stops the rest of the run.</p>
                </td></tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
