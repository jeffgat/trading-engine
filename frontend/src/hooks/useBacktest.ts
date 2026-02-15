import { useState, useCallback } from "react";
import type { BacktestResult } from "../lib/types";

interface BacktestParams {
  instrument?: string;
  sessions?: string[];
  start?: string;
  end?: string;
  [key: string]: unknown;
}

interface UseBacktestReturn {
  data: BacktestResult | null;
  loading: boolean;
  error: string | null;
  runBacktest: (params?: BacktestParams) => Promise<string | null>;
  setData: (data: BacktestResult | null) => void;
}

export function useBacktest(): UseBacktestReturn {
  const [data, setData] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = useCallback(async (params?: BacktestParams): Promise<string | null> => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params ?? {}),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
      }

      const json = await res.json();
      const result: BacktestResult = json.result ?? json;
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

  return { data, loading, error, runBacktest, setData };
}
