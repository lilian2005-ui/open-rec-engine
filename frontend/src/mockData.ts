/**
 * Fake data for the screens, so the frontend works before the backend is ready.
 * Same examples as the project report (wireframes): Acme 97, Helix 86, Orbit 74,
 * Brightly 0. Every number follows the lead score rule:
 *   lead score = best suitable fit + 5 for each extra suitable fit (max 100),
 * and a job is suitable when its fit score is 60 or more.
 *
 *   Acme Corp   fits 92 and 78  ->  92 + 5 = 97
 *   Helix AI    fits 81 and 76  ->  81 + 5 = 86
 *   Orbit Tech  fit  74         ->  74
 *   Brightly    fit  45 (< 60)  ->  0, not qualified
 */
import { countWords } from "./format";
import type { Draft, Job, JobRequirements, Lead, User } from "./types";

type RequirementOverrides = Partial<JobRequirements> & Pick<JobRequirements, "required_skills">;

function requirement(job_id: number, title: string, over: RequirementOverrides): JobRequirements {
  return {
    job_id,
    source_hash: null,
    title,
    seniority: "senior",
    min_years_experience: 5,
    preferred_skills: [],
    timezone_offsets: null, // not stated in the posting stays null, never guessed
    employment_type: "full_time",
    remote_policy: "remote",
    salary_min: null,
    salary_max: null,
    salary_currency: null,
    salary_period: null,
    extraction_status: "ok",
    flag_reason: null,
    fit_score: null,
    fit_reason: null,
    parsed_at: "2026-10-26T10:03:00Z",
    ...over,
  };
}

const TEXT = "We are looking for an experienced engineer to join our remote team.";

export const MOCK_JOBS: Job[] = [
  {
    job_id: 1, company_id: 1, company_name: "Acme Corp", source: "himalayas",
    external_id: "acme-senior-react-developer-7f3a",
    url: "https://himalayas.app/companies/acme/jobs/senior-react-developer",
    title: "Senior React Developer", description_text: TEXT,
    posted_at: "2026-10-26T08:00:00Z", expires_at: "2026-11-25T08:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(1, "Senior React Developer", {
      required_skills: ["react", "typescript", "redux"], preferred_skills: ["graphql"],
      timezone_offsets: [-5, -4], salary_min: 90000, salary_max: 120000,
      salary_currency: "USD", salary_period: "annual", fit_score: 92,
      fit_reason: "Our pool has 3 profiles with react, typescript and redux at 5+ years, in US Eastern hours",
    }),
  },
  {
    job_id: 2, company_id: 1, company_name: "Acme Corp", source: "himalayas",
    external_id: "acme-frontend-engineer-4c82", url: "https://himalayas.app/companies/acme/jobs/frontend-engineer",
    title: "Frontend Engineer", description_text: TEXT,
    posted_at: "2026-10-26T05:00:00Z", expires_at: "2026-11-25T05:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(2, "Frontend Engineer", {
      seniority: "mid", min_years_experience: 3,
      required_skills: ["react", "javascript", "css"], fit_score: 78,
      fit_reason: "Our pool covers 2 of the 3 required skills",
    }),
  },
  {
    job_id: 3, company_id: 2, company_name: "Helix AI", source: "himalayas",
    external_id: "helix-ml-engineer-nlp-21bc",
    url: "https://himalayas.app/companies/helix-ai/jobs/ml-engineer-nlp",
    title: "ML Engineer (NLP)", description_text: TEXT,
    posted_at: "2026-10-25T21:00:00Z", expires_at: "2026-11-24T21:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(3, "ML Engineer (NLP)", {
      required_skills: ["python", "pytorch", "nlp"], fit_score: 81,
      fit_reason: "Our pool covers python and pytorch well for NLP roles",
    }),
  },
  {
    job_id: 4, company_id: 2, company_name: "Helix AI", source: "himalayas",
    external_id: "helix-data-scientist-8a17", url: "https://himalayas.app/companies/helix-ai/jobs/data-scientist",
    title: "Data Scientist", description_text: TEXT,
    posted_at: "2026-10-25T18:00:00Z", expires_at: "2026-11-24T18:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(4, "Data Scientist", {
      seniority: "mid", min_years_experience: 3,
      required_skills: ["python", "sql", "pandas"], fit_score: 76,
      fit_reason: "Our pool covers python and sql, with fewer profiles in pandas",
    }),
  },
  {
    job_id: 5, company_id: 3, company_name: "Orbit Tech", source: "himalayas",
    external_id: "orbit-python-backend-developer-9d04",
    url: "https://himalayas.app/companies/orbit-tech/jobs/python-backend-developer",
    title: "Python Backend Developer", description_text: TEXT,
    posted_at: "2026-10-25T09:00:00Z", expires_at: "2026-11-24T09:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(5, "Python Backend Developer", {
      required_skills: ["python", "fastapi", "postgresql"], fit_score: 74,
      fit_reason: "Our pool covers fastapi and postgresql",
    }),
  },
  {
    job_id: 6, company_id: 4, company_name: "Brightly", source: "himalayas",
    external_id: "brightly-devops-engineer-62d0", url: "https://himalayas.app/companies/brightly/jobs/devops-engineer",
    title: "DevOps Engineer", description_text: TEXT,
    posted_at: "2026-10-25T08:00:00Z", expires_at: "2026-11-24T08:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "scored",
    requirements: requirement(6, "DevOps Engineer", {
      required_skills: ["kubernetes", "docker", "terraform"], fit_score: 45,
      fit_reason: "Few profiles have kubernetes with 5 years of experience",
    }),
  },
  {
    job_id: 7, company_id: 3, company_name: "Orbit Tech", source: "himalayas",
    external_id: "orbit-platform-engineer-5e11",
    url: "https://himalayas.app/companies/orbit-tech/jobs/platform-engineer",
    title: "Platform Engineer", description_text: TEXT,
    posted_at: "2026-10-25T07:00:00Z", expires_at: "2026-11-24T07:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "needs_review",
    requirements: requirement(7, "Platform Engineer", {
      required_skills: ["go", "kubernetes"], extraction_status: "needs_review",
      flag_reason: "Instruction-like text in the posting",
    }),
  },
  {
    job_id: 8, company_id: 5, company_name: "Nile Systems", source: "himalayas",
    external_id: "nile-data-engineer-b5e9", url: "https://himalayas.app/companies/nile-systems/jobs/data-engineer",
    title: "Data Engineer", description_text: TEXT,
    posted_at: "2026-10-24T10:00:00Z", expires_at: "2026-11-23T10:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "discovered",
    requirements: null, // stage 2 has not run yet
  },
  {
    job_id: 9, company_id: 5, company_name: "Nile Systems", source: "himalayas",
    external_id: "nile-qa-engineer-33aa",
    url: "https://himalayas.app/companies/nile-systems/jobs/qa-engineer",
    title: "QA Engineer", description_text: TEXT,
    posted_at: "2026-10-24T09:00:00Z", expires_at: "2026-11-23T09:00:00Z",
    discovered_at: "2026-10-26T10:02:00Z", updated_at: null, status: "parsed",
    requirements: requirement(9, "QA Engineer", {
      seniority: "mid", min_years_experience: 3, required_skills: ["selenium", "python"],
    }),
  },
];

