import { describe, expect, it } from "vitest";
import { MOCK_DRAFTS, MOCK_JOBS, MOCK_LEADS, MOCK_USERS } from "./mockData";

const THRESHOLD = 60;
const TODAY = new Date("2026-10-27T00:00:00Z");

/** The lead score rule from the data contract, section 6. */
function expectedScore(companyId: number) {
  const fits = MOCK_JOBS.filter(
    (j) =>
      j.company_id === companyId &&
      j.status === "scored" &&
      (j.requirements?.fit_score ?? -1) >= THRESHOLD &&
      (j.expires_at === null || new Date(j.expires_at) > TODAY),
  ).map((j) => j.requirements!.fit_score!);
  if (fits.length === 0) return { score: 0, best: 0, count: 0 };
  const best = Math.max(...fits);
  return { score: Math.min(100, best + 5 * (fits.length - 1)), best, count: fits.length };
}

describe("fake leads follow the lead score rule", () => {
  it("has the project report examples: Acme 97, Helix 86, Orbit 74, Brightly 0", () => {
    const scores = Object.fromEntries(MOCK_LEADS.map((l) => [l.company_name, l.lead_score]));
    expect(scores).toEqual({ "Acme Corp": 97, "Helix AI": 86, "Orbit Tech": 74, Brightly: 0 });
  });

  it.each(MOCK_LEADS.map((l) => [l.company_name, l] as const))("%s matches its jobs", (_name, lead) => {
    const expected = expectedScore(lead.company_id);
    expect(lead.lead_score).toBe(expected.score);
    expect(lead.best_job_score).toBe(expected.best);
    expect(lead.qualifying_jobs).toBe(expected.count);
    expect(lead.evidence.job_ids).toHaveLength(expected.count);
    expect(lead.status === "not_qualified").toBe(expected.count === 0);
  });

  it("lists in evidence only jobs of that company", () => {
    for (const lead of MOCK_LEADS) {
      for (const id of lead.evidence.job_ids) {
        expect(MOCK_JOBS.find((j) => j.job_id === id)?.company_id).toBe(lead.company_id);
      }
    }
  });
});

describe("fake jobs follow the data contract", () => {
  it("has unique ids and unique (source, external_id)", () => {
    expect(new Set(MOCK_JOBS.map((j) => j.job_id)).size).toBe(MOCK_JOBS.length);
    expect(new Set(MOCK_JOBS.map((j) => `${j.source}/${j.external_id}`)).size).toBe(MOCK_JOBS.length);
  });

  it("has a fit score and a reason together, or neither (DB rule fit_score_has_reason)", () => {
    for (const job of MOCK_JOBS) {
      const r = job.requirements;
      expect(r === null || (r.fit_score === null) === (r.fit_reason === null)).toBe(true);
      if (r?.fit_score != null) {
        expect(r.fit_score).toBeGreaterThanOrEqual(0);
        expect(r.fit_score).toBeLessThanOrEqual(100);
      }
    }
  });

  it("only scored jobs have a fit score, and every scored job has one", () => {
    for (const job of MOCK_JOBS) {
      expect(job.requirements?.fit_score != null).toBe(job.status === "scored");
    }
  });

  it("has requirements that belong to their job, with lowercase skills", () => {
    for (const job of MOCK_JOBS) {
      if (!job.requirements) continue;
      expect(job.requirements.job_id).toBe(job.job_id);
      for (const skill of [...job.requirements.required_skills, ...job.requirements.preferred_skills]) {
        expect(skill).toBe(skill.toLowerCase());
      }
    }
  });

  it("shows the statuses the feed needs", () => {
    const statuses = new Set(MOCK_JOBS.map((j) => j.status));
    for (const s of ["discovered", "parsed", "needs_review", "scored"] as const) {
      expect(statuses.has(s)).toBe(true);
    }
  });

  it("flags a needs_review job with a reason", () => {
    const flagged = MOCK_JOBS.filter((j) => j.status === "needs_review");
    expect(flagged.length).toBeGreaterThan(0);
    for (const job of flagged) expect(job.requirements?.flag_reason).toBeTruthy();
  });

  it("uses only Himalayas as a source", () => {
    for (const job of MOCK_JOBS) {
      expect(job.source).toBe("himalayas");
    }
  });
});

describe("fake drafts and users", () => {
  it("has drafts of 120-180 words with a matching word_count", () => {
    for (const draft of MOCK_DRAFTS) {
      expect(draft.word_count).toBe(draft.body.split(/\s+/).filter(Boolean).length);
      expect(draft.word_count).toBeGreaterThanOrEqual(120);
      expect(draft.word_count).toBeLessThanOrEqual(180);
    }
  });

  it("has a pending draft without a reviewer yet", () => {
    for (const draft of MOCK_DRAFTS.filter((d) => d.status === "pending_review")) {
      expect(draft.reviewed_by).toBeNull();
      expect(draft.reviewed_at).toBeNull();
    }
  });

  it("has an admin and a reviewer, with lowercase emails", () => {
    expect(MOCK_USERS.map((u) => u.role).sort()).toEqual(["admin", "reviewer"]);
    for (const u of MOCK_USERS) expect(u.email).toBe(u.email.toLowerCase());
  });
});