import { useState, useEffect, useCallback } from "react";
import type {
  NewsStraddleHistoryItem,
  NewsStraddleResult,
} from "@/backtesting/lib/types";

export function useNewsStraddleHistory() {
  const [history, setHistory] = useState<NewsStraddleHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/bt-api/news-straddle/runs?limit=100");
      if (!res.ok) return;
      const json = await res.json();
      setHistory(json.result ?? json);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loadRun = useCallback(
    async (resultId: string): Promise<NewsStraddleResult | null> => {
      try {
        const res = await fetch(`/bt-api/news-straddle/runs/${resultId}`);
        if (!res.ok) return null;
        const json = await res.json();
        return json.result ?? json;
      } catch {
        return null;
      }
    },
    []
  );

  const deleteRun = useCallback(
    async (resultId: string) => {
      try {
        await fetch(`/bt-api/news-straddle/runs/${resultId}`, {
          method: "DELETE",
        });
        setHistory((h) => h.filter((r) => r.result_id !== resultId));
      } catch {
        // silent
      }
    },
    []
  );

  return { history, loading, refresh, loadRun, deleteRun };
}
