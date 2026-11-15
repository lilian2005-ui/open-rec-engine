import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";

/** A tiny localStorage for the test, because the test runs in Node, not in a browser. */
function fakeLocalStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

beforeEach(() => {
  vi.stubGlobal("localStorage", fakeLocalStorage());
  api.resetMockData();
});
afterEach(() => {
  vi.useRealTimers();
});

const asAdmin = () => api.login("lilian@simera.com", "x");
const asReviewer = () => api.login("nadeen@simera.com", "x");

describe("auth (fake mode)", () => {
  it("is in fake mode by default", () => {
    expect(api.USE_MOCK).toBe(true);
  });

  it("logs in with a known email and any password, and remembers the user", async () => {
    const user = await api.login("Lilian@Simera.com ", "anything");
    expect(user.role).toBe("admin");
    expect((await api.getCurrentUser())?.user_id).toBe(user.user_id);
  });

  it("refuses an unknown email or an empty password with 401", async () => {
    await expect(api.login("nobody@simera.com", "x")).rejects.toMatchObject({ status: 401 });
    await expect(api.login("lilian@simera.com", "")).rejects.toBeInstanceOf(api.ApiError);
    expect(await api.getCurrentUser()).toBeNull();
  });

  it("forgets the user after logout, and then every screen gets 401", async () => {
    await asReviewer();
    await api.logout();
    expect(await api.getCurrentUser()).toBeNull();
    await expect(api.getJobs()).rejects.toMatchObject({ status: 401 });
  });

  it("registers a new reviewer and refuses the same email twice (409)", async () => {
    const user = await api.register("Mohammed", "Mohammed@Simera.com", "password123");
    expect(user).toMatchObject({ role: "reviewer", email: "mohammed@simera.com" });
    await expect(api.register("Mohammed", "mohammed@simera.com", "password123")).rejects.toMatchObject({ status: 409 });
    expect((await api.login("mohammed@simera.com", "x")).full_name).toBe("Mohammed");
  });
});

describe("jobs", () => {
  beforeEach(asReviewer);

  it("returns a page with total, newest first", async () => {
    const page = await api.getJobs({ page_size: 5 });
    expect(page).toMatchObject({ total: 11, page: 1, page_size: 5 });
    expect(page.items).toHaveLength(5);
    const dates = page.items.map((j) => j.posted_at ?? "");
    expect([...dates].sort().reverse()).toEqual(dates);
  });

  it("filters by status and searches the title or the company", async () => {
    expect((await api.getJobs({ status: "needs_review" })).items.map((j) => j.title)).toEqual(["Video Annotation"]);
    expect((await api.getJobs({ q: "ledger" })).total).toBe(2);
    expect((await api.getJobs({ q: "qa engineer" })).items[0].company_name).toBe("Online Doctor AG");
  });

  it("gives the detail with requirements, null requirements for a discovered job, and 404", async () => {
    expect((await api.getJob(3)).requirements?.fit_score).toBe(85);
    expect((await api.getJob(9)).requirements).toBeNull();
    await expect(api.getJob(999)).rejects.toMatchObject({ status: 404 });
  });

  it("saves corrected requirements: the job goes back to parsed without a fit score", async () => {
    const job = await api.updateRequirements(7, { required_skills: ["video annotation"] });
    expect(job.status).toBe("parsed");
    expect(job.requirements).toMatchObject({ required_skills: ["video annotation"], fit_score: null, flag_reason: null });
  });

  it("returns a copy, so a screen cannot change the fake data", async () => {
    const first = await api.getJob(1);
    first.title = "CHANGED";
    expect((await api.getJob(1)).title).toBe("Senior Customer Success Manager");
  });
});

