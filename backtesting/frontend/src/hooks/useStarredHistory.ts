import { useState, useCallback, useEffect, useRef } from "react";
import type { BacktestHistoryItem, BacktestResult } from "../lib/types";

const POLL_INTERVAL_MS = 5000;

interface UseStarredReturn {
  history: BacktestHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadBacktest: (id: string) => Promise<BacktestResult | null>;
  refilterBacktest: (id: string, start?: string, end?: string) => Promise<BacktestResult | null>;
  unstarBacktest: (id: string) => Promise<void>;
  hideBacktest: (id: string) => Promise<boolean>;
  renameBacktest: (id: string, newName: string) => Promise<boolean>;
  bulkUnstarBacktests: (ids: string[]) => Promise<void>;
  bulkHideBacktests: (ids: string[]) => Promise<void>;
  setActiveId: (id: string | null) => void;
}

export function useStarredHistory(): UseStarredReturn {
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
      const res = await fetch("/api/starred");
      if (res.ok) {
        const data = await res.json();
        setHistory(data.result ?? data);
      }
    } catch {
      // API unavailable
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

  const refilterBacktest = useCallback(async (id: string, start?: string, end?: string): Promise<BacktestResult | null> => {
    try {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      const qs = params.toString();
      const url = `/api/backtests/${id}${qs ? `?${qs}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      const json = await res.json();
      return json.result ?? json;
    } catch {
      return null;
    }
  }, []);

  const unstarBacktest = useCallback(async (id: string) => {
    try {
      await fetch(`/api/backtests/${id}/star`, { method: "POST" });
      if (activeId === id) setActiveId(null);
      await refreshHistory();
    } catch {
      // ignore
    }
  }, [activeId, refreshHistory]);

  const hideBacktest = useCallback(async (id: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/backtests/${id}/hide`, { method: "POST" });
      if (!res.ok) return false;
      const json = await res.json();
      const hidden: boolean = json.result?.hidden ?? false;
      await refreshHistory();
      return hidden;
    } catch {
      return false;
    }
  }, [refreshHistory]);

  const renameBacktest = useCallback(async (id: string, newName: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/backtests/${id}/name`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName }),
      });
      if (!res.ok) return false;
      await refreshHistory();
      return true;
    } catch {
      return false;
    }
  }, [refreshHistory]);

  const bulkUnstarBacktests = useCallback(async (ids: string[]) => {
    const toUnstar = ids.filter((id) => {
      const item = history.find((h) => h.id === id);
      return item && item.starred;
    });
    if (toUnstar.length > 0) {
      await Promise.all(toUnstar.map((id) => fetch(`/api/backtests/${id}/star`, { method: "POST" })));
      await refreshHistory();
    }
  }, [history, refreshHistory]);

  const bulkHideBacktests = useCallback(async (ids: string[]) => {
    const toHide = ids.filter((id) => {
      const item = history.find((h) => h.id === id);
      return item && !item.hidden;
    });
    if (toHide.length > 0) {
      await Promise.all(toHide.map((id) => fetch(`/api/backtests/${id}/hide`, { method: "POST" })));
      await refreshHistory();
    }
  }, [history, refreshHistory]);

  useEffect(() => {
    refreshHistory();
    const id = setInterval(refreshHistory, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshHistory]);

  return { history, loading, activeId, refreshHistory, loadBacktest, refilterBacktest, unstarBacktest, hideBacktest, renameBacktest, bulkUnstarBacktests, bulkHideBacktests, setActiveId };
}
