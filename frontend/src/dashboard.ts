import * as api from "./api";
import type { PipelineRun } from "./types";

/** The leads that count as "qualified" on the dashboard. */
const QUALIFIED = ["qualified", "draft_ready", "approved"] as const;

/** Only the total of a list: ask for one item, read `total`. */
const countJobs = (status?: "scored" | "needs_review") =>
  api.getJobs({ status, page_size: 1 }).then((p) => p.total);
const countLeads = (status: (typeof QUALIFIED)[number]) =>
  api.getLeads({ status, page_size: 1 }).then((p) => p.total);

export async function loadDashboard() {
  const [discovered, scored, needsReview, qualified, draftsWaiting, top, runs] = await Promise.all([
    countJobs(),
    countJobs("scored"),
    countJobs("needs_review"),
    Promise.all(QUALIFIED.map(countLeads)).then((totals) => totals.reduce((a, b) => a + b, 0)),
    countLeads("draft_ready"),
    api.getLeads({ page_size: 3 }),
    // the runs endpoint may not exist yet on the real backend (#28): show "No runs yet" instead of an error
    api.getRuns(1).catch(() => [] as PipelineRun[]),
  ]);
  return {
    discovered, scored, needsReview, qualified, draftsWaiting,
    topLeads: top.items.filter((l) => l.status !== "not_qualified"),
    lastRun: runs[0] ?? null,
  };
}