describe("leads and drafts", () => {
  beforeEach(asReviewer);

  it("returns leads with the highest score first", async () => {
    const leads = await api.getLeads();
    expect(leads.items.slice(0, 4).map((l) => l.lead_score)).toEqual([97, 85, 72, 0]);
  });

  it("gives the review page: evidence jobs only, newest draft, contact", async () => {
    const lead = await api.getLead(1);
    expect(lead.jobs.map((j) => j.fit_score)).toEqual([92, 78]);
    expect(lead.draft).toMatchObject({ version: 2, status: "pending_review" });
    expect(lead.company.contact_name).toBeNull();
    const od = await api.getLead(2);
    expect(od.jobs.map((j) => j.job_id)).toEqual([3]); // the 55 job is not evidence
  });

  it("approves the newest draft once; a second decision is 409", async () => {
    const draft = await api.approveDraft(2);
    expect(draft.status).toBe("approved");
    expect((await api.getLead(1)).status).toBe("approved");
    await expect(api.rejectDraft(2, "late")).rejects.toMatchObject({ status: 409 });
  });

  it("saves the name of the logged-in reviewer on every decision", async () => {
    await api.login("lilian@simera.com", "anything");
    expect((await api.approveDraft(2)).reviewed_by).toBe("Lilian Abu Ramadan");
    await api.login("nadeen@simera.com", "anything");
    expect((await api.editDraft(3, { subject: "New subject", body: "one two three" })).reviewed_by).toBe("Nadeen Shadeed");
    expect((await api.rejectDraft(3, "too long")).reviewed_by).toBe("Nadeen Shadeed");
  });

  it("refuses to reject without a comment (422) and keeps the comment", async () => {
    await expect(api.rejectDraft(3, "  ")).rejects.toMatchObject({ status: 422 });
    expect((await api.rejectDraft(3, "too long")).review_comment).toBe("too long");
    expect((await api.getLead(2)).status).toBe("rejected");
  });

  it("edits a draft: status edited and the word count is counted again", async () => {
    const d = await api.editDraft(3, { subject: "New subject", body: "one two three" });
    expect(d).toMatchObject({ status: "edited", word_count: 3, subject: "New subject" });
  });

  it("cannot review an old version", async () => {
    await expect(api.approveDraft(1)).rejects.toMatchObject({ status: 409 });
  });

  it("regenerates a new version, but not for approved or not qualified companies", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const next = api.regenerateDraft(1);
    await vi.runAllTimersAsync();
    expect((await next).version).toBe(3);
    const approved = api.regenerateDraft(3).catch((e) => e);
    const notQualified = api.regenerateDraft(4).catch((e) => e);
    await vi.runAllTimersAsync();
    expect(await approved).toMatchObject({ status: 409 });
    expect(await notQualified).toMatchObject({ status: 409 });
  });

  it("saves a contact and refuses a wrong email", async () => {
    await expect(api.updateContact(1, { contact_name: "Sam", contact_title: null, contact_email: "nope" })).rejects.toMatchObject({ status: 422 });
    expect((await api.updateContact(1, { contact_name: "Sam Lee", contact_title: "COO", contact_email: "sam@helix.example" })).contact_name).toBe("Sam Lee");
  });
});

describe("pipeline and settings", () => {
  it("lets only admins run the pipeline or change settings (403)", async () => {
    await asReviewer();
    await expect(api.startRun()).rejects.toMatchObject({ status: 403 });
    await expect(api.updateSettings({ lead_threshold: 70 })).rejects.toMatchObject({ status: 403 });
    expect((await api.getSettings()).lead_threshold).toBe(60); // reading is fine
  });

  it("starts one run at a time: the second is 409 until the first finishes", async () => {
    await asAdmin();
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    /** run a fake call while moving the fake clock, so its small delay passes */
    async function tick<T>(promise: Promise<T>, ms = 200): Promise<T> {
      await vi.advanceTimersByTimeAsync(ms);
      return promise;
    }
    const { run_id } = await tick(api.startRun());
    expect((await tick(api.getRuns(1)))[0]).toMatchObject({ run_id, status: "running" });
    expect(await tick(api.startRun().catch((e) => e))).toMatchObject({ status: 409 });
    await vi.advanceTimersByTimeAsync(6000);
    expect((await tick(api.getRun(run_id))).status).toBe("completed");
  });

  it("checks settings with the backend limits (422)", async () => {
    await asAdmin();
    await expect(api.updateSettings({ lead_threshold: 150 })).rejects.toMatchObject({ status: 422 });
    expect((await api.updateSettings({ lead_threshold: 80, run_mode: "scheduled" })).lead_threshold).toBe(80);
  });
});
