import { useCallback, useEffect, useRef, useState } from "react";
import type { LogResponse, MainLogEntry } from "@/lib/types";

const MAX_ENTRIES = 500;

export function useMainLogs(
  subscribe: (type: string, cb: (data: unknown) => void) => () => void,
) {
  const [entries, setEntries] = useState<MainLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const initialFetchDone = useRef(false);

  // Initial fetch (newest first)
  useEffect(() => {
    fetch("/api/logs/main?limit=100&offset=0")
      .then((r) => r.json())
      .then((data: LogResponse<MainLogEntry>) => {
        setEntries(data.entries);
        setTotal(data.total);
        setLoading(false);
        initialFetchDone.current = true;
      })
      .catch(() => setLoading(false));
  }, []);

  // WebSocket — prepend new entries
  const handleNew = useCallback((data: unknown) => {
    if (!initialFetchDone.current) return;
    const entry = data as MainLogEntry;
    setEntries((prev) => [entry, ...prev].slice(0, MAX_ENTRIES));
    setTotal((prev) => prev + 1);
  }, []);

  useEffect(() => {
    return subscribe("log", handleNew);
  }, [subscribe, handleNew]);

  // Load older entries
  const loadMore = useCallback(() => {
    const offset = entries.length;
    fetch(`/api/logs/main?limit=100&offset=${offset}`)
      .then((r) => r.json())
      .then((data: LogResponse<MainLogEntry>) => {
        setEntries((prev) => [...prev, ...data.entries]);
      });
  }, [entries.length]);

  return { entries, total, loading, loadMore };
}
