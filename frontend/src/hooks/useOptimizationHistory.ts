import { useState, useCallback, useEffect, useRef } from "react";
import type { OptimizationHistoryItem, OptimizationResult } from "../lib/types";

const POLL_INTERVAL_MS = 5000;

interface UseOptimizationHistoryReturn {
  history: OptimizationHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadOptimization: (id: string) => Promise<OptimizationResult | null>;
  deleteOptimization: (id: string) => Promise<void>;
  setActiveId: (id: string | null) => void;
}

export function useOptimizationHistory(): UseOptimizationHistoryReturn {
  const [history, setHistory] = useState<OptimizationHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const refreshHistory = useCallback(async () => {
    if (initialLoad.current) {
      setLoading(true);
      initialLoad.current = false;
    }
    try {
      const res = await fetch("/api/optimizations");
      if (res.ok) {
        setHistory(await res.json());
      }
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOptimization = useCallback(async (id: string): Promise<OptimizationResult | null> => {
    try {
      const res = await fetch(`/api/optimizations/${id}`);
      if (!res.ok) return null;
      const data: OptimizationResult = await res.json();
      setActiveId(id);
      return data;
    } catch {
      return null;
    }
  }, []);

  const deleteOptimization = useCallback(async (id: string) => {
    try {
      await fetch(`/api/optimizations/${id}`, { method: "DELETE" });
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

  return { history, loading, activeId, refreshHistory, loadOptimization, deleteOptimization, setActiveId };
}
