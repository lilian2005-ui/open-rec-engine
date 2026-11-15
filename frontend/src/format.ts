/** Small helpers that turn API values into text for the screens. No React here. */
import type { JobRequirements, PipelineRun, RunError, RunStage } from "./types";

/** "draft_ready" -> "Draft ready" */
export function label(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Old name kept for code that still uses it: "draft_ready" -> "DRAFT READY". */
export function displayStatus(value: string): string {
  return value.replace(/_/g, " ").toUpperCase();
}

/** Word count with the same rule as the backend (split on whitespace). */
export function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

/** "2h ago", "3d ago". */
export function timeAgo(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "–";
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** "Nov 15, 09:12 AM" in the viewer's own time zone. */
export function formatDate(iso: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** "6 min" between two dates, or "running…" if not finished. */
export function duration(start: string, end: string | null): string {
  if (!end) return "running…";
  const minutes = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000);
  return minutes < 1 ? "< 1 min" : `${minutes} min`;
}

/** [-5, -4] -> "UTC-5, UTC-4"; empty -> null (shown as "Not stated"). */
export function formatTimezones(offsets: number[] | null): string | null {
  if (!offsets || offsets.length === 0) return null;
  return offsets.map((o) => (o === 0 ? "UTC" : `UTC${o > 0 ? "+" : ""}${o}`)).join(", ");
}

/** 85000-105000 USD annual -> "85,000–105,000 USD / year"; nothing stated -> null. */
export function formatSalary(r: Pick<JobRequirements, "salary_min" | "salary_max" | "salary_currency" | "salary_period">): string | null {
  if (r.salary_min == null && r.salary_max == null) return null;
  const n = (v: number | null) => (v == null ? "?" : v.toLocaleString("en-US"));
  const range = r.salary_min === r.salary_max || r.salary_max == null ? n(r.salary_min) : `${n(r.salary_min)}–${n(r.salary_max)}`;
  const period = r.salary_period ? ` / ${r.salary_period === "annual" ? "year" : r.salary_period.replace("ly", "")}` : "";
  return `${range}${r.salary_currency ? ` ${r.salary_currency}` : ""}${period}`;
}

/** Score color group, used by rings and pills. */
export function scoreTone(score: number | null, threshold = 60): "high" | "mid" | "low" {
  if (score == null) return "low";
  if (score >= 80) return "high";
  if (score >= threshold) return "mid";
  return "low";
}

/** The stage results of a run (empty if the backend saved only an error list). */
export function runStages(run: PipelineRun): RunStage[] {
  const e = run.errors;
  return e && !Array.isArray(e) ? (e.stages ?? []) : [];
}

/** The errors of a run, always as a list of { stage, message }. */
export function runErrors(run: PipelineRun): RunError[] {
  const e = run.errors;
  const list = !e ? [] : Array.isArray(e) ? e : (e.errors ?? []);
  return list.map((item) => (typeof item === "string" ? { message: item } : item));
}

/** Error text from the API, for example {"detail": "..."} -> "...". */
export function errorText(error: unknown): string {
  if (error instanceof Error) {
    try {
      const parsed = JSON.parse(error.message);
      if (typeof parsed?.detail === "string") return parsed.detail;
      if (Array.isArray(parsed?.detail)) return parsed.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* not JSON, use the text as it is */
    }
    return error.message;
  }
  return "Something went wrong";
}
