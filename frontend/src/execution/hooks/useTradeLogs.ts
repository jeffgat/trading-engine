import { useCallback, useEffect, useRef, useState } from "react";
import type { LogResponse, TradeLogEntry } from "@/execution/lib/types";

const MAX_ENTRIES = 500;

export function useTradeLogs(
  subscribe: (type: string, cb: (data: unknown) => void) => () => void,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const [entries, setEntries] = useState<TradeLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const initialFetchDone = useRef(false);

  // Initial fetch (newest first)
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    fetch("/exec-api/logs/trades?limit=500&offset=0")
      .then((r) => r.json())
      .then((data: LogResponse<TradeLogEntry>) => {
        setEntries(data.entries);
        setTotal(data.total);
        setLoading(false);
        initialFetchDone.current = true;
      })
      .catch(() => setLoading(false));
  }, [enabled]);

  // WebSocket — prepend new entries
  const handleNew = useCallback((data: unknown) => {
    if (!initialFetchDone.current) return;
    const entry = data as TradeLogEntry;
    setEntries((prev) => [entry, ...prev].slice(0, MAX_ENTRIES));
    setTotal((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    return subscribe("trade_log", handleNew);
  }, [enabled, subscribe, handleNew]);

  // Load older entries
  const loadMore = useCallback(() => {
    if (!enabled) return;
    const offset = entries.length;
    fetch(`/exec-api/logs/trades?limit=100&offset=${offset}`)
      .then((r) => r.json())
      .then((data: LogResponse<TradeLogEntry>) => {
        setEntries((prev) => [...prev, ...data.entries]);
      });
  }, [enabled, entries.length]);

  return { entries, total, loading, loadMore };
}
