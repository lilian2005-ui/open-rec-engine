/**
 * The ONLY file that talks to the backend. Every screen imports from here.
 *
 * It has an internal switch between fake data and the real backend:
 *   - fake (default): answers come from src/mockData.ts, no backend needed.
 *   - real: fetch() calls to the FastAPI backend (Open_Rec_API_Contract_v1.md).
 * Change it with VITE_USE_MOCK in frontend/.env.local (see .env.example), then
 * restart `npm run dev`. The screens do not change.
 */
import { countWords } from "./format";
import {
  MOCK_COMPANIES, MOCK_DRAFTS, MOCK_JOBS, MOCK_LEADS, MOCK_RUNS, MOCK_SETTINGS, MOCK_USERS,
  type MockDraft, type MockJob, type MockLead,
} from "./mockData";
import type {
  Company, ContactUpdate, Draft, JobDetail, JobListItem, JobStatus, LeadDetail, LeadListItem, LeadStatus,
  Page, PipelineRun, RequirementsUpdate, Settings, TokenOut, User,
} from "./types";

/** true = fake data. Only the exact text "false" switches to the real backend. */
export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== "false";
const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Paths of the real backend, as in the API contract. Change them only here. */
const ENDPOINTS = {
  register: "/auth/register",
  login: "/auth/login",
  me: "/auth/me",
  jobs: "/jobs",
  job: (id: number) => `/jobs/${id}`,
  requirements: (id: number) => `/jobs/${id}/requirements`,
  leads: "/leads",
  lead: (id: number) => `/leads/${id}`,
  contact: (id: number) => `/leads/${id}/contact`,
  regenerate: (leadId: number) => `/leads/${leadId}/draft/regenerate`,
  draft: (id: number) => `/drafts/${id}`,
  approve: (id: number) => `/drafts/${id}/approve`,
  reject: (id: number) => `/drafts/${id}/reject`,
  run: "/pipeline/run",
  runs: "/pipeline/runs",
  runOne: (id: number) => `/pipeline/runs/${id}`,
  settings: "/settings",
};

// ---------- login token ----------

const TOKEN_KEY = "openrec_token";

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private window: the login lasts until the page is closed */
  }
}
function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* nothing saved */
  }
}

/** The app listens to this to go back to the login screen when the token expires. */
export const UNAUTHORIZED_EVENT = "openrec:unauthorized";

// ---------- real backend ----------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(API_URL + path, { ...init, headers });
  if (!response.ok) {
    if (response.status === 401 && path !== ENDPOINTS.login) {
      // the token expired (8 hours) or is wrong: forget it and show the login screen
      clearToken();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const text = q.toString();
  return text ? `?${text}` : "";
}

// ---------- fake backend ----------

const MOCK_DELAY_MS = 150; // small delay, so loading states can be seen and tested

/** The fake "database". A copy, so tests can reset it and screens cannot change MOCK_*. */
let db = freshMockDb();
function freshMockDb() {
  return {
    jobs: structuredClone(MOCK_JOBS) as MockJob[],
    leads: structuredClone(MOCK_LEADS) as MockLead[],
    drafts: structuredClone(MOCK_DRAFTS) as MockDraft[],
    companies: structuredClone(MOCK_COMPANIES) as Record<number, Company>,
    runs: structuredClone(MOCK_RUNS) as PipelineRun[],
    settings: structuredClone(MOCK_SETTINGS) as Settings,
    users: structuredClone(MOCK_USERS) as User[],
  };
}
/** For tests: start again from mockData.ts. */
export function resetMockData(): void {
  db = freshMockDb();
}

async function mock<T>(value: T): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  return structuredClone(value); // a copy, so a screen cannot change the fake data
}
async function mockFail(status: number, detail: string): Promise<never> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  throw new ApiError(status, JSON.stringify({ detail }));
}

