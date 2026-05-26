import { useState, useCallback, useEffect, useRef } from "react";
import type { BacktestMapping } from "@/execution/lib/types";
import type { EquityCurvePoint, Trade } from "@/backtesting/lib/types";

const STORAGE_KEY = "exec_backtest_mappings";

const DEFAULT_MAPPINGS: Record<string, BacktestMapping> = {
  "ALPHA_V1-A": { backtestId: "bt-exec-exact-alpha-v1-a-last-5y-2021-03-25-to-2026-b56228", deployDate: "2026-04-05" },
  FAST: { backtestId: "bt-exec-exact-fast-last-5y-2021-03-25-to-2026-03-24-6d76c8", deployDate: "2026-03-09" },
  FAST_V2: { backtestId: "bt-exec-fast-v2-2024-2026-live-comparison-918820", deployDate: "2026-03-09" },
};

interface BacktestCurveData {
  curve: { date: string; r: number }[];
  riskUsd: number;
}

type BacktestTradeWithNetR = Trade & {
  net_r_multiple?: number | null;
  net_pnl_usd?: number | null;
};

function buildBacktestRCurve(
  trades: BacktestTradeWithNetR[],
  equityCurve: EquityCurvePoint[],
  riskUsd: number,
): { date: string; r: number }[] {
  if (trades.length > 0) {
    let cumulativeR = 0;
    return trades.map((trade) => {
      const r = trade.r_multiple ?? trade.net_r_multiple;
      if (r != null) cumulativeR += r;
      return {
        date: trade.exit_time?.slice(0, 10) || trade.date,
        r: cumulativeR,
      };
    });
  }

  return equityCurve.map((p) => ({
    date: p.date,
    r: p.pnl_cumulative / riskUsd,
  }));
}

interface UseBacktestComparisonReturn {
  mappings: Record<string, BacktestMapping>;
  setMapping: (configName: string, mapping: BacktestMapping) => void;
  backtestCurves: Record<string, BacktestCurveData | null>;
  loading: Record<string, boolean>;
  errors: Record<string, string | null>;
}

function loadMappings(): Record<string, BacktestMapping> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const stored = JSON.parse(raw);
      // Defaults take priority — stored values are only kept for configs
      // not present in DEFAULT_MAPPINGS (e.g. user-added configs)
      return { ...stored, ...DEFAULT_MAPPINGS };
    }
  } catch {
    // ignore corrupt localStorage
  }
  return { ...DEFAULT_MAPPINGS };
}

function saveMappings(mappings: Record<string, BacktestMapping>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(mappings));
}

export function useBacktestComparison(): UseBacktestComparisonReturn {
  const [mappings, setMappings] = useState<Record<string, BacktestMapping>>(loadMappings);
  const [backtestCurves, setBacktestCurves] = useState<Record<string, BacktestCurveData | null>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const fetchedIds = useRef<Record<string, string>>({});

  const setMapping = useCallback((configName: string, mapping: BacktestMapping) => {
    setMappings((prev) => {
      const next = { ...prev, [configName]: mapping };
      saveMappings(next);
      return next;
    });
  }, []);

  // Fetch backtest data when backtestId changes
  useEffect(() => {
    for (const [configName, mapping] of Object.entries(mappings)) {
      const { backtestId } = mapping;
      if (!backtestId || fetchedIds.current[configName] === backtestId) continue;
      fetchedIds.current[configName] = backtestId;

      setLoading((prev) => ({ ...prev, [configName]: true }));
      setErrors((prev) => ({ ...prev, [configName]: null }));

      fetch(`/bt-api/backtests/${backtestId}`)
        .then(async (res) => {
          if (!res.ok) throw new Error(`Backtest "${backtestId}" not found`);
          const json = await res.json();
          const data = json.result ?? json;
          const riskUsd: number = data.config?.risk_usd ?? 1;
          const equityCurve: EquityCurvePoint[] = data.equity_curve ?? [];
          const trades: BacktestTradeWithNetR[] = data.trades ?? [];
          const curve = buildBacktestRCurve(trades, equityCurve, riskUsd);
          setBacktestCurves((prev) => ({ ...prev, [configName]: { curve, riskUsd } }));
          setErrors((prev) => ({ ...prev, [configName]: null }));
        })
        .catch((err) => {
          setErrors((prev) => ({ ...prev, [configName]: err.message }));
          setBacktestCurves((prev) => ({ ...prev, [configName]: null }));
          // Allow re-fetch on retry
          delete fetchedIds.current[configName];
        })
        .finally(() => {
          setLoading((prev) => ({ ...prev, [configName]: false }));
        });
    }
  }, [mappings]);

  return { mappings, setMapping, backtestCurves, loading, errors };
}
