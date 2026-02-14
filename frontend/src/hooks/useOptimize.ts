import { useState, useCallback } from "react";
import type { OptimizationResult } from "../lib/types";

interface OptimizeParams {
  instrument?: string;
  sessions?: string[];
  start?: string;
  end?: string;
  sweeps: Record<string, string>;
  metric?: string;
}

interface UseOptimizeReturn {
  data: OptimizationResult | null;
  loading: boolean;
  error: string | null;
  runOptimize: (params: OptimizeParams) => Promise<string | null>;
  setData: (data: OptimizationResult | null) => void;
}

export function useOptimize(): UseOptimizeReturn {
  const [data, setData] = useState<OptimizationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runOptimize = useCallback(async (params: OptimizeParams): Promise<string | null> => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }

      const result: OptimizationResult = await res.json();
      setData(result);
      return result.id ?? null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, runOptimize, setData };
}
