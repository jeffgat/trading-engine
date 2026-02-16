import { useState, useCallback, useEffect, useRef } from "react";
import type { OptimizationHistoryItem, OptimizationResult } from "../lib/types";

const POLL_INTERVAL_MS = 5000;

interface UseOptimizationHistoryReturn {
  history: OptimizationHistoryItem[];
  loading: boolean;
  activeId: string | null;
  refreshHistory: () => Promise<void>;
  loadOptimization: (id: string) => Promise<OptimizationResult | null>;
  refilterOptimization: (id: string, start?: string, end?: string) => Promise<OptimizationResult | null>;
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
        const data = await res.json();
        setHistory(data.result ?? data);
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
      const json = await res.json();
      const data: OptimizationResult = json.result ?? json;
      setActiveId(id);
      return data;
    } catch {
      return null;
    }
  }, []);

  const refilterOptimization = useCallback(async (id: string, start?: string, end?: string): Promise<OptimizationResult | null> => {
    try {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      const qs = params.toString();
      const url = `/api/optimizations/${id}${qs ? `?${qs}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      const json = await res.json();
      return json.result ?? json;
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

  return { history, loading, activeId, refreshHistory, loadOptimization, refilterOptimization, deleteOptimization, setActiveId };
}
