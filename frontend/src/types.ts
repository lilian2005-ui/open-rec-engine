/**
 * Data shapes used by the screens. Copied from the data contract (v1.1) and from
 * backend/schemas: same names, snake_case, null for "not known".
 * Dates arrive as ISO 8601 strings in UTC (for example "2026-10-18T09:00:00Z").
 */

// ---- allowed values (data contract, section 11). Lowercase, like in the database.
export type Source = "himalayas" | "remotive";
export type JobStatus = "discovered" | "parsed" | "needs_review" | "scored" | "failed";
export type LeadStatus = "qualified" | "not_qualified" | "draft_ready" | "approved" | "rejected";
export type DraftStatus = "pending_review" | "approved" | "edited" | "rejected";
export type UserRole = "reviewer" | "admin";
export type Seniority = "entry" | "mid" | "senior" | "lead";
export type EmploymentType = "full_time" | "part_time" | "contractor" | "other";
export type RemotePolicy = "remote" | "hybrid" | "onsite";
export type SalaryPeriod = "hourly" | "weekly" | "fortnightly" | "monthly" | "annual";
export type ExtractionStatus = "ok" | "needs_review" | "failed";

/** Stage 2 + 3 result for one job (JobRequirements + fit score). */
export interface JobRequirements {
  job_id: number;
  source_hash: string | null;
  title: string | null;
  seniority: Seniority | null;
  min_years_experience: number | null;
  required_skills: string[];
  preferred_skills: string[];
  timezone_offsets: number[] | null;
  employment_type: EmploymentType | null;
  remote_policy: RemotePolicy | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: SalaryPeriod | null;
  extraction_status: ExtractionStatus;
  flag_reason: string | null;
  fit_score: number | null; // 0-100, null until the job is scored
  fit_reason: string | null;
  parsed_at: string | null;
}

/** A job posting as the job feed needs it. */
export interface Job {
  job_id: number;
  company_id: number;
  company_name: string; // joined from company, the feed shows it
  source: Source;
  external_id: string;
  url: string;
  title: string;
  description_text: string | null;
  posted_at: string | null;
  expires_at: string | null;
  discovered_at: string;
  updated_at: string | null;
  status: JobStatus;
  requirement: JobRequirements | null; // null before stage 2
}

/** The current score of one company. */
export interface Lead {
  lead_id: number;
  company_id: number;
  company_name: string; // joined from company
  run_id: number;
  lead_score: number; // 0-100, computed by code
  best_job_score: number;
  qualifying_jobs: number;
  status: LeadStatus;
  reason: string;
  evidence: { job_ids: number[] };
  scored_at: string;
}

/** An outreach draft with its review decision. */
export interface Draft {
  draft_id: number;
  lead_id: number;
  subject: string;
  body: string;
  word_count: number; // 120-180
  version: number;
  status: DraftStatus;
  reviewed_by: number | null; // user_id
  reviewed_at: string | null;
  review_comment: string | null;
  created_at: string;
}

/** What the API says about a user. There is no password field on purpose. */
export interface User {
  user_id: number;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

/** Answer of the login endpoint (backend/schemas/auth.py: TokenOut). */
export interface TokenOut {
  access_token: string;
  token_type: string;
}