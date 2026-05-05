import { useEffect, useState, useCallback } from "react";

export interface LiveTrade {
  id: number;
  timestamp: string;
  session: string;
  date: string; // YYYYMMDD
  direction: number; // 1 = long, -1 = short
  entry_price: number;
  stop_price: number;
  tp1_price: number;
  tp2_price: number;
  exit_type: string;
  tp1_hit: number; // 0 or 1
  exit_timestamp: string;
  config_name: string;
  r_result: number | null;
  entry_timestamp?: string | null;
  ticker?: string | null;
  exec_ticker?: string | null;
  leg?: string | null;
  notes: string | null;
}

interface LiveTradesResponse {
  trades: LiveTrade[];
  total: number;
}

export function useLiveTrades() {
  const [trades, setTrades] = useState<LiveTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrades = useCallback(() => {
    fetch("/exec-api/trades/history?source=db&limit=2000")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: LiveTradesResponse) => {
        setTrades(data.trades);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Initial fetch + poll every 30s
  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 30_000);
    return () => clearInterval(interval);
  }, [fetchTrades]);

  return { trades, loading, error, refetch: fetchTrades };
}
