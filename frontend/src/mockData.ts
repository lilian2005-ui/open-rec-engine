/**
 * Fake data for the screens, so the frontend works before the backend is ready.
 * Only api.ts reads it. The shapes here are "database-like"; api.ts turns them
 * into the exact answers of the API contract.
 *
 * Every lead follows the lead score rule (data contract, section 6):
 *   lead score = best suitable fit + 5 for each extra suitable fit (max 100),
 *   a job is suitable when it is scored and its fit score is 60 or more.
 *
 *   Helix Health          fits 92 and 78   ->  92 + 5 = 97
 *   Online Doctor AG      fits 85 and 55   ->  85 (55 is below 60)
 *   Brightwave Logistics  fit  72          ->  72
 *   Ledgerly              fits 48 and 40   ->  0, not qualified
 */
import { countWords } from "./format";
import type {
  Company, Draft, JobDetail, JobRequirements, LeadHistoryItem, LeadStatus, PipelineRun, Settings, User,
} from "./types";

export const MOCK_THRESHOLD = 60;

export interface MockJob extends JobDetail {
  company_id: number;
}
export interface MockLead {
  lead_id: number;
  company_id: number;
  lead_score: number;
  best_job_score: number;
  qualifying_jobs: number;
  status: LeadStatus;
  reason: string;
  evidence: { job_ids: number[] };
  history: LeadHistoryItem[];
}
export interface MockDraft extends Draft {
  lead_id: number;
}

export const MOCK_COMPANIES: Record<number, Company> = {
  1: { name: "Helix Health", website: "https://helixhealth.example", location: "Remote (US)", contact_name: null, contact_title: null, contact_email: null },
  2: { name: "Online Doctor AG", website: null, location: "Switzerland", contact_name: "Anna Keller", contact_title: "Head of Engineering", contact_email: "anna.keller@onlinedoctor.example" },
  3: { name: "Brightwave Logistics", website: null, location: "Remote (Europe)", contact_name: null, contact_title: null, contact_email: null },
  4: { name: "Ledgerly", website: null, location: null, contact_name: null, contact_title: null, contact_email: null },
  5: { name: "Northwind Labs", website: null, location: null, contact_name: null, contact_title: null, contact_email: null },
  6: { name: "micro1", website: null, location: null, contact_name: null, contact_title: null, contact_email: null },
  7: { name: "Kangtai Pharma", website: null, location: "China", contact_name: null, contact_title: null, contact_email: null },
  8: { name: "Samsara", website: null, location: null, contact_name: null, contact_title: null, contact_email: null },
};

function req(over: Partial<JobRequirements> & Pick<JobRequirements, "required_skills">): JobRequirements {
  return {
    preferred_skills: [], seniority: "senior", min_years_experience: null, timezone_offsets: null,
    employment_type: "full_time", remote_policy: "remote", salary_min: null, salary_max: null,
    salary_currency: null, salary_period: null, fit_score: null, fit_reason: null, flag_reason: null,
    ...over,
  };
}

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

function job(
  job_id: number, company_id: number, title: string, status: MockJob["status"], posted: number,
  description_text: string, requirements: JobRequirements | null,
): MockJob {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return {
    job_id, company_id, title, status, requirements, description_text,
    company_name: MOCK_COMPANIES[company_id].name, source: "himalayas",
    url: `https://himalayas.app/companies/${company_id}/jobs/${slug}`,
    posted_at: hoursAgo(posted), expires_at: null,
    fit_score: requirements?.fit_score ?? null,
  };
}

