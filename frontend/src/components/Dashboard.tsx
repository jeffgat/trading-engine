import { useState } from "react";
import { useBacktest } from "../hooks/useBacktest";
import { useHistory } from "../hooks/useHistory";
import { StatBar } from "./StatBar";
import { EquityChart } from "./EquityChart";
import { HistoryPanel } from "./HistoryPanel";
import { TradesTable } from "./TradesTable";
import { Skeleton } from "./Skeleton";

export function Dashboard() {
  const { data, loading, error, runBacktest, setData } = useBacktest();
  const { history, activeId, refreshHistory, loadBacktest, deleteBacktest, setActiveId } =
    useHistory();
  const [historyLoading, setHistoryLoading] = useState(false);

  const isLoading = loading || historyLoading;

  const handleRun = async () => {
    const id = await runBacktest();
    if (id) {
      setActiveId(id);
      await refreshHistory();
    }
  };

  const handleLoad = async (id: string) => {
    setHistoryLoading(true);
    const result = await loadBacktest(id);
    if (result) setData(result);
    setHistoryLoading(false);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            Gat Labs BT
          </h1>
          {data?.config.instrument && !isLoading && (
            <p className="mt-0.5 text-sm text-text-muted">
              {data.config.instrument} &middot; R:R {data.config.rr} &middot; Risk $
              {data.config.risk_usd?.toLocaleString()}
            </p>
          )}
        </div>
        <button
          onClick={handleRun}
          disabled={isLoading}
          className="rounded-lg border border-border bg-bg-card px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-card-hover disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Backtest"}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-lg border border-loss/30 bg-loss/10 px-4 py-2 text-sm text-loss">
          {error}
        </div>
      )}

      {/* Main content: History sidebar + Stats/Chart */}
      <div className="flex gap-4">
        {/* History panel */}
        <div className="w-72 shrink-0">
          <HistoryPanel
            history={history}
            activeId={activeId}
            onLoad={handleLoad}
            onDelete={deleteBacktest}
            onRefresh={refreshHistory}
          />
        </div>

        {/* Stats + Chart + Trades */}
        <div className="min-w-0 flex-1">
          {isLoading && <LoadingSkeleton />}

          {!isLoading && data && (
            <div className="space-y-4">
              <StatBar summary={data.summary} trades={data.trades} />
              <EquityChart data={data.equity_curve} />
              <TradesTable trades={data.trades} />
            </div>
          )}

          {!isLoading && !data && (
            <div className="flex h-[400px] items-center justify-center text-text-muted">
              Run or select a backtest to start
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {/* Stat cards row 1 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-[88px] rounded-lg" />
        ))}
      </div>
      {/* Stat cards row 2 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-[88px] rounded-lg" />
        ))}
      </div>
      {/* Chart */}
      <Skeleton className="h-[430px] rounded-lg" />
      {/* Table */}
      <Skeleton className="h-[200px] rounded-lg" />
    </div>
  );
}
