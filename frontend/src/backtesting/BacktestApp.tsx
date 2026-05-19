import { lazy, Suspense, useState } from "react";
import { BacktestingTabSkeleton } from "@/shared/ui/page-skeletons";

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

const BacktestDashboard = lazy(() =>
  import("@/backtesting/components/BacktestDashboard").then((module) => ({ default: module.BacktestDashboard })),
);
const SavedStrategiesDashboard = lazy(() =>
  import("@/backtesting/components/SavedStrategiesDashboard").then((module) => ({ default: module.SavedStrategiesDashboard })),
);
const ConfigsDashboard = lazy(() =>
  import("@/backtesting/components/ConfigsDashboard").then((module) => ({ default: module.ConfigsDashboard })),
);
const OptimizeDashboard = lazy(() =>
  import("@/backtesting/components/OptimizeDashboard").then((module) => ({ default: module.OptimizeDashboard })),
);
const CoverageDashboard = lazy(() =>
  import("@/backtesting/components/CoverageDashboard").then((module) => ({ default: module.CoverageDashboard })),
);
const RiskEngineDashboard = lazy(() =>
  import("@/backtesting/components/RiskEngineDashboard").then((module) => ({ default: module.RiskEngineDashboard })),
);
const RegimeDashboard = lazy(() =>
  import("@/backtesting/components/RegimeDashboard").then((module) => ({ default: module.RegimeDashboard })),
);
const NewsDashboard = lazy(() =>
  import("@/backtesting/components/NewsDashboard").then((module) => ({ default: module.NewsDashboard })),
);

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

      <Suspense fallback={<BacktestingTabSkeleton tab={activeTab} />}>
        {activeTab === "backtests" && <BacktestDashboard />}
        {activeTab === "saved" && <SavedStrategiesDashboard />}
        {activeTab === "configs" && <ConfigsDashboard />}
        {activeTab === "optimizations" && <OptimizeDashboard />}
        {activeTab === "coverage" && <CoverageDashboard />}
        {activeTab === "risk-engine" && <RiskEngineDashboard />}
        {activeTab === "regime" && <RegimeDashboard />}
        {activeTab === "news" && <NewsDashboard />}
      </Suspense>
    </>
  );
}