function mockUserFromToken(): User | null {
  const token = getToken();
  if (!token?.startsWith("mock:")) return null;
  return db.users.find((u) => u.user_id === Number(token.slice(5))) ?? null;
}
/** 401 / 403 like the backend: null = allowed. */
function mockGuard(adminOnly = false): [number, string] | null {
  const user = mockUserFromToken();
  if (!user) return [401, "Not authenticated"];
  if (adminOnly && user.role !== "admin") return [403, "Admins only"];
  return null;
}
function paginate<T>(items: T[], page = 1, page_size = 20): Page<T> {
  const start = (page - 1) * page_size;
  return { items: items.slice(start, start + page_size), total: items.length, page, page_size };
}
const now = () => new Date().toISOString();

function jobRow(j: MockJob): JobListItem {
  return { job_id: j.job_id, title: j.title, company_name: j.company_name, source: j.source,
    posted_at: j.posted_at, status: j.status, fit_score: j.requirements?.fit_score ?? null };
}
function jobDetail(j: MockJob): JobDetail {
  return { ...jobRow(j), url: j.url, description_text: j.description_text, expires_at: j.expires_at,
    requirements: j.requirements };
}
function leadRow(l: MockLead): LeadListItem {
  return { lead_id: l.lead_id, company_name: db.companies[l.company_id].name, lead_score: l.lead_score,
    best_job_score: l.best_job_score, qualifying_jobs: l.qualifying_jobs, status: l.status, reason: l.reason };
}
function newestDraft(leadId: number): MockDraft | undefined {
  return db.drafts.filter((d) => d.lead_id === leadId).sort((a, b) => b.version - a.version)[0];
}
function publicDraft(d: MockDraft): Draft {
  const { lead_id: _leadId, ...rest } = d; // eslint-disable-line @typescript-eslint/no-unused-vars
  return rest;
}

// ---------- auth ----------

/** Log in. Real: POST login, then ask who we are. Fake: any password, the email picks the user. */
export async function login(email: string, password: string): Promise<User> {
  const cleanEmail = email.trim().toLowerCase();
  if (USE_MOCK) {
    const user = db.users.find((u) => u.email === cleanEmail);
    if (!user || !password) return mockFail(401, "Invalid email or password"); // never say which field
    setToken(`mock:${user.user_id}`);
    return mock(user);
  }
  const body = JSON.stringify({ email: cleanEmail, password });
  const token = await request<TokenOut>(ENDPOINTS.login, { method: "POST", body });
  setToken(token.access_token);
  return request<User>(ENDPOINTS.me);
}

/** Create an account. New accounts are reviewers; admins are made with create_admin. */
export async function register(full_name: string, email: string, password: string): Promise<User> {
  const cleanEmail = email.trim().toLowerCase();
  if (USE_MOCK) {
    if (db.users.some((u) => u.email === cleanEmail)) return mockFail(409, "Email already registered");
    const user: User = { user_id: Math.max(...db.users.map((u) => u.user_id)) + 1, full_name: full_name.trim(),
      email: cleanEmail, role: "reviewer", is_active: true, created_at: now() };
    db.users.push(user);
    return mock(user);
  }
  const body = JSON.stringify({ full_name: full_name.trim(), email: cleanEmail, password });
  return request<User>(ENDPOINTS.register, { method: "POST", body });
}

export async function logout(): Promise<void> {
  clearToken();
}

/** The logged-in user, or null if nobody is logged in (or the token expired). */
export async function getCurrentUser(): Promise<User | null> {
  if (!getToken()) return null;
  if (USE_MOCK) {
    const user = mockUserFromToken();
    if (!user) clearToken();
    return user ? mock(user) : null;
  }
  try {
    return await request<User>(ENDPOINTS.me);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

// ---------- jobs ----------

export interface JobQuery {
  status?: JobStatus | "";
  q?: string;
  page?: number;
  page_size?: number;
}

/** The job feed, newest first. */
export async function getJobs(params: JobQuery = {}): Promise<Page<JobListItem>> {
  const { status, q, page = 1, page_size = 20 } = params;
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const text = (q ?? "").trim().toLowerCase();
    const rows = db.jobs
      .filter((j) => !status || j.status === status)
      .filter((j) => !text || j.title.toLowerCase().includes(text) || j.company_name.toLowerCase().includes(text))
      .sort((a, b) => (b.posted_at ?? "").localeCompare(a.posted_at ?? ""))
      .map(jobRow);
    return mock(paginate(rows, page, page_size));
  }
  return request<Page<JobListItem>>(ENDPOINTS.jobs + query({ status, q, page, page_size }));
}

export async function getJob(jobId: number): Promise<JobDetail> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const j = db.jobs.find((x) => x.job_id === jobId);
    return j ? mock(jobDetail(j)) : mockFail(404, "Job not found");
  }
  return request<JobDetail>(ENDPOINTS.job(jobId));
}

