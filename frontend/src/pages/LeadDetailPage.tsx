import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { LoadError, Loading } from "../components/PageState";
import { ScoreRing } from "../components/Score";
import { StatusBadge } from "../components/StatusBadge";
import { countWords, errorText, formatDate, label } from "../format";
import { useLoad } from "../hooks/useLoad";
import type { Company, ContactUpdate, Draft, LeadDetail } from "../types";

const MIN_WORDS = 120;
const MAX_WORDS = 180;

/** Lead review (FR-19 to FR-26). Approving only marks the draft: NOTHING is sent from Open Rec. */
export function LeadDetailPage() {
  const leadId = Number(useParams().leadId);
  const { data: lead, setData, error, loading, reload } = useLoad(() => api.getLead(leadId), String(leadId));

  if (loading && !lead) return <Loading />;
  if (error) {
    const notFound = error instanceof api.ApiError && error.status === 404;
    return notFound
      ? <div className="state"><p style={{ marginBottom: 12 }}>Lead not found</p><Link to="/leads">Back to leads</Link></div>
      : <LoadError error={error} onRetry={reload} />;
  }
  if (!lead) return null;

  return (
    <>
      <Link className="crumb" to="/leads">Leads ›</Link>
      <div className="page-head" style={{ alignItems: "center" }}>
        <div>
          <h1 style={{ margin: 0 }}>{lead.company_name}</h1>
          <p className="muted">{lead.qualifying_jobs} qualifying job{lead.qualifying_jobs === 1 ? "" : "s"} · best job {lead.best_job_score}</p>
        </div>
        <StatusBadge status={lead.status} />
        <ScoreRing score={lead.lead_score} caption="lead" />
      </div>

      <div className="two-cols reverse">
        <div className="stack">
          <div className="card">
            <div className="card-title"><h2><Icon name="bulb" />Why this lead</h2></div>
            <p style={{ color: "var(--text-2)" }}>{lead.reason}</p>
          </div>
          <div className="card">
            <div className="card-title"><h2><Icon name="jobs" />Suitable jobs (evidence)</h2></div>
            {lead.jobs.length === 0 ? <p className="muted">No job reaches the threshold.</p> : lead.jobs.map((j) => (
              <Link className="evidence-job" to={`/jobs/${j.job_id}`} key={j.job_id}>
                <span className="row" style={{ gap: 10, alignItems: "center" }}>
                  <span className="pill mid">{j.fit_score ?? "–"}</span><b style={{ fontWeight: 500 }} className="grow">{j.title}</b><Icon name="chevronRight" />
                </span>
                {j.fit_reason && <p className="muted small" style={{ marginTop: 4 }}>{j.fit_reason}</p>}
              </Link>
            ))}
          </div>
          {lead.history.length > 0 && (
            <div className="card">
              <div className="card-title"><h2><Icon name="history" />Score history</h2></div>
              <table>
                <thead><tr><th style={{ padding: "8px 0", background: "none" }}>Run</th><th style={{ background: "none" }}>Score</th><th style={{ background: "none" }}>Status</th></tr></thead>
                <tbody>
                  {[...lead.history].reverse().map((h) => (
                    <tr key={h.run_id}><td style={{ padding: "8px 0" }}>#{h.run_id} · {formatDate(h.created_at)}</td><td>{h.lead_score}</td><td>{h.status ? label(h.status) : "–"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <ContactCard leadId={lead.lead_id} company={lead.company} onSaved={(company) => setData({ ...lead, company })} />
        </div>

        <DraftCard lead={lead} onChange={(draft, status) => setData({ ...lead, draft, status: status ?? lead.status })} />
      </div>
    </>
  );
}

// ---------- contact ----------

function ContactCard({ leadId, company, onSaved }: { leadId: number; company: Company; onSaved: (c: Company) => void }) {
  const [open, setOpen] = useState(false);
  const has = Boolean(company.contact_name || company.contact_email);
  return (
    <div className="card">
      <div className="card-title">
        <h2><Icon name="user" />Contact <span className="muted small" style={{ fontWeight: 400 }}>(optional)</span></h2>
        <button className="btn" onClick={() => setOpen(true)}>{has ? "Edit" : "Add"}</button>
      </div>
      {has ? (
        <div className="kv">
          <div><small>Name</small>{company.contact_name ?? "–"}</div>
          <div><small>Title</small>{company.contact_title ?? "–"}</div>
          <div><small>Email</small>{company.contact_email ?? "–"}</div>
        </div>
      ) : <p className="muted">None yet — add manually.</p>}
      {open && <ContactModal leadId={leadId} company={company} onClose={() => setOpen(false)} onSaved={(c) => { onSaved(c); setOpen(false); }} />}
    </div>
  );
}

function ContactModal({ leadId, company, onClose, onSaved }: { leadId: number; company: Company; onClose: () => void; onSaved: (c: Company) => void }) {
  const [f, setF] = useState({ name: company.contact_name ?? "", title: company.contact_title ?? "", email: company.contact_email ?? "" });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    if (f.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim())) return setProblem("This email does not look right");
    const contact: ContactUpdate = { contact_name: f.name.trim() || null, contact_title: f.title.trim() || null, contact_email: f.email.trim() || null };
    setBusy(true);
    try {
      onSaved(await api.updateContact(leadId, contact));
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Contact person" subtitle="Added by hand. The AI only sees the name and title, never the email." onClose={onClose}>
      {problem && <div className="notice error">{problem}</div>}
      <div className="field"><label htmlFor="cn">Name</label><input id="cn" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
      <div className="field"><label htmlFor="ct">Title</label><input id="ct" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
      <div className="field"><label htmlFor="ce">Email</label><input id="ce" className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </Modal>
  );
}

// ---------- draft ----------

function DraftCard({ lead, onChange }: { lead: LeadDetail; onChange: (d: Draft, status?: LeadDetail["status"]) => void }) {
  const draft = lead.draft;
  const [checks, setChecks] = useState({ facts: false, tone: false });
  const [modal, setModal] = useState<"edit" | "reject" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const canRegenerate = lead.status !== "approved" && lead.status !== "not_qualified";
  const open = draft && (draft.status === "pending_review" || draft.status === "edited");

  async function act(name: string, call: () => Promise<Draft>, status?: LeadDetail["status"]) {
    setBusy(name);
    setProblem(null);
    try {
      const d = await call();
      onChange(d, status);
      setChecks({ facts: false, tone: false });
      setModal(null);
    } catch (e) {
      setProblem(name === "regenerate" && e instanceof api.ApiError && e.status >= 500
        ? "Could not write a new draft, try again" : errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
    } catch {
      setProblem("Could not copy. Select the text and copy it by hand.");
    }
  }

  if (lead.status === "not_qualified") {
    return <div className="card"><div className="card-title"><h2><Icon name="mail" />Outreach draft</h2></div><p className="muted">Not qualified companies get no draft.</p></div>;
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-title">
          <h2><Icon name="mail" />Outreach draft</h2>
          {draft && <StatusBadge status={draft.status} />}
        </div>
        {problem && <div className="notice error" role="alert">{problem}</div>}
        {!draft ? (
          <>
            <p className="muted" style={{ marginBottom: 12 }}>No draft yet. The AI writes one in the next run, or now:</p>
            <button className="btn" disabled={Boolean(busy)} onClick={() => act("regenerate", () => api.regenerateDraft(lead.lead_id), "draft_ready")}>
              <Icon name="refresh" />{busy === "regenerate" ? "Writing…" : "Write draft"}
            </button>
          </>
        ) : (
          <>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
              <span className="muted small">Version {draft.version}</span>
              <span className={`small ${draft.word_count < MIN_WORDS || draft.word_count > MAX_WORDS ? "" : "muted"}`} style={draft.word_count < MIN_WORDS || draft.word_count > MAX_WORDS ? { color: "var(--amber)" } : undefined}>
                {draft.word_count} words ({MIN_WORDS}–{MAX_WORDS})
              </span>
            </div>
            {draft.status === "rejected" && draft.review_comment && (
              <div className="notice warn"><Icon name="alert" /><div><b>Rejected</b><p>{draft.review_comment}</p></div></div>
            )}
            <small className="muted">Subject</small>
            <p style={{ fontWeight: 500, marginBottom: 12 }}>{draft.subject}</p>
            <small className="muted">Message</small>
            <div className="draft-body" style={{ marginTop: 6 }}>{draft.body}</div>
          </>
        )}
      </div>

      {draft && (
        <div className="card">
          {open ? (
            <>
              <div className="card-title"><h2><Icon name="clipboard" />Review checklist</h2></div>
              <label className="check"><input type="checkbox" checked={checks.facts} onChange={(e) => setChecks({ ...checks, facts: e.target.checked })} />Facts match the jobs</label>
              <label className="check"><input type="checkbox" checked={checks.tone} onChange={(e) => setChecks({ ...checks, tone: e.target.checked })} />Tone approved</label>
              <div className="actions">
                <button className="btn btn-danger" disabled={Boolean(busy)} onClick={() => setModal("reject")}><Icon name="x" />Reject</button>
                <button className="btn" disabled={Boolean(busy)} onClick={() => setModal("edit")}><Icon name="edit" />Edit</button>
                <button className="btn" disabled={Boolean(busy) || !canRegenerate} onClick={() => act("regenerate", () => api.regenerateDraft(lead.lead_id), "draft_ready")}>
                  <Icon name="refresh" />{busy === "regenerate" ? "Writing…" : "Regenerate"}
                </button>
                <span className="grow" />
                <button className="btn btn-primary" disabled={Boolean(busy) || !checks.facts || !checks.tone}
                  title={!checks.facts || !checks.tone ? "Tick both checks first" : undefined}
                  onClick={() => act("approve", () => api.approveDraft(draft.draft_id), "approved")}>
                  <Icon name="check" />{busy === "approve" ? "Approving…" : "Approve"}
                </button>
              </div>
            </>
          ) : draft.status === "approved" ? (
            <>
              <div className="notice success" style={{ marginBottom: 12 }}><Icon name="check" /><span>Approved{draft.reviewed_at ? ` on ${formatDate(draft.reviewed_at)}` : ""}. Copy it and send it yourself.</span></div>
              <button className="btn" onClick={copy}><Icon name="clipboard" />{copied ? "Copied" : "Copy subject and message"}</button>
            </>
          ) : (
            <>
              <p className="muted" style={{ marginBottom: 12 }}>This version was rejected. Ask the AI for a new one; your comment is used to fix it.</p>
              <button className="btn btn-primary" disabled={Boolean(busy) || !canRegenerate} onClick={() => act("regenerate", () => api.regenerateDraft(lead.lead_id), "draft_ready")}>
                <Icon name="refresh" />{busy === "regenerate" ? "Writing…" : "Regenerate"}
              </button>
            </>
          )}
          <p className="hint" style={{ marginTop: 10 }}>Approving marks the draft ready to send manually. Nothing is sent from Open Rec.</p>
        </div>
      )}

      {modal === "edit" && draft && (
        <EditModal draft={draft} busy={busy === "edit"} onClose={() => setModal(null)}
          onSave={(subject, body) => act("edit", () => api.editDraft(draft.draft_id, { subject, body }))} />
      )}
      {modal === "reject" && draft && (
        <RejectModal busy={busy === "reject"} onClose={() => setModal(null)}
          onReject={(comment) => act("reject", () => api.rejectDraft(draft.draft_id, comment), "rejected")} />
      )}
    </div>
  );
}

function EditModal({ draft, busy, onClose, onSave }: { draft: Draft; busy: boolean; onClose: () => void; onSave: (s: string, b: string) => void }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const words = countWords(body);
  const ok = subject.trim().length > 0 && subject.length <= 150 && body.trim().length > 0;
  return (
    <Modal title="Edit draft" subtitle="Your changes are saved as this version, with the status Edited." onClose={onClose}>
      <div className="field"><label htmlFor="subj">Subject</label><input id="subj" className="input" maxLength={150} value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
      <div className="field">
        <label htmlFor="body">Message</label>
        <textarea id="body" className="input" rows={14} value={body} onChange={(e) => setBody(e.target.value)} />
        <p className="hint" style={words < MIN_WORDS || words > MAX_WORDS ? { color: "var(--amber)" } : undefined}>{words} words (the AI writes {MIN_WORDS}–{MAX_WORDS}; your edit can be any length)</p>
      </div>
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={!ok || busy} onClick={() => onSave(subject, body)}>{busy ? "Saving…" : "Save changes"}</button>
      </div>
    </Modal>
  );
}

function RejectModal({ busy, onClose, onReject }: { busy: boolean; onClose: () => void; onReject: (comment: string) => void }) {
  const [comment, setComment] = useState("");
  return (
    <Modal title="Reject this draft?" subtitle="Say what is wrong. Regenerate uses your comment to write a better version." onClose={onClose}>
      <div className="field">
        <label htmlFor="why">Reason (required)</label>
        <textarea id="why" className="input" rows={4} maxLength={1000} placeholder="For example: too formal, start with Hello" value={comment} onChange={(e) => setComment(e.target.value)} />
      </div>
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-danger" disabled={!comment.trim() || busy} onClick={() => onReject(comment.trim())}><Icon name="x" />{busy ? "Rejecting…" : "Reject"}</button>
      </div>
    </Modal>
  );
}
