import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getCurrentUser, getJobs, getLeadDraft, getLeads, login, logout, USE_MOCK } from "./api";

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
});

describe("api.ts in fake mode", () => {
  it("is in fake mode by default", () => {
    expect(USE_MOCK).toBe(true);
  });

  it("logs in with a known email and any password, and remembers the user", async () => {
    const user = await login("Lilian@Simera.com ", "anything");
    expect(user.email).toBe("lilian@simera.com");
    expect(user.role).toBe("admin");
    expect((await getCurrentUser())?.user_id).toBe(user.user_id);
  });

  it("refuses an unknown email or an empty password with 401", async () => {
    await expect(login("nobody@simera.com", "x")).rejects.toMatchObject({ status: 401 });
    await expect(login("lilian@simera.com", "")).rejects.toBeInstanceOf(ApiError);
    expect(await getCurrentUser()).toBeNull();
  });

  it("forgets the user after logout", async () => {
    await login("nadeen@simera.com", "x");
    await logout();
    expect(await getCurrentUser()).toBeNull();
  });

  it("returns leads with the highest score first", async () => {
    const leads = await getLeads();
    expect(leads.map((l) => l.lead_score)).toEqual([97, 86, 74, 0]);
  });

  it("returns a copy, so a screen cannot change the fake data", async () => {
    const first = await getJobs();
    first[0].title = "CHANGED";
    expect((await getJobs())[0].title).toBe("Senior React Developer");
  });

  it("returns the draft of Acme and null for a lead without a draft", async () => {
    expect((await getLeadDraft(1))?.subject).toContain("Acme Corp");
    expect(await getLeadDraft(2)).toBeNull();
  });
});