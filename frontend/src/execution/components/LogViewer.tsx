import { useMemo, useState } from "react";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { Input } from "@/shared/ui/input";
import { LOG_LEVEL_COLORS } from "@/execution/lib/constants";
import type { MainLogEntry, TradeLogEntry } from "@/execution/lib/types";

interface LogViewerProps {
  mainEntries: MainLogEntry[];
  mainTotal: number;
  mainLoading: boolean;
  loadMoreMain: () => void;
  tradeEntries: TradeLogEntry[];
  tradeTotal: number;
  tradeLoading: boolean;
  loadMoreTrade: () => void;
}

export function LogViewer({
  mainEntries,
  mainTotal,
  mainLoading,
  loadMoreMain,
  tradeEntries,
  tradeTotal,
  tradeLoading,
  loadMoreTrade,
}: LogViewerProps) {
  const [tab, setTab] = useState<"main" | "trade">("main");
  const [search, setSearch] = useState("");
  const [levelFilter, setLevelFilter] = useState("ALL");

  const filteredMain = useMemo(() => {
    let result = mainEntries;
    if (levelFilter !== "ALL") {
      const levels: Record<string, number> = {
        DEBUG: 0,
        INFO: 1,
        WARNING: 2,
        WARN: 2,
        ERROR: 3,
      };
      const min = levels[levelFilter] ?? 0;
      result = result.filter(
        (e) => (levels[e.level.toUpperCase().trim()] ?? 0) >= min,
      );
    }
    if (search) {
      const s = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.message.toLowerCase().includes(s) ||
          e.logger.toLowerCase().includes(s),
      );
    }
    return result;
  }, [mainEntries, levelFilter, search]);

  const filteredTrade = useMemo(() => {
    if (!search) return tradeEntries;
    const s = search.toLowerCase();
    return tradeEntries.filter(
      (e) =>
        e.event.toLowerCase().includes(s) ||
        e.session.toLowerCase().includes(s) ||
        JSON.stringify(e.details).toLowerCase().includes(s),
    );
  }, [tradeEntries, search]);

  const isMain = tab === "main";
  const loading = isMain ? mainLoading : tradeLoading;

  return (
    <div className="space-y-3">
      {/* Controls */}
      <div className="flex items-center gap-3">
        {/* Tab toggle */}
        <div className="flex rounded-md border border-border bg-bg-secondary">
          <button
            onClick={() => setTab("main")}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              isMain
                ? "bg-bg-card-hover text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            Main Log
          </button>
          <button
            onClick={() => setTab("trade")}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              !isMain
                ? "bg-bg-card-hover text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            Trade Log
          </button>
        </div>

        {/* Search */}
        <Input
          placeholder="Search logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 max-w-xs bg-bg-secondary border-border text-sm"
        />

        {/* Level filter (main log only) */}
        {isMain && (
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="h-8 rounded-md border border-border bg-bg-secondary px-2 text-xs text-text-secondary"
          >
            <option value="ALL">All Levels</option>
            <option value="DEBUG">DEBUG+</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARNING+</option>
            <option value="ERROR">ERROR</option>
          </select>
        )}

        <span className="text-xs text-text-muted ml-auto">
          {isMain
            ? `${filteredMain.length} of ${mainTotal}`
            : `${filteredTrade.length} of ${tradeTotal}`}
        </span>
      </div>

      {/* Log content */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-text-muted">
          Loading logs...
        </div>
      ) : (
        <ScrollArea className="h-[calc(100vh-240px)] rounded-md border border-border bg-bg-card">
          <div className="font-mono text-xs leading-relaxed">
            {isMain ? (
              <>
                {filteredMain.map((entry, i) => (
                  <div
                    key={`${entry.timestamp}-${i}`}
                    className="flex gap-2 border-b border-border/20 px-3 py-1 hover:bg-bg-card-hover"
                  >
                    <span className="text-text-muted whitespace-nowrap">
                      {entry.timestamp.split(" ")[1] ?? entry.timestamp}
                    </span>
                    <span
                      className={`w-12 text-right ${LOG_LEVEL_COLORS[entry.level.trim()] ?? "text-text-secondary"}`}
                    >
                      {entry.level.trim()}
                    </span>
                    <span className="text-text-muted truncate max-w-32">
                      {entry.logger}
                    </span>
                    <span className="text-text-secondary flex-1">
                      {entry.message}
                    </span>
                  </div>
                ))}
                {filteredMain.length < mainTotal && (
                  <button
                    onClick={loadMoreMain}
                    className="w-full py-2 text-text-muted hover:text-text-secondary transition-colors"
                  >
                    Load older logs...
                  </button>
                )}
              </>
            ) : (
              <>
                {filteredTrade.map((entry, i) => (
                  <div
                    key={`${entry.timestamp}-${i}`}
                    className="flex gap-2 border-b border-border/20 px-3 py-1 hover:bg-bg-card-hover"
                  >
                    <span className="text-text-muted whitespace-nowrap">
                      {entry.timestamp.split(" ")[1] ?? entry.timestamp}
                    </span>
                    <span className="text-info w-10">{entry.session}</span>
                    <span className="text-text-primary font-medium w-24">
                      {entry.event}
                    </span>
                    <span className="text-text-secondary flex-1">
                      {Object.entries(entry.details)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(" ")}
                    </span>
                  </div>
                ))}
                {filteredTrade.length < tradeTotal && (
                  <button
                    onClick={loadMoreTrade}
                    className="w-full py-2 text-text-muted hover:text-text-secondary transition-colors"
                  >
                    Load older logs...
                  </button>
                )}
              </>
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
