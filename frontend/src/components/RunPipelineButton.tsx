import { usePipelineRun } from "../hooks/usePipelineRun";
import { useAuth } from "../useAuth";
import type { PipelineRun } from "../types";
import { Icon } from "./Icon";

/** The one "Run pipeline" button (Dashboard, Jobs, Settings). Admins only. */
export function RunPipelineButton({ onFinished }: { onFinished?: (run: PipelineRun) => void }) {
  const { isAdmin } = useAuth();
  const { running, error, start } = usePipelineRun(onFinished);
  if (!isAdmin) return null;
  return (
    <div style={{ textAlign: "right" }}>
      <button className="btn btn-primary" onClick={start} disabled={Boolean(running)}>
        <Icon name={running ? "refresh" : "play"} />
        {running ? `Running… (#${running.run_id})` : "Run pipeline"}
      </button>
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
