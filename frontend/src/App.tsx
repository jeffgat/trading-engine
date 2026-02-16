import { useState } from "react";
import { BacktestDashboard } from "./components/BacktestDashboard";
import { CoverageDashboard } from "./components/CoverageDashboard";
import { OptimizeDashboard } from "./components/OptimizeDashboard";
import { SavedStrategiesDashboard } from "./components/SavedStrategiesDashboard";

type Tab = "backtests" | "saved" | "optimizations" | "coverage";

const TAB_LABELS: Record<Tab, string> = {
  backtests: "Backtests",
  saved: "Saved",
  optimizations: "Optimizations",
  coverage: "Coverage",
};

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("backtests");

  return (
    <div>
      {/* Tab bar */}
      <div className="border-b border-border bg-bg-secondary">
        <div className="mx-auto flex max-w-7xl gap-0 px-4 sm:px-6 lg:px-8">
          {(["backtests", "saved", "optimizations", "coverage"] as const).map((tab) => (
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
    </div>
  );
}

export default App;
