import { useState, useCallback, useEffect, useRef } from "react";
import type { BacktestHistoryItem, BacktestResult } from "@/backtesting/lib/types";

const POLL_INTERVAL_MS = 5000;

interface UseHistoryReturn {
  history: BacktestHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadBacktest: (id: string) => Promise<BacktestResult | null>;
  refilterBacktest: (id: string, start?: string, end?: string) => Promise<BacktestResult | null>;
  deleteBacktest: (id: string) => Promise<void>;
  starBacktest: (id: string) => Promise<boolean>;
  hideBacktest: (id: string) => Promise<boolean>;
  renameBacktest: (id: string, newName: string) => Promise<boolean>;
  bulkStarBacktests: (ids: string[]) => Promise<void>;
  bulkHideBacktests: (ids: string[]) => Promise<void>;
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
      const res = await fetch("/bt-api/backtests");
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
      const res = await fetch(`/bt-api/backtests/${id}`);
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
      const url = `/bt-api/backtests/${id}${qs ? `?${qs}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      const json = await res.json();
      return json.result ?? json;
    } catch {
      return null;
    }
  }, []);

  const deleteBacktest = useCallback(async (id: string) => {
    try {
      await fetch(`/bt-api/backtests/${id}`, { method: "DELETE" });
      if (activeId === id) setActiveId(null);
      await refreshHistory();
    } catch {
      // ignore
    }
  }, [activeId, refreshHistory]);

  const starBacktest = useCallback(async (id: string): Promise<boolean> => {
    try {
      const res = await fetch(`/bt-api/backtests/${id}/star`, { method: "POST" });
      if (!res.ok) return false;
      const json = await res.json();
      const starred: boolean = json.result?.starred ?? false;
      await refreshHistory();
      return starred;
    } catch {
      return false;
    }
  }, [refreshHistory]);

  const hideBacktest = useCallback(async (id: string): Promise<boolean> => {
    try {
      const res = await fetch(`/bt-api/backtests/${id}/hide`, { method: "POST" });
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
      const res = await fetch(`/bt-api/backtests/${id}/name`, {
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

  const bulkStarBacktests = useCallback(async (ids: string[]) => {
    const toStar = ids.filter((id) => {
      const item = history.find((h) => h.id === id);
      return item && !item.starred;
    });
    if (toStar.length > 0) {
      await Promise.all(toStar.map((id) => fetch(`/bt-api/backtests/${id}/star`, { method: "POST" })));
      await refreshHistory();
    }
  }, [history, refreshHistory]);

  const bulkHideBacktests = useCallback(async (ids: string[]) => {
    const toHide = ids.filter((id) => {
      const item = history.find((h) => h.id === id);
      return item && !item.hidden;
    });
    if (toHide.length > 0) {
      await Promise.all(toHide.map((id) => fetch(`/bt-api/backtests/${id}/hide`, { method: "POST" })));
      await refreshHistory();
    }
  }, [history, refreshHistory]);

  useEffect(() => {
    refreshHistory();
    const id = setInterval(refreshHistory, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshHistory]);

  return { history, loading, activeId, refreshHistory, loadBacktest, refilterBacktest, deleteBacktest, starBacktest, hideBacktest, renameBacktest, bulkStarBacktests, bulkHideBacktests, setActiveId };
}
