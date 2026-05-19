import { useState } from "react";
import { BacktestDashboard } from "@/backtesting/components/BacktestDashboard";
import { CoverageDashboard } from "@/backtesting/components/CoverageDashboard";
import { ConfigsDashboard } from "@/backtesting/components/ConfigsDashboard";
import { OptimizeDashboard } from "@/backtesting/components/OptimizeDashboard";
import { RiskEngineDashboard } from "@/backtesting/components/RiskEngineDashboard";
import { SavedStrategiesDashboard } from "@/backtesting/components/SavedStrategiesDashboard";
import { NewsDashboard } from "@/backtesting/components/NewsDashboard";
import { RegimeDashboard } from "@/backtesting/components/RegimeDashboard";

type Tab = "backtests" | "saved" | "configs" | "optimizations" | "coverage" | "risk-engine" | "regime" | "news";

const TAB_LABELS: Record<Tab, string> = {
  backtests: "Backtests",
  saved: "Saved",
  configs: "Configs",
  optimizations: "Optimizations",
  coverage: "Coverage",
  "risk-engine": "Risk Engine",
  regime: "Regime",
  news: "News",
};

export function BacktestApp() {
  const [activeTab, setActiveTab] = useState<Tab>("backtests");

  return (
    <>
      {/* Tab bar */}
      <div className="border-b border-border bg-bg-secondary/60 px-4 py-2 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto rounded-lg border border-border bg-bg-primary/70 p-1">
          {(["backtests", "saved", "configs", "optimizations", "coverage", "risk-engine", "regime", "news"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`min-h-9 shrink-0 rounded-md px-4 font-mono text-sm font-semibold lowercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-profit/40 ${
                activeTab === tab
                  ? "bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]"
                  : "text-text-secondary hover:bg-bg-card-hover hover:text-foreground"
              }`}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "backtests" && <BacktestDashboard />}
      {activeTab === "saved" && <SavedStrategiesDashboard />}
      {activeTab === "configs" && <ConfigsDashboard />}
      {activeTab === "optimizations" && <OptimizeDashboard />}
      {activeTab === "coverage" && <CoverageDashboard />}
      {activeTab === "risk-engine" && <RiskEngineDashboard />}
      {activeTab === "regime" && <RegimeDashboard />}
      {activeTab === "news" && <NewsDashboard />}
    </>
  );
}