export const MOCK_JOBS: MockJob[] = [
  job(1, 1, "Senior Customer Success Manager", "scored", 2,
    "Helix Health is looking for a Senior Customer Success Manager to own the relationship with our clinic customers after onboarding. You will run onboarding for new accounts, lead quarterly business reviews, reduce churn and work closely with Product to share customer feedback. You have 5+ years in customer success for a SaaS product and you are comfortable with renewals and expansion conversations. Fully remote, US hours overlap.",
    req({ required_skills: ["customer success", "saas onboarding", "account management"], preferred_skills: ["hubspot", "healthcare"], min_years_experience: 5, timezone_offsets: [-5, -4], salary_min: 85000, salary_max: 105000, salary_currency: "USD", salary_period: "annual", fit_score: 92, fit_reason: "3 profiles cover customer success and SaaS onboarding with 5+ years" })),
  job(2, 1, "Support Lead (EN/ES)", "scored", 6,
    "We need a Support Lead who speaks English and Spanish to lead a small support team, set up our help center and handle escalations from Spanish-speaking clinics.",
    req({ required_skills: ["customer support", "team leadership", "spanish"], seniority: "lead", fit_score: 78, fit_reason: "2 profiles cover bilingual support and team leading" })),
  job(3, 2, "Senior QA Engineer", "scored", 5,
    "Join OnlineDoctor: We're expanding! We are a fast-growing telemedicine company focused on improving access to dermatological care. We are looking for a Senior QA Engineer to take full ownership of verification and testing for our product. This is a hands-on role covering both manual and automated testing: you will investigate new features and edge cases yourself, while building automation that makes repeated checks reliable and efficient. You will be part of the Product & Tech team, working with a medical device in a healthcare environment where reliability, privacy and evidence that critical functionality performs as intended are essential.",
    req({ required_skills: ["manual testing", "test automation", "api testing", "ci/cd"], preferred_skills: ["python", "pytest", "playwright", "aws"], timezone_offsets: [1], fit_score: 85, fit_reason: "2 profiles cover manual testing, test automation and API testing at senior level; timezone overlaps" })),
  job(4, 3, "Operations Coordinator (Remote)", "scored", 8,
    "Brightwave Logistics is hiring an Operations Coordinator to track shipments, talk to suppliers and carriers, and keep our order data clean. Excellent written English and experience with logistics tools are required.",
    req({ required_skills: ["logistics coordination", "supplier communication", "excel"], seniority: "mid", min_years_experience: 2, fit_score: 72, fit_reason: "1 profile covers logistics coordination and supplier communication" })),
  job(5, 4, "Bookkeeper, Part-time", "scored", 10,
    "Ledgerly needs a part-time bookkeeper with QuickBooks and US tax experience for small business clients.",
    req({ required_skills: ["bookkeeping", "quickbooks", "us tax"], seniority: "mid", employment_type: "part_time", salary_min: 25, salary_max: 35, salary_currency: "USD", salary_period: "hourly", fit_score: 48, fit_reason: "1 profile has bookkeeping, but none has US tax experience" })),
  job(6, 5, "Senior Data Engineer", "parsed", 12,
    "Northwind Labs is looking for a Senior Data Engineer to build batch and streaming pipelines on GCP.",
    req({ required_skills: ["python", "sql", "airflow", "gcp"], min_years_experience: 5 })),
  job(7, 6, "Video Annotation", "needs_review", 26,
    "We are looking for detail-oriented people to annotate short videos for AI training. Flexible hours, fully remote, paid per task. Originally posted on Himalayas.",
    req({ required_skills: [], seniority: null, employment_type: "contractor", flag_reason: "No required skills could be extracted" })),
  job(8, 7, "Medical Sales Representative", "failed", 30,
    "医药代表，负责医院客户的拜访与产品推广。", null),
  job(9, 8, "Product Designer", "discovered", 48,
    "Samsara is hiring a Product Designer to work on our fleet management apps.", null),
  job(10, 2, "Frontend Developer", "scored", 20,
    "Online Doctor is looking for a Frontend Developer with Vue and TypeScript for the patient app.",
    req({ required_skills: ["vue", "typescript", "css"], seniority: "mid", min_years_experience: 3, timezone_offsets: [1], fit_score: 55, fit_reason: "2 profiles have typescript, but none has Vue" })),
  job(11, 4, "Accounts Payable Specialist", "scored", 40,
    "Ledgerly is hiring an Accounts Payable Specialist with NetSuite experience.",
    req({ required_skills: ["accounts payable", "netsuite"], seniority: "mid", fit_score: 40, fit_reason: "No profile has NetSuite" })),
];

const history = (scores: Array<[number, number, LeadStatus]>): LeadHistoryItem[] =>
  scores.map(([run_id, lead_score, status], i) => ({ run_id, lead_score, status, created_at: hoursAgo(24 * (scores.length - i)) }));

