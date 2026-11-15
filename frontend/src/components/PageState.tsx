import { errorText } from "../format";

export function Loading() {
  return <p className="state">Loading…</p>;
}

/** An error with a Retry button. 404 shows its own message. */
export function LoadError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state">
      <p style={{ marginBottom: 12 }}>{errorText(error)}</p>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}
