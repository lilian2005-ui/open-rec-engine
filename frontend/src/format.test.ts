import { describe, expect, it } from "vitest";
import { formatSalary, formatTimezones, label, runErrors, runStages, timeAgo } from "./format";
import type { PipelineRun } from "./types";
import { parseList, parseOffsets, registerProblems, requirementsProblems } from "./validation";

const run = (errors: PipelineRun["errors"]): PipelineRun => ({ run_id: 1, status: "completed", trigger_type: "manual",
  started_at: "", finished_at: null, jobs_fetched: 0, jobs_new: 0, jobs_updated: 0, errors, started_by: null });

describe("format", () => {
  it("shows statuses and empty values for people", () => {
    expect(label("needs_review")).toBe("Needs review");
    expect(formatTimezones([-5, -4])).toBe("UTC-5, UTC-4");
    expect(formatTimezones([])).toBeNull();
    expect(formatSalary({ salary_min: null, salary_max: null, salary_currency: null, salary_period: null })).toBeNull();
    expect(formatSalary({ salary_min: 85000, salary_max: 105000, salary_currency: "USD", salary_period: "annual" })).toBe("85,000–105,000 USD / year");
    expect(timeAgo("2026-01-01T10:00:00Z", new Date("2026-01-01T12:00:00Z"))).toBe("2h ago");
  });

  it("reads run errors in both shapes (contract list, or P1-6 stages + errors)", () => {
    expect(runErrors(run(["boom"]))).toEqual([{ message: "boom" }]);
    expect(runStages(run([]))).toEqual([]);
    const both = run({ stages: [{ stage: "drafts", result: "2 created" }], errors: [{ stage: "drafts", message: "x" }] });
    expect(runStages(both)).toHaveLength(1);
    expect(runErrors(both)[0].stage).toBe("drafts");
  });
});

describe("validation", () => {
  it("checks the register form before sending", () => {
    expect(registerProblems("Lilian", "password1", "password1")).toEqual([]);
    expect(registerProblems("L", "short", "other")).toHaveLength(3);
  });

  it("parses skills and timezones", () => {
    expect(parseList("React, TypeScript ,, react")).toEqual(["react", "typescript"]);
    expect(parseOffsets("-5, UTC-4")).toEqual([-5, -4]);
    expect(parseOffsets("25")).toBeNull();
  });

  it("checks requirements with the backend limits", () => {
    expect(requirementsProblems({ required_skills: ["a"], min_years_experience: -3 })).toHaveLength(1);
    expect(requirementsProblems({ required_skills: [], salary_min: 10, salary_max: 5 })).toHaveLength(2);
  });
});
