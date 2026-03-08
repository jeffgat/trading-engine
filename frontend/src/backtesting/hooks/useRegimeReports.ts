import { useCallback, useEffect, useState } from "react";
import type { RegimeReportHistoryItem, RegimeReportResult } from "@/backtesting/lib/types";

export function useRegimeReports() {
  const [history, setHistory] = useState<RegimeReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/bt-api/regime-reports?limit=200");
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

  const loadReport = useCallback(async (resultId: string): Promise<RegimeReportResult | null> => {
    try {
      const res = await fetch(`/bt-api/regime-reports/${resultId}`);
      if (!res.ok) return null;
      const json = await res.json();
      return json.result ?? json;
    } catch {
      return null;
    }
  }, []);

  const deleteReport = useCallback(async (resultId: string) => {
    try {
      await fetch(`/bt-api/regime-reports/${resultId}`, { method: "DELETE" });
      setHistory((h) => h.filter((r) => r.result_id !== resultId));
    } catch {
      // silent
    }
  }, []);

  const createReport = useCallback(async (backtestResultId: string, method: string) => {
    const res = await fetch("/bt-api/regime-reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backtest_result_id: backtestResultId, method }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
    }
    const json = await res.json();
    const report: RegimeReportResult = json.result ?? json;
    await refresh();
    return report;
  }, [refresh]);

  return { history, loading, refresh, loadReport, deleteReport, createReport };
}
