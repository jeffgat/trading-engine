import { useState } from "react";
import { Dashboard } from "./components/Dashboard";
import { OptimizeDashboard } from "./components/OptimizeDashboard";

type Tab = "backtests" | "optimizations";

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("backtests");

  return (
    <div>
      {/* Tab bar */}
      <div className="border-b border-border bg-bg-secondary">
        <div className="mx-auto flex max-w-7xl gap-0 px-4 sm:px-6 lg:px-8">
          {(["backtests", "optimizations"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`relative px-5 py-3 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "text-text-primary"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {tab === "backtests" ? "Backtests" : "Optimizations"}
              {activeTab === tab && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "backtests" ? <Dashboard /> : <OptimizeDashboard />}
    </div>
  );
}

export default App;
