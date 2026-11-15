import { label } from "../format";

const TONES: Record<string, string> = {
  // jobs
  scored: "green", parsed: "blue", needs_review: "amber", failed: "red", discovered: "gray",
  // leads
  qualified: "blue", draft_ready: "blue", approved: "green", rejected: "red", not_qualified: "gray",
  // drafts
  pending_review: "amber", edited: "blue",
  // runs
  running: "blue", completed: "green", partial: "amber",
};

/** A soft colored badge for any status value: "needs_review" -> "Needs review". */
export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge tone-${TONES[status] ?? "gray"}`}>{label(status)}</span>;
}
