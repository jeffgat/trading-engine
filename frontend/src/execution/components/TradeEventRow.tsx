import { Badge } from "@/shared/ui/badge";
import { EVENT_COLORS, CONFIG_COLORS } from "@/execution/lib/constants";
import { SessionTag } from "./SessionTag";
import type { TradeLogEntry } from "@/execution/lib/types";

interface TradeEventRowProps {
  entry: TradeLogEntry;
  strategyType?: "continuation" | "lsi";
}

export function TradeEventRow({ entry, strategyType }: TradeEventRowProps) {
  const isLsi = strategyType === "lsi";
  const eventColor =
    EVENT_COLORS[entry.event] ?? "bg-text-muted/20 text-text-muted";
  const [datePart, timePart] = entry.timestamp.split(" ");

  const detailParts = Object.entries(entry.details).filter(
    ([key]) => key !== "bar_time" && key !== "tick_time" && key !== "resolution",
  );

  return (
    <div className="flex items-start gap-3 border-b border-border/30 px-3 py-2 hover:bg-bg-card-hover transition-colors">
      {/* Timestamp */}
      <span className="font-mono text-xs text-text-muted whitespace-nowrap pt-0.5">
        {timePart && datePart ? `${datePart} ${timePart}` : entry.timestamp}
      </span>

      {/* Config badge */}
      {entry.config && (
        <span
          className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
            CONFIG_COLORS[entry.config] ?? "bg-text-muted/20 text-text-muted border-text-muted/30"
          }`}
        >
          {entry.config}
        </span>
      )}

      {/* asset */}
      {entry.asset && <SessionTag session={entry.asset.toUpperCase()} />}

      {/* Session */}
      <SessionTag session={entry.session} />

      {/* Strategy type */}
      {strategyType && (
        <span
          className={`text-[10px] font-medium px-1.5 py-0.5 rounded whitespace-nowrap ${
            isLsi
              ? "text-violet-400 bg-violet-400/10"
              : "text-emerald-400 bg-emerald-400/10"
          }`}
        >
          {isLsi ? "LSI" : "ORB"}
        </span>
      )}

      {/* Event badge */}
      <Badge variant="outline" className={`border-0 text-xs ${eventColor}`}>
        {entry.event}
      </Badge>

      {/* Details */}
      {detailParts.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {detailParts.map(([key, value]) => (
            <span key={key} className="text-xs">
              <span className="text-text-muted">{key}=</span>
              <span className="font-mono text-text-secondary">{value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
