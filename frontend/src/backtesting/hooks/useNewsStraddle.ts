import { useState, useCallback } from "react";
import type { NewsStraddleResult, NewsStraddleSweepResult } from "@/backtesting/lib/types";

interface RegimeFilters {
  max_atr_pct?: number | null;
  min_volume_ratio?: number | null;
  max_volume_ratio?: number | null;
  direction_filter?: string | null;
  skip_days?: number[] | null;
}

interface SingleParams extends RegimeFilters {
  buffer_points?: number;
  target_points?: number;
  event_types?: string[];
  observation_window_seconds?: number;
  instrument?: string;
  start?: string;
  end?: string;
  stop_loss_points?: number | null;
}

interface SweepParams extends RegimeFilters {
  buffer_range?: string;
  target_range?: string;
  event_types?: string[];
  observation_window_seconds?: number;
  instrument?: string;
  start?: string;
  end?: string;
  stop_loss_points?: number | null;
}

export function useNewsStraddle() {
  const [singleData, setSingleData] = useState<NewsStraddleResult | null>(null);
  const [sweepData, setSweepData] = useState<NewsStraddleSweepResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSingle = useCallback(async (params: SingleParams) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/bt-api/news-straddle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
      }
      const json = await res.json();
      const result: NewsStraddleResult = json.result ?? json;
      setSingleData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const runSweep = useCallback(async (params: SweepParams) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/bt-api/news-straddle/sweep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
      }
      const json = await res.json();
      const result: NewsStraddleSweepResult = json.result ?? json;
      setSweepData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  return { singleData, setSingleData, sweepData, loading, error, runSingle, runSweep };
}
