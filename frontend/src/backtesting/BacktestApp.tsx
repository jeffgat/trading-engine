import { useState } from "react";
import { BacktestDashboard } from "@/backtesting/components/BacktestDashboard";
import { CoverageDashboard } from "@/backtesting/components/CoverageDashboard";
import { OptimizeDashboard } from "@/backtesting/components/OptimizeDashboard";
import { RiskEngineDashboard } from "@/backtesting/components/RiskEngineDashboard";
import { SavedStrategiesDashboard } from "@/backtesting/components/SavedStrategiesDashboard";

type Tab = "backtests" | "saved" | "optimizations" | "coverage" | "risk-engine";

const TAB_LABELS: Record<Tab, string> = {
  backtests: "Backtests",
  saved: "Saved",
  optimizations: "Optimizations",
  coverage: "Coverage",
  "risk-engine": "Risk Engine",
};

export function BacktestApp() {
  const [activeTab, setActiveTab] = useState<Tab>("backtests");

  return (
    <>
      {/* Tab bar */}
      <div className="border-b border-border bg-bg-secondary">
        <div className="mx-auto flex max-w-7xl gap-0 px-4 sm:px-6 lg:px-8">
          {(["backtests", "saved", "optimizations", "coverage", "risk-engine"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`relative px-5 py-3 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "text-text-primary"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {TAB_LABELS[tab]}
              {activeTab === tab && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "backtests" && <BacktestDashboard />}
      {activeTab === "saved" && <SavedStrategiesDashboard />}
      {activeTab === "optimizations" && <OptimizeDashboard />}
      {activeTab === "coverage" && <CoverageDashboard />}
      {activeTab === "risk-engine" && <RiskEngineDashboard />}
    </>
  );
}
