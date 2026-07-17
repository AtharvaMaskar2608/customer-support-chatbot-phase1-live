import { useCallback, useState } from 'react';

/**
 * useState backed by localStorage. Used for the web frame's open/collapsed
 * state and its dragged position, so both persist across reloads (spec: web
 * frame position persists via localStorage). SECURITY: only UI state is ever
 * stored here — never the access_token or session_id.
 */
export function usePersistedState<T>(key: string, initial: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw != null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* ignore quota/availability errors — persistence is best-effort */
      }
    },
    [key],
  );

  return [value, set];
}
