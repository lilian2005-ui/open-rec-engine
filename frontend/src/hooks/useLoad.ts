import { useCallback, useEffect, useRef, useState } from "react";

interface Result<T> {
  key: string | null;
  data: T | null;
  error: unknown;
}

/**
 * Load data for a screen: { data, error, loading, reload, setData }.
 * `load` runs again when `key` changes (for example the page number or the id).
 * While a new answer comes, the old data stays on screen; old answers are ignored.
 */
export function useLoad<T>(load: () => Promise<T>, key: string) {
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T>>({ key: null, data: null, error: null });
  const requestKey = `${key}#${version}`;

  useEffect(() => {
    let current = true;
    loadRef.current()
      .then((data) => current && setResult({ key: requestKey, data, error: null }))
      .catch((error) => current && setResult((prev) => ({ key: requestKey, data: prev.data, error })));
    return () => {
      current = false;
    };
  }, [requestKey]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const setData = useCallback((data: T) => setResult((prev) => ({ ...prev, data })), []);
  const loading = result.key !== requestKey;
  return { data: result.data, error: loading ? null : result.error, loading, reload, setData };
}
