/** Form checks done in the browser before sending, with the same limits as the backend. */
import type { RequirementsUpdate } from "./types";

/** UserCreate: name 2-100, password 8-72. */
export function registerProblems(name: string, password: string, confirm: string): string[] {
  const problems: string[] = [];
  if (name.trim().length < 2 || name.trim().length > 100) problems.push("Name must be 2 to 100 characters");
  if (password.length < 8 || password.length > 72) problems.push("Password must be 8 to 72 characters");
  if (password !== confirm) problems.push("The two passwords are not the same");
  return problems;
}

/** "React, TypeScript ,," -> ["react", "typescript"] (lowercase, like the backend). */
export function parseList(text: string): string[] {
  return [...new Set(text.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean))];
}

/** "-5, -4" -> [-5, -4]; null if a value is not a whole hour from -12 to 14. */
export function parseOffsets(text: string): number[] | null {
  const parts = text.split(",").map((s) => s.trim().replace(/^utc/i, "")).filter(Boolean);
  const values = parts.map(Number);
  if (values.some((v) => !Number.isInteger(v) || v < -12 || v > 14)) return null;
  return values;
}

/** JobRequirements limits: experience 0-50, salary min <= max, at least one required skill. */
export function requirementsProblems(r: RequirementsUpdate): string[] {
  const problems: string[] = [];
  const years = r.min_years_experience;
  if (years != null && (!Number.isInteger(years) || years < 0 || years > 50)) problems.push("Experience must be a whole number from 0 to 50");
  if (r.salary_min != null && r.salary_min < 0) problems.push("Salary cannot be negative");
  if (r.salary_min != null && r.salary_max != null && r.salary_min > r.salary_max) problems.push("Minimum salary is higher than maximum");
  if (r.salary_currency && !/^[A-Za-z]{3}$/.test(r.salary_currency)) problems.push("Currency must be 3 letters, for example USD");
  if (!r.required_skills || r.required_skills.length === 0) problems.push("Add at least one required skill");
  return problems;
}
