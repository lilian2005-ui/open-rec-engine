import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { loadDashboard } from "./dashboard";

function fakeLocalStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

beforeEach(async () => {
  vi.stubGlobal("localStorage", fakeLocalStorage());
  api.resetMockData();
  await api.login("nadeen@simera.com", "x"); // a reviewer can see the dashboard too
});

describe("dashboard numbers (fake data)", () => {
  it("counts jobs, leads and drafts from the list totals", async () => {
    const d = await loadDashboard();
    expect(d.discovered).toBe(11);
    expect(d.scored).toBe(7);
    expect(d.qualified).toBe(3);
    expect(d.draftsWaiting).toBe(2);
    expect(d.needsReview).toBeGreaterThan(0);
  });

  it("shows at most 3 top companies, best first, without not-qualified ones", async () => {
    const { topLeads } = await loadDashboard();
    expect(topLeads.length).toBeLessThanOrEqual(3);
    expect(topLeads.every((l) => l.status !== "not_qualified")).toBe(true);
    const scores = topLeads.map((l) => l.lead_score);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
  });

  it("returns the newest run as the last run", async () => {
    const { lastRun } = await loadDashboard();
    expect(lastRun?.run_id).toBe((await api.getRuns(1))[0].run_id);
  });
});