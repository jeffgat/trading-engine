import { useState, useCallback, useEffect, useRef } from "react";
import type { BacktestHistoryItem, BacktestResult } from "../lib/types";

const POLL_INTERVAL_MS = 5000;

interface UseHistoryReturn {
  history: BacktestHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadBacktest: (id: string) => Promise<BacktestResult | null>;
  deleteBacktest: (id: string) => Promise<void>;
  setActiveId: (id: string | null) => void;
}

export function useBacktestHistory(): UseHistoryReturn {
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const refreshHistory = useCallback(async () => {
    if (initialLoad.current) {
      setLoading(true);
      initialLoad.current = false;
    }
    try {
      const res = await fetch("/api/backtests");
      if (res.ok) {
        const data = await res.json();
        setHistory(data.result ?? data);
      }
    } catch {
      // API unavailable — leave history empty
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBacktest = useCallback(async (id: string): Promise<BacktestResult | null> => {
    try {
      const res = await fetch(`/api/backtests/${id}`);
      if (!res.ok) return null;
      const json = await res.json();
      const data: BacktestResult = json.result ?? json;
      setActiveId(id);
      return data;
    } catch {
      return null;
    }
  }, []);

  const deleteBacktest = useCallback(async (id: string) => {
    try {
      await fetch(`/api/backtests/${id}`, { method: "DELETE" });
      if (activeId === id) setActiveId(null);
      await refreshHistory();
    } catch {
      // ignore
    }
  }, [activeId, refreshHistory]);

  useEffect(() => {
    refreshHistory();
    const id = setInterval(refreshHistory, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshHistory]);

  return { history, loading, activeId, refreshHistory, loadBacktest, deleteBacktest, setActiveId };
}