export const MOCK_LEADS: Lead[] = [
  {
    lead_id: 1, company_id: 1, company_name: "Acme Corp", run_id: 3,
    lead_score: 97, best_job_score: 92, qualifying_jobs: 2, status: "draft_ready",
    reason: "Acme Corp has 2 open React roles that our talent pool covers well (fit 92 and 78).",
    evidence: { job_ids: [1, 2] }, scored_at: "2026-10-26T10:06:00Z",
  },
  {
    lead_id: 2, company_id: 2, company_name: "Helix AI", run_id: 3,
    lead_score: 86, best_job_score: 81, qualifying_jobs: 2, status: "qualified",
    reason: "Helix AI is hiring for NLP and data roles; our talent pool covers Python and PyTorch well.",
    evidence: { job_ids: [3, 4] }, scored_at: "2026-10-26T10:06:00Z",
  },
  {
    lead_id: 3, company_id: 3, company_name: "Orbit Tech", run_id: 3,
    lead_score: 74, best_job_score: 74, qualifying_jobs: 1, status: "qualified",
    reason: "Orbit Tech has 1 Python backend role; our pool covers FastAPI and PostgreSQL.",
    evidence: { job_ids: [5] }, scored_at: "2026-10-26T10:06:00Z",
  },
  {
    lead_id: 4, company_id: 4, company_name: "Brightly", run_id: 3,
    lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified",
    reason: "The DevOps role needs Kubernetes with 5 years of experience; its fit score of 45 is below 60.",
    evidence: { job_ids: [] }, scored_at: "2026-10-26T10:06:00Z",
  },
];

const ACME_BODY = `Hello Acme Corp team,

I noticed you are hiring a Senior React Developer and a Frontend Engineer, and I wanted to reach out because the talent pool at Simera covers both roles well.

For the Senior React Developer role, we work with experienced frontend engineers, including several senior React and TypeScript engineers with 5+ years of experience who work in US Eastern hours. Their skills match the React, TypeScript and Redux requirements in your posting. For the Frontend Engineer role, our pool covers two of the three required skills.

We would be glad to share how our engineers could support your team on these roles. If it is useful, we can arrange a short call to talk about your priorities and timeline.

Thank you for your time. I look forward to hearing from you.

Best regards,
The Simera team`;

export const MOCK_DRAFTS: Draft[] = [
  {
    draft_id: 1, lead_id: 1,
    subject: "Senior React talent available for Acme Corp",
    body: ACME_BODY, word_count: countWords(ACME_BODY), version: 1,
    status: "pending_review", reviewed_by: null, reviewed_at: null, review_comment: null,
    created_at: "2026-10-26T10:07:00Z",
  },
];

/** Mock accounts. In mock mode any password works; the email picks the user. */
export const MOCK_USERS: User[] = [
  { user_id: 1, full_name: "Lilian Abu Ramadan", email: "lilian@simera.com", role: "admin",
    is_active: true, created_at: "2026-10-20T08:00:00Z" },
  { user_id: 2, full_name: "Nadeen Shadeed", email: "nadeen@simera.com", role: "reviewer",
    is_active: true, created_at: "2026-10-20T08:05:00Z" },
];