const NO_SCORED_JOBS = "No scored jobs yet, so the company cannot be qualified.";

export const MOCK_LEADS: MockLead[] = [
  { lead_id: 1, company_id: 1, lead_score: 97, best_job_score: 92, qualifying_jobs: 2, status: "draft_ready",
    reason: "Helix Health is hiring a Senior Customer Success Manager and a Support Lead. 3 Simera profiles cover customer success, SaaS onboarding and English–Spanish support.",
    evidence: { job_ids: [1, 2] }, history: history([[6, 92, "qualified"], [8, 97, "draft_ready"]]) },
  { lead_id: 2, company_id: 2, lead_score: 85, best_job_score: 85, qualifying_jobs: 1, status: "draft_ready",
    reason: "Online Doctor AG is hiring a Senior QA Engineer. 2 profiles cover manual and automated testing at senior level.",
    evidence: { job_ids: [3] }, history: history([[8, 85, "draft_ready"]]) },
  { lead_id: 3, company_id: 3, lead_score: 72, best_job_score: 72, qualifying_jobs: 1, status: "approved",
    reason: "Brightwave Logistics is hiring an Operations Coordinator. 1 profile covers logistics coordination and supplier communication.",
    evidence: { job_ids: [4] }, history: history([[7, 72, "qualified"], [8, 72, "approved"]]) },
  { lead_id: 4, company_id: 4, lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified",
    reason: "No job reaches the threshold of 60: the best fit is 48 (Bookkeeper, Part-time).",
    evidence: { job_ids: [] }, history: history([[8, 0, "not_qualified"]]) },
  { lead_id: 5, company_id: 5, lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified", reason: NO_SCORED_JOBS, evidence: { job_ids: [] }, history: history([[8, 0, "not_qualified"]]) },
  { lead_id: 6, company_id: 6, lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified", reason: NO_SCORED_JOBS, evidence: { job_ids: [] }, history: history([[8, 0, "not_qualified"]]) },
  { lead_id: 7, company_id: 7, lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified", reason: NO_SCORED_JOBS, evidence: { job_ids: [] }, history: history([[8, 0, "not_qualified"]]) },
  { lead_id: 8, company_id: 8, lead_score: 0, best_job_score: 0, qualifying_jobs: 0, status: "not_qualified", reason: NO_SCORED_JOBS, evidence: { job_ids: [] }, history: history([[8, 0, "not_qualified"]]) },
];

function draft(draft_id: number, lead_id: number, version: number, status: Draft["status"], subject: string, body: string,
  review_comment: string | null = null): MockDraft {
  return { draft_id, lead_id, version, status, subject, body, word_count: countWords(body),
    reviewed_by: status === "pending_review" ? null : "Lilian Abu Ramadan",
    reviewed_at: status === "pending_review" ? null : hoursAgo(3), review_comment };
}

const HELIX_V1 = `Dear Sir or Madam,

We at Simera are writing to you regarding your current openings for a Senior Customer Success Manager and a Support Lead. Simera is a remote hiring platform that connects companies with pre-vetted professionals across technical and business roles, and takes care of hiring paperwork such as payroll and compliance.

Our talent pool includes 3 profiles that cover customer success and SaaS onboarding with 5+ years of experience, as well as 2 profiles with bilingual English and Spanish support and team leading experience.

We would therefore be pleased to arrange a meeting with your hiring team at your earliest convenience in order to discuss the possibility of presenting these profiles to you and answering any questions you may have.

Yours faithfully,
Simera team`;

const HELIX_V2 = `Hello Helix Health team,

I noticed you are hiring a Senior Customer Success Manager and a Support Lead. Simera is a remote hiring platform that connects companies with pre-vetted professionals across technical and business roles, and takes care of hiring paperwork such as payroll and compliance.

We work with 3 profiles that cover customer success and SaaS onboarding with 5+ years, and 2 profiles with bilingual English–Spanish support and team leading experience. They could help your team keep new clinics happy from the first week and handle Spanish-speaking customers without extra hiring effort, while your current team stays focused on growth.

Would you be open to a short call next week to see if these profiles fit your team?

Best regards,
Simera team`;

const ONLINE_DOCTOR = `Hi Anna,

I noticed Online Doctor AG is hiring a Senior QA Engineer to own testing for your medical device product. Simera is a remote hiring platform that connects companies with pre-vetted professionals across technical and business roles, and takes care of hiring paperwork such as payroll and compliance.

We work with 2 profiles that cover manual testing, test automation and API testing at senior level, and their working hours overlap with your timezone. They have built automation that makes repeated checks reliable while still testing new features by hand, which matches what your posting describes.

If it is useful, I would be happy to share these profiles with you. Would you be open to a short call next week to talk about the role?

Best regards,
Simera team`;

const BRIGHTWAVE = `Hello Brightwave Logistics team,

I noticed you are hiring an Operations Coordinator to track shipments and work with suppliers and carriers. Simera is a remote hiring platform that connects companies with pre-vetted professionals across technical and business roles, and takes care of hiring paperwork such as payroll and compliance.

We work with 1 profile that covers logistics coordination and supplier communication, with strong written English and daily experience keeping order data clean. This could help your team keep shipments on track, answer suppliers faster and reduce delays, while you focus on growing the business with fewer daily surprises.

Would you be open to a short call next week to see if this profile fits your team?

Best regards,
Simera team`;

export const MOCK_DRAFTS: MockDraft[] = [
  draft(1, 1, 1, "rejected", "Remote talent for Helix Health", HELIX_V1, "Too formal. Start with Hello and keep it friendly."),
  draft(2, 1, 2, "pending_review", "Customer success talent for your Senior CSM role", HELIX_V2),
  draft(3, 2, 1, "pending_review", "QA talent for your Senior QA Engineer role", ONLINE_DOCTOR),
  draft(4, 3, 1, "approved", "Operations talent for your Operations Coordinator role", BRIGHTWAVE),
];

export const MOCK_RUNS: PipelineRun[] = [
  { run_id: 8, status: "partial", trigger_type: "manual", started_by: "Lilian Abu Ramadan",
    started_at: hoursAgo(3), finished_at: new Date(Date.now() - 3 * 3_600_000 + 6 * 60_000).toISOString(),
    jobs_fetched: 100, jobs_new: 12, jobs_updated: 3,
    errors: {
      stages: [
        { stage: "discovery", result: "100 fetched, 12 new, 3 updated" },
        { stage: "understanding", result: "14 parsed, 1 needs review" },
        { stage: "fit scoring", result: "14 scored" },
        { stage: "lead scoring", result: "3 qualified, 5 not qualified" },
        { stage: "drafts", result: "2 created, 1 failed" },
      ],
      errors: [{ stage: "drafts", message: "lead 4 (Ledgerly): no draft: mentions no role title" }],
    } },
  { run_id: 7, status: "completed", trigger_type: "scheduled", started_by: null,
    started_at: hoursAgo(35), finished_at: hoursAgo(34.9), jobs_fetched: 100, jobs_new: 9, jobs_updated: 0, errors: [] },
  { run_id: 6, status: "completed", trigger_type: "manual", started_by: "Shaima",
    started_at: hoursAgo(52), finished_at: hoursAgo(51.9), jobs_fetched: 100, jobs_new: 20, jobs_updated: 0, errors: [] },
  { run_id: 5, status: "failed", trigger_type: "manual", started_by: "Lilian Abu Ramadan",
    started_at: hoursAgo(58), finished_at: hoursAgo(57.99), jobs_fetched: 0, jobs_new: 0, jobs_updated: 0,
    errors: [{ stage: "discovery", message: "Himalayas did not answer (timeout after 30 s)" }] },
];

export const MOCK_SETTINGS: Settings = {
  lead_threshold: MOCK_THRESHOLD, fetch_limit: 100, himalayas_enabled: true,
  run_mode: "manual", max_retries: 3, run_interval_hours: 32, run_at_hour: null,
};

/** Mock accounts. In mock mode any password works; the email picks the user. */
export const MOCK_USERS: User[] = [
  { user_id: 1, full_name: "Lilian Abu Ramadan", email: "lilian@simera.com", role: "admin", is_active: true },
  { user_id: 2, full_name: "Nadeen Shadeed", email: "nadeen@simera.com", role: "reviewer", is_active: true },
];
