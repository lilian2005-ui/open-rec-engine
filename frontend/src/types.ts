/**
 * Data shapes used by the screens, the same as Open_Rec_API_Contract_v1.md:
 * same names, snake_case, null for "not known".
 * Dates arrive as ISO 8601 strings in UTC (for example "2026-10-18T09:00:00Z").
 */

// ---- allowed values (data contract, section 11). Lowercase, like in the database.
export type Source = "himalayas";
export type JobStatus = "discovered" | "parsed" | "needs_review" | "scored" | "failed";
export type LeadStatus = "qualified" | "not_qualified" | "draft_ready" | "approved" | "rejected";
export type DraftStatus = "pending_review" | "approved" | "edited" | "rejected";
export type UserRole = "reviewer" | "admin";
export type Seniority = "entry" | "mid" | "senior" | "lead";
export type EmploymentType = "full_time" | "part_time" | "contractor" | "other";
export type RemotePolicy = "remote" | "hybrid" | "onsite";
export type SalaryPeriod = "hourly" | "weekly" | "fortnightly" | "monthly" | "annual";
export type RunStatus = "running" | "completed" | "partial" | "failed";
export type TriggerType = "manual" | "scheduled";
export type RunMode = "manual" | "scheduled";

/** Every list endpoint answers like this: ?page=1&page_size=20 */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------- jobs ----------

/** What the AI extracted from a posting, plus the fit score (null until scored). */
export interface JobRequirements {
  title?: string | null;
  required_skills: string[];
  preferred_skills: string[];
  seniority: Seniority | null;
  min_years_experience: number | null;
  timezone_offsets: number[] | null;
  employment_type: EmploymentType | null;
  remote_policy: RemotePolicy | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: SalaryPeriod | null;
  fit_score: number | null;
  fit_reason: string | null;
  flag_reason: string | null;
}

/** The fields a person can correct on the job detail screen (FR-12). */
export type RequirementsUpdate = Partial<
  Pick<
    JobRequirements,
    | "required_skills" | "preferred_skills" | "seniority" | "min_years_experience"
    | "timezone_offsets" | "employment_type" | "remote_policy"
    | "salary_min" | "salary_max" | "salary_currency" | "salary_period"
  >
>;

/** One row of the job feed. */
export interface JobListItem {
  job_id: number;
  title: string;
  company_name: string;
  source: Source;
  posted_at: string | null;
  status: JobStatus;
  fit_score: number | null;
}

/** The job detail screen: the row + the posting + what the AI extracted. */
export interface JobDetail extends JobListItem {
  url: string;
  description_text: string | null;
  expires_at: string | null;
  requirements: JobRequirements | null; // null while the job is still "discovered"
}

// ---------- leads and drafts ----------

/** One row of the leads list. */
export interface LeadListItem {
  lead_id: number;
  company_name: string;
  lead_score: number; // 0-100, computed by code
  best_job_score: number;
  qualifying_jobs: number;
  status: LeadStatus;
  reason: string;
}

export interface Company {
  name: string;
  website: string | null;
  location: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
}

export type ContactUpdate = Pick<Company, "contact_name" | "contact_title" | "contact_email">;

export interface LeadJob {
  job_id: number;
  title: string;
  fit_score: number | null;
  fit_reason: string | null;
}

export interface LeadHistoryItem {
  run_id: number;
  lead_score: number;
  status?: LeadStatus;
  created_at: string;
}

/** An outreach draft. NOTHING is ever sent from Open Rec. */
export interface Draft {
  draft_id: number;
  subject: string;
  body: string;
  word_count: number;
  version: number;
  status: DraftStatus;
  reviewed_at?: string | null;
  review_comment?: string | null;
}

/** The lead review screen. */
export interface LeadDetail extends LeadListItem {
  company: Company;
  jobs: LeadJob[]; // only the jobs that count for the score (evidence)
  history: LeadHistoryItem[];
  draft: Draft | null; // the newest version, or null
}

// ---------- pipeline runs and settings ----------

export interface RunStage {
  stage: string;
  result: string;
}

export interface RunError {
  stage?: string;
  message: string;
}

/**
 * The contract has `errors: []`. P1-6 may save `{ stages, errors }` in the same
 * column, so the screens accept both (see runStages / runErrors in format.ts).
 */
export type RunErrors = Array<RunError | string> | { stages?: RunStage[]; errors?: Array<RunError | string> };

export interface PipelineRun {
  run_id: number;
  status: RunStatus;
  trigger_type: TriggerType;
  started_at: string;
  finished_at: string | null;
  jobs_fetched: number;
  jobs_new: number;
  jobs_updated: number;
  errors: RunErrors | null;
  started_by: string | null; // full name; null for a scheduled run
}

export interface Settings {
  lead_threshold: number; // 0-100
  fetch_limit: number; // 1-500
  himalayas_enabled: boolean;
  run_mode: RunMode;
  max_retries: number; // 0-5
  run_interval_hours?: number; // 1-168, from P1-7 (scheduled runs)
}

// ---------- users ----------

/** What the API says about a user. There is no password field on purpose. */
export interface User {
  user_id: number;
  full_name: string;
  email: string;
  role: UserRole;
  is_active?: boolean;
  created_at?: string;
}

/** Answer of POST /auth/login. */
export interface TokenOut {
  access_token: string;
  token_type: string;
}
