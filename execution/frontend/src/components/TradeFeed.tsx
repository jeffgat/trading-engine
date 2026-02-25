import { ScrollArea } from "@/components/ui/scroll-area";
import { TradeEventRow } from "./TradeEventRow";
import type { TradeLogEntry } from "@/lib/types";

interface TradeFeedProps {
  entries: TradeLogEntry[];
  total: number;
  loading: boolean;
  loadMore: () => void;
}

export function TradeFeed({
  entries,
  total,
  loading,
  loadMore,
}: TradeFeedProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading trade events...
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        No trade events yet
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-sm text-text-muted">
        {entries.length} of {total} events
      </div>
      <ScrollArea className="h-[calc(100vh-220px)] rounded-md border border-border bg-bg-card">
        <div>
          {entries.map((entry, i) => (
            <TradeEventRow key={`${entry.timestamp}-${i}`} entry={entry} />
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
    </div>
  );
}
