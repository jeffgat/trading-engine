import { BacktestApp } from "@/backtesting/BacktestApp";
import { ExecutionApp } from "@/execution/ExecutionApp";
import { useState } from "react";

type Section = "backtesting" | "execution";

function App() {
  const [section, setSection] = useState<Section>("backtesting");

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* Top-level section nav */}
      <nav className="border-b border-border bg-bg-secondary">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-6">
            <span className="text-lg font-semibold tracking-tight text-text-primary">
              Gat Capital
            </span>
            <div className="flex gap-1">
              {(["backtesting", "execution"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSection(s)}
                  className={`px-4 py-3 text-sm font-medium capitalize transition-colors border-b-2 ${
                    section === s
                      ? "border-accent text-text-primary"
                      : "border-transparent text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {s === "backtesting" ? "Backtesting" : "Execution"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </nav>

      {/* Section content */}
      {section === "backtesting" && <BacktestApp />}
      {section === "execution" && <ExecutionApp />}
    </div>
  );
}

export default App;