/** Correct what the AI extracted (FR-12). The job goes back to "parsed" and is scored again in the next run. */
export async function updateRequirements(jobId: number, changes: RequirementsUpdate): Promise<JobDetail> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const j = db.jobs.find((x) => x.job_id === jobId);
    if (!j || !j.requirements) return mockFail(404, "Job not found or not analysed yet");
    j.requirements = { ...j.requirements, ...changes, fit_score: null, fit_reason: null, flag_reason: null };
    j.status = "parsed";
    j.fit_score = null;
    return mock(jobDetail(j));
  }
  return request<JobDetail>(ENDPOINTS.requirements(jobId), { method: "PATCH", body: JSON.stringify(changes) });
}

// ---------- leads ----------

export interface LeadQuery {
  status?: LeadStatus | "";
  page?: number;
  page_size?: number;
}

/** Companies, highest lead score first. */
export async function getLeads(params: LeadQuery = {}): Promise<Page<LeadListItem>> {
  const { status, page = 1, page_size = 20 } = params;
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const rows = db.leads
      .filter((l) => !status || l.status === status)
      .map(leadRow)
      .sort((a, b) => b.lead_score - a.lead_score || a.company_name.localeCompare(b.company_name));
    return mock(paginate(rows, page, page_size));
  }
  return request<Page<LeadListItem>>(ENDPOINTS.leads + query({ status, page, page_size }));
}

export async function getLead(leadId: number): Promise<LeadDetail> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const l = db.leads.find((x) => x.lead_id === leadId);
    if (!l) return mockFail(404, "Lead not found");
    const jobs = l.evidence.job_ids
      .map((id) => db.jobs.find((j) => j.job_id === id))
      .filter((j): j is MockJob => Boolean(j))
      .map((j) => ({ job_id: j.job_id, title: j.title, fit_score: j.requirements?.fit_score ?? null,
        fit_reason: j.requirements?.fit_reason ?? null }))
      .sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0));
    const d = newestDraft(leadId);
    return mock({ ...leadRow(l), company: db.companies[l.company_id], jobs, history: l.history,
      draft: d ? publicDraft(d) : null });
  }
  return request<LeadDetail>(ENDPOINTS.lead(leadId));
}

/** Add or change the contact person by hand (FR-26). The AI never sees the email. */
export async function updateContact(leadId: number, contact: ContactUpdate): Promise<Company> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const l = db.leads.find((x) => x.lead_id === leadId);
    if (!l) return mockFail(404, "Lead not found");
    if (contact.contact_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact.contact_email)) {
      return mockFail(422, "contact_email is not a valid email");
    }
    Object.assign(db.companies[l.company_id], contact);
    return mock(db.companies[l.company_id]);
  }
  return request<Company>(ENDPOINTS.contact(leadId), { method: "PATCH", body: JSON.stringify(contact) });
}

// ---------- drafts (nothing is ever sent) ----------

function mockDecide(draftId: number): MockDraft | [number, string] {
  const d = db.drafts.find((x) => x.draft_id === draftId);
  if (!d) return [404, "Draft not found"];
  if (newestDraft(d.lead_id)?.draft_id !== d.draft_id) return [409, "Only the newest version can be reviewed"];
  if (d.status === "approved" || d.status === "rejected") return [409, "This draft is already decided"];
  return d;
}

