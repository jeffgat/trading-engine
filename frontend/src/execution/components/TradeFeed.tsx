import { useMemo, useState } from "react";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { ExecutionTabSkeleton } from "@/shared/ui/page-skeletons";
import { TradeEventRow } from "./TradeEventRow";
import { ExecTradeChartModal } from "./ExecTradeChartModal";
import type { ConfigResponse, TradeLogEntry, ExecTradeContext } from "@/execution/lib/types";
import { CHARTABLE_EVENTS, resolveTradeContext } from "@/execution/lib/utils";

interface TradeFeedProps {
  entries: TradeLogEntry[];
  total: number;
  loading: boolean;
  loadMore: () => void;
  activeConfig: string;
  config: ConfigResponse | null;
}

function buildStrategyLookup(config: ConfigResponse | null): Record<string, "continuation" | "lsi"> {
  const map: Record<string, "continuation" | "lsi"> = {};
  if (!config?.sessions) return map;
  for (const [key, cfg] of Object.entries(config.sessions)) {
    const short = key.includes(":") ? key.split(":")[1] : key;
    map[short] = cfg.type === "continuation" ? "continuation" : "lsi";
  }
  return map;
}

export function TradeFeed({
  entries,
  total,
  loading,
  loadMore,
  config,
}: TradeFeedProps) {
  const stratLookup = buildStrategyLookup(config);

  const [selectedConfig, setSelectedConfig] = useState("ALL");

  const configNames = useMemo(() => {
    const names = new Set<string>();
    for (const e of entries) {
      if (e.config) names.add(e.config);
    }
    return Array.from(names).sort();
  }, [entries]);

  const filtered = useMemo(() => {
    if (selectedConfig === "ALL") return entries;
    return entries.filter((e) => e.config === selectedConfig);
  }, [entries, selectedConfig]);

  const [chartContext, setChartContext] = useState<ExecTradeContext | null>(null);
  const [chartOpen, setChartOpen] = useState(false);

  const handleRowClick = (entry: TradeLogEntry, index: number) => {
    const ctx = resolveTradeContext(entry, entries, index);
    if (ctx) {
      setChartContext(ctx);
      setChartOpen(true);
    }
  };

  if (loading) {
    return <ExecutionTabSkeleton tab="trades" />;
  }

  if (filtered.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        No trade events yet
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-sm text-text-muted">
          {filtered.length} of {total} events
        </div>
        <Select value={selectedConfig} onValueChange={setSelectedConfig}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Configs</SelectItem>
            {configNames.map((name) => (
              <SelectItem key={name} value={name}>{name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <ScrollArea className="h-[calc(100vh-220px)] rounded-md border border-border bg-bg-card">
        <div>
          {filtered.map((entry, i) => (
            <TradeEventRow
              key={`${entry.timestamp}-${i}`}
              entry={entry}
              strategyType={stratLookup[entry.session]}
              clickable={CHARTABLE_EVENTS.has(entry.event)}
              onClick={() => handleRowClick(entry, i)}
            />
          ))}
          {entries.length < total && (
            <button
              onClick={loadMore}
              className="w-full py-2 text-sm text-text-muted hover:text-text-secondary transition-colors"
            >
              Load older events...
            </button>
          )}
        </div>
      </ScrollArea>
      <ExecTradeChartModal
        tradeContext={chartContext}
        open={chartOpen}
        onOpenChange={setChartOpen}
      />
    </div>
  );
}
