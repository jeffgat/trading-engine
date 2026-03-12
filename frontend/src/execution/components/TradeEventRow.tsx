import { Badge } from "@/shared/ui/badge";
import { EVENT_COLORS, CONFIG_COLORS } from "@/execution/lib/constants";
import { SessionTag } from "./SessionTag";
import type { TradeLogEntry } from "@/execution/lib/types";

interface TradeEventRowProps {
  entry: TradeLogEntry;
  strategyType?: "continuation" | "lsi";
  onClick?: () => void;
  clickable?: boolean;
}

export function TradeEventRow({ entry, strategyType, onClick, clickable }: TradeEventRowProps) {
  const isLsi = strategyType === "lsi";
  const eventColor =
    EVENT_COLORS[entry.event] ?? "bg-text-muted/20 text-text-muted";
  const [datePart, timePart] = entry.timestamp.split(" ");
  const eventTime = entry.details.tick_time ?? entry.details.bar_time;
  const resolution = entry.details.resolution;

  const detailParts = Object.entries(entry.details).filter(
    ([key]) => key !== "bar_time" && key !== "tick_time" && key !== "resolution",
  );

  return (
    <div
      className={`flex items-start gap-3 border-b border-border/30 px-3 py-2 hover:bg-bg-card-hover transition-colors group ${
        clickable ? "cursor-pointer" : ""
      }`}
      onClick={clickable ? onClick : undefined}
    >
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

      {resolution && (
        <span className="rounded bg-text-muted/10 px-1.5 py-0.5 font-mono text-[10px] text-text-muted whitespace-nowrap">
          {resolution}
        </span>
      )}

      {eventTime && (
        <span className="text-xs whitespace-nowrap">
          <span className="text-text-muted">
            {entry.details.tick_time ? "tick_time=" : "bar_time="}
          </span>
          <span className="font-mono text-text-secondary">{eventTime}</span>
        </span>
      )}

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

      {/* Chart icon on hover for clickable rows */}
      {clickable && (
        <span className="ml-auto opacity-0 group-hover:opacity-60 transition-opacity pt-0.5">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-text-muted"
          >
            <path d="M3 3v18h18" />
            <path d="M7 16l4-8 4 4 4-6" />
          </svg>
        </span>
      )}
    </div>
  );
}
