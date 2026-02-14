import { useState, useCallback, useEffect } from "react";
import type { BacktestHistoryItem, BacktestResult } from "../lib/types";

interface UseHistoryReturn {
  history: BacktestHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadBacktest: (id: string) => Promise<BacktestResult | null>;
  deleteBacktest: (id: string) => Promise<void>;
  setActiveId: (id: string | null) => void;
}

export function useHistory(): UseHistoryReturn {
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/backtests");
      if (res.ok) {
        setHistory(await res.json());
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
      const data: BacktestResult = await res.json();
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
  }, [refreshHistory]);

  return { history, loading, activeId, refreshHistory, loadBacktest, deleteBacktest, setActiveId };
}
