import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api";
import { errorText } from "../format";
import type { PipelineRun } from "../types";

const POLL_MS = 3000;

/**
 * Start a run and follow it: POST /pipeline/run answers at once with run_id,
 * then we ask GET /pipeline/runs/{id} every 3 seconds until it is not "running".
 * `onFinished` is called once at the end, so the screen can reload its data.
 */
export function usePipelineRun(onFinished?: (run: PipelineRun) => void) {
  const [running, setRunning] = useState<PipelineRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const finished = useRef(onFinished);
  useEffect(() => {
    finished.current = onFinished;
  }, [onFinished]);

  // a run started from another tab or by the schedule also disables the button
  useEffect(() => {
    api.getRuns(1).then((runs) => {
      if (runs[0]?.status === "running") setRunning(runs[0]);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const run = await api.getRun(running.run_id);
        if (run.status !== "running") {
          setRunning(null);
          finished.current?.(run);
        }
      } catch {
        /* keep trying; the next tick asks again */
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const { run_id } = await api.startRun();
      setRunning(await api.getRun(run_id));
    } catch (e) {
      setError(e instanceof api.ApiError && e.status === 409 ? "A run is already in progress" : errorText(e));
    }
  }, []);

  return { running, error, start };
}
