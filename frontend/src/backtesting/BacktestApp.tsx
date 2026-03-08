import { useState } from "react";
import { BacktestDashboard } from "@/backtesting/components/BacktestDashboard";
import { CoverageDashboard } from "@/backtesting/components/CoverageDashboard";
import { OptimizeDashboard } from "@/backtesting/components/OptimizeDashboard";
import { RiskEngineDashboard } from "@/backtesting/components/RiskEngineDashboard";
import { SavedStrategiesDashboard } from "@/backtesting/components/SavedStrategiesDashboard";
import { NewsDashboard } from "@/backtesting/components/NewsDashboard";
import { RegimeDashboard } from "@/backtesting/components/RegimeDashboard";

type Tab = "backtests" | "saved" | "optimizations" | "coverage" | "risk-engine" | "regime" | "news";

const TAB_LABELS: Record<Tab, string> = {
  backtests: "Backtests",
  saved: "Saved",
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
      <div className="border-b border-border bg-bg-secondary">
        <div className="mx-auto flex max-w-7xl gap-1 px-4 sm:px-6 lg:px-8">
          {(["backtests", "saved", "optimizations", "coverage", "risk-engine", "regime", "news"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab
                  ? "border-accent text-text-primary"
                  : "border-transparent text-text-muted hover:text-text-secondary hover:border-border"
              }`}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "backtests" && <BacktestDashboard />}
      {activeTab === "saved" && <SavedStrategiesDashboard />}
      {activeTab === "optimizations" && <OptimizeDashboard />}
      {activeTab === "coverage" && <CoverageDashboard />}
      {activeTab === "risk-engine" && <RiskEngineDashboard />}
      {activeTab === "regime" && <RegimeDashboard />}
      {activeTab === "news" && <NewsDashboard />}
    </>
  );
}
