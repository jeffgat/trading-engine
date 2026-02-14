import { useMemo } from "react";
import type { Trade } from "../lib/types";
import { formatCurrency } from "../lib/utils";
import { ScrollArea } from "./ui/scroll-area";

function formatR(r: number): string {
  const sign = r >= 0 ? "+" : "";
  return `${sign}${r.toFixed(2)}R`;
}

interface TradesTableProps {
  trades: Trade[];
  riskUsd: number;
}

const EXIT_LABELS: Record<string, string> = {
  tp1_tp2: "tp1+tp2",
  tp1_flat: "tp1+flat",
  tp1_be: "tp1+be",
  stop: "sl",
  flat: "flat",
  no_fill: "no fill",
};

export function TradesTable({ trades, riskUsd }: TradesTableProps) {
  const filled = useMemo(
    () =>
      trades
        .filter((t) => t.exit_type !== "no_fill")
        .slice()
        .reverse(),
    [trades],
  );

  if (!filled.length) {
    return (
      <div className="flex h-40 items-center justify-center text-text-muted">
        No trades to display
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-bg-card">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <h2 className="text-sm font-medium text-text-secondary">Trades</h2>
        <span className="text-xs text-text-muted">{filled.length} filled</span>
      </div>

      <ScrollArea className="h-[480px]">
        <div className="min-w-[860px]">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-bg-card">
              <tr className="border-b border-border text-text-muted">
                <th className="whitespace-nowrap px-4 py-2 font-medium">#</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium">Date</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium">Session</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium">Side</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">Qty</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">Entry</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">Stop</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">Risk (pts)</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium">Exit</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">P&L</th>
                <th className="whitespace-nowrap px-4 py-2 font-medium text-right">R</th>
              </tr>
            </thead>
            <tbody>
              {filled.map((t, i) => {
                const isWin = t.pnl_usd > 0;
                const isLoss = t.pnl_usd < 0;
                const pnlColor = isWin
                  ? "var(--color-profit)"
                  : isLoss
                    ? "var(--color-loss)"
                    : "var(--color-text-muted)";

                return (
                  <tr
                    key={i}
                    className="border-b border-border/50 transition-colors hover:bg-bg-card-hover"
                  >
                    <td className="whitespace-nowrap px-4 py-1.5 font-mono text-text-muted">
                      {i + 1}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-text-primary">{t.date}</td>
                    <td className="whitespace-nowrap px-4 py-1.5">
                      <span className="rounded bg-bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                        {t.session}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5">
                      <span
                        className="font-medium"
                        style={{
                          color:
                            t.direction === "long"
                              ? "var(--color-profit)"
                              : "var(--color-loss)",
                        }}
                      >
                        {t.direction === "long" ? "LONG" : "SHORT"}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-primary">
                      {t.qty}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-primary">
                      {t.entry_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-muted">
                      {t.stop_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-muted">
                      {t.risk_points.toFixed(2)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-text-secondary">
                      {EXIT_LABELS[t.exit_type] ?? t.exit_type}
                    </td>
                    <td
                      className="whitespace-nowrap px-4 py-1.5 text-right font-mono font-semibold"
                      style={{ color: pnlColor }}
                    >
                      {formatCurrency(t.pnl_usd)}
                    </td>
                    <td
                      className="whitespace-nowrap px-4 py-1.5 text-right font-mono"
                      style={{ color: pnlColor }}
                    >
                      {formatR(t.pnl_usd / riskUsd)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ScrollArea>
    </div>
  );
}