export async function editDraft(draftId: number, changes: { subject: string; body: string }): Promise<Draft> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const d = mockDecide(draftId);
    if (Array.isArray(d)) return mockFail(...d);
    if (!changes.subject.trim() || changes.subject.length > 150 || !changes.body.trim()) {
      return mockFail(422, "Subject (1–150 characters) and message are required");
    }
    Object.assign(d, { subject: changes.subject.trim(), body: changes.body.trim(), word_count: countWords(changes.body),
      status: "edited", reviewed_by: mockUserFromToken()?.full_name ?? null, reviewed_at: now() });
    return mock(publicDraft(d));
  }
  return request<Draft>(ENDPOINTS.draft(draftId), { method: "PATCH", body: JSON.stringify(changes) });
}

export async function approveDraft(draftId: number): Promise<Draft> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const d = mockDecide(draftId);
    if (Array.isArray(d)) return mockFail(...d);
    Object.assign(d, { status: "approved", reviewed_by: mockUserFromToken()?.full_name ?? null, reviewed_at: now() });
    const lead = db.leads.find((l) => l.lead_id === d.lead_id);
    if (lead) lead.status = "approved";
    return mock(publicDraft(d));
  }
  return request<Draft>(ENDPOINTS.approve(draftId), { method: "POST" });
}

export async function rejectDraft(draftId: number, review_comment: string): Promise<Draft> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    if (!review_comment.trim()) return mockFail(422, "A comment is required to reject a draft");
    const d = mockDecide(draftId);
    if (Array.isArray(d)) return mockFail(...d);
    Object.assign(d, { status: "rejected", reviewed_by: mockUserFromToken()?.full_name ?? null, reviewed_at: now(), review_comment: review_comment.trim() });
    const lead = db.leads.find((l) => l.lead_id === d.lead_id);
    if (lead) lead.status = "rejected";
    return mock(publicDraft(d));
  }
  return request<Draft>(ENDPOINTS.reject(draftId), { method: "POST", body: JSON.stringify({ review_comment }) });
}

/** A new version written by the AI (P2-2). The old versions stay as history. */
export async function regenerateDraft(leadId: number): Promise<Draft> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const lead = db.leads.find((l) => l.lead_id === leadId);
    if (!lead) return mockFail(404, "Lead not found");
    if (lead.status === "approved") return mockFail(409, "This draft is already approved");
    if (lead.status === "not_qualified") return mockFail(409, "This company has no suitable jobs");
    const company = db.companies[lead.company_id];
    const titles = lead.evidence.job_ids.map((id) => db.jobs.find((j) => j.job_id === id)?.title).filter(Boolean);
    const body = `Hello ${company.name} team,

I noticed you are hiring for the ${titles.join(" and ")} role${titles.length > 1 ? "s" : ""}. Simera is a remote hiring platform that connects companies with pre-vetted professionals across technical and business roles, and takes care of hiring paperwork such as payroll and compliance.

${lead.reason.replace(/^.*?\.\s*/, "")} Our team reviews every profile before we share it, so you only spend time on people who match what your posting asks for, and we keep the process simple for your hiring team from the first call.

Would you be open to a short call next week to see if these profiles could help your team?

Best regards,
Simera team`;
    const version = (newestDraft(leadId)?.version ?? 0) + 1;
    const d: MockDraft = { draft_id: Math.max(0, ...db.drafts.map((x) => x.draft_id)) + 1, lead_id: leadId, version,
      subject: `${titles[0] ?? "Remote"} talent for ${company.name}`, body, word_count: countWords(body),
      status: "pending_review", reviewed_by: null, reviewed_at: null, review_comment: null };
    db.drafts.push(d);
    lead.status = "draft_ready";
    await new Promise((resolve) => setTimeout(resolve, 900)); // the real AI call takes a few seconds
    return mock(publicDraft(d));
  }
  return request<Draft>(ENDPOINTS.regenerate(leadId), { method: "POST" });
}

// ---------- pipeline runs (admin) ----------

const MOCK_RUN_SECONDS = 5;

/** Start a run. The answer comes at once; the stages continue in the background. 409 = one is already running. */
export async function startRun(): Promise<{ run_id: number }> {
  if (USE_MOCK) {
    const denied = mockGuard(true);
    if (denied) return mockFail(...denied);
    if (db.runs.some((r) => r.status === "running")) return mockFail(409, "A run is already in progress");
    const user = mockUserFromToken();
    const run: PipelineRun = { run_id: Math.max(0, ...db.runs.map((r) => r.run_id)) + 1, status: "running",
      trigger_type: "manual", started_by: user?.full_name ?? null, started_at: now(), finished_at: null,
      jobs_fetched: 0, jobs_new: 0, jobs_updated: 0, errors: null };
    db.runs.unshift(run);
    setTimeout(() => {
      Object.assign(run, { status: "completed", finished_at: now(), jobs_fetched: db.settings.fetch_limit,
        jobs_new: 0, jobs_updated: 0, errors: { stages: [
          { stage: "discovery", result: `${db.settings.fetch_limit} fetched, 0 new, 0 updated` },
          { stage: "understanding", result: "0 parsed" }, { stage: "fit scoring", result: "0 scored" },
          { stage: "lead scoring", result: `${db.leads.filter((l) => l.qualifying_jobs > 0).length} qualified, ${db.leads.filter((l) => l.qualifying_jobs === 0).length} not qualified` },
          { stage: "drafts", result: "0 created" }], errors: [] } });
    }, MOCK_RUN_SECONDS * 1000);
    return mock({ run_id: run.run_id });
  }
  return request<{ run_id: number }>(ENDPOINTS.run, { method: "POST" });
}

export async function getRuns(limit = 10): Promise<PipelineRun[]> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    return mock(db.runs.slice(0, limit));
  }
  return request<PipelineRun[]>(ENDPOINTS.runs + query({ limit }));
}

export async function getRun(runId: number): Promise<PipelineRun> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    const run = db.runs.find((r) => r.run_id === runId);
    return run ? mock(run) : mockFail(404, "Run not found");
  }
  return request<PipelineRun>(ENDPOINTS.runOne(runId));
}

// ---------- settings ----------

export async function getSettings(): Promise<Settings> {
  if (USE_MOCK) {
    const denied = mockGuard();
    if (denied) return mockFail(...denied);
    return mock(db.settings);
  }
  return request<Settings>(ENDPOINTS.settings);
}

/** Change settings (admin). Send only what changed. Wrong values come back as 422. */
export async function updateSettings(changes: Partial<Settings>): Promise<Settings> {
  if (USE_MOCK) {
    const denied = mockGuard(true);
    if (denied) return mockFail(...denied);
    const next = { ...db.settings, ...changes };
    const problem = settingsProblem(next);
    if (problem) return mockFail(422, problem);
    db.settings = next;
    return mock(db.settings);
  }
  return request<Settings>(ENDPOINTS.settings, { method: "PUT", body: JSON.stringify(changes) });
}

/** The same limits as AppSettings in the backend. null = all fine. */
export function settingsProblem(s: Settings): string | null {
  const whole = (v: number) => Number.isInteger(v);
  if (!whole(s.lead_threshold) || s.lead_threshold < 0 || s.lead_threshold > 100) return "Lead threshold must be a whole number from 0 to 100";
  if (!whole(s.fetch_limit) || s.fetch_limit < 1 || s.fetch_limit > 500) return "Jobs per run must be a whole number from 1 to 500";
  if (!whole(s.max_retries) || s.max_retries < 0 || s.max_retries > 5) return "Retries must be a whole number from 0 to 5";
  if (s.run_interval_hours !== undefined && (!whole(s.run_interval_hours) || s.run_interval_hours < 1 || s.run_interval_hours > 168)) {
    return "Run every must be a whole number of hours from 1 to 168";
  }
  if (s.run_at_hour != null && (!whole(s.run_at_hour) || s.run_at_hour < 0 || s.run_at_hour > 23)) {
    return "Run at must be a whole hour from 0 to 23";
  }
  return null;
}
