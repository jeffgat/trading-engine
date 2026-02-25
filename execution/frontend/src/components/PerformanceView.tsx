import type { ConfigResponse, TradeLogEntry } from "@/lib/types";

interface PerformanceViewProps {
  entries: TradeLogEntry[];
  loading: boolean;
  config: ConfigResponse | null;
}

interface SessionCfg {
  rr?: number;
  tp1_ratio?: number;
}

interface OpenTrade {
  id: string;
  session: string;
  ticker: string;
  direction: "Long" | "Short";
  entryTs: string;
}

interface PerfRow {
  id: string;
  entryDate: string;
  entryTime: string;
  exitDate: string;
  exitTime: string;
  ticker: string;
  session: string;
  direction: "Long" | "Short";
  rValue: number | null;
  strategy: string;
  notes: string;
  sortTs: string;
}

const EXIT_EVENTS = new Set(["SL_HIT", "BE_HIT", "TP2_HIT", "TP2_DIRECT", "EOD_FLAT"]);

function splitTs(ts: string): { date: string; time: string } {
  const [date = "—", time = "—"] = ts.split(" ");
  return { date, time };
}

function tickerFromEntry(entry: TradeLogEntry): string {
  const raw = (entry.asset || entry.session.split("_")[0] || "").toUpperCase();
  if (raw.includes("NQ")) return "NQ";
  if (raw.includes("ES")) return "ES";
  if (raw.includes("GC")) return "GC";
  return "—";
}

function sessionLabel(session: string): string {
  const parts = session.split("_");
  return parts[1] ?? session;
}

function getRValue(
  event: string,
  cfg: SessionCfg | undefined,
): number | null {
  const rr = cfg?.rr;
  const tp1 = cfg?.tp1_ratio;

  if (event === "SL_HIT") return -1;
  if (event === "BE_HIT") {
    if (rr == null || tp1 == null) return 0;
    return 0.5 * rr * tp1;
  }
  if (event === "TP2_DIRECT") {
    if (rr == null) return null;
    return rr;
  }
  if (event === "TP2_HIT") {
    if (rr == null || tp1 == null) return null;
    return 0.5 * rr * (1 + tp1);
  }
  return null;
}

function buildRows(entries: TradeLogEntry[], config: ConfigResponse | null): PerfRow[] {
  const ordered = [...entries].reverse();
  const openBySession = new Map<string, OpenTrade>();
  const rows: PerfRow[] = [];

  for (const entry of ordered) {
    if (entry.event === "FILLED") {
      const dirRaw = (entry.details.dir || "").toLowerCase();
      const direction = dirRaw === "short" ? "Short" : "Long";
      openBySession.set(entry.session, {
        id: `${entry.session}-${entry.timestamp}`,
        session: entry.session,
        ticker: tickerFromEntry(entry),
        direction,
        entryTs: entry.timestamp,
      });
      continue;
    }

    if (!EXIT_EVENTS.has(entry.event)) continue;

    const open = openBySession.get(entry.session);
    if (!open) continue;

    const entryParts = splitTs(open.entryTs);
    const exitParts = splitTs(entry.timestamp);
    const sessionCfg = (config?.sessions?.[open.session] ?? {}) as SessionCfg;
    const rValue = getRValue(entry.event, sessionCfg);

    rows.push({
      id: `${open.id}-${entry.event}-${entry.timestamp}`,
      entryDate: entryParts.date,
      entryTime: entryParts.time,
      exitDate: exitParts.date,
      exitTime: exitParts.time,
      ticker: open.ticker,
      session: sessionLabel(open.session),
      direction: open.direction,
      rValue,
      strategy: "ORB",
      notes: "",
      sortTs: entry.timestamp,
    });
    openBySession.delete(entry.session);
  }

  for (const open of openBySession.values()) {
    const entryParts = splitTs(open.entryTs);
    rows.push({
      id: `${open.id}-open`,
      entryDate: entryParts.date,
      entryTime: entryParts.time,
      exitDate: "—",
      exitTime: "open",
      ticker: open.ticker,
      session: sessionLabel(open.session),
      direction: open.direction,
      rValue: null,
      strategy: "ORB",
      notes: "active",
      sortTs: open.entryTs,
    });
  }

  rows.sort((a, b) => b.sortTs.localeCompare(a.sortTs));
  return rows;
}

function Pill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "long" | "short" | "rpos" | "rneg" | "ticker-nq" | "ticker-es" | "ticker-gc";
}) {
  const toneClass =
    tone === "ticker-nq"
      ? "bg-info/20 text-info border-info/30"
      : tone === "ticker-es"
        ? "bg-loss/20 text-loss border-loss/30"
        : tone === "ticker-gc"
          ? "bg-warning/20 text-warning border-warning/30"
          : tone === "long"
      ? "bg-profit/20 text-profit border-profit/30"
      : tone === "short"
        ? "bg-loss/20 text-loss border-loss/30"
        : tone === "rpos"
          ? "bg-profit/15 text-profit border-profit/30"
          : tone === "rneg"
            ? "bg-loss/15 text-loss border-loss/30"
            : "bg-[#26262d] text-text-secondary border-border";

  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs ${toneClass}`}>
      {label}
    </span>
  );
}

export function PerformanceView({ entries, loading, config }: PerformanceViewProps) {
  const rows = buildRows(entries, config);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading performance...
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-sm text-text-muted">
        {rows.length} closed/open trades
      </div>

      <div className="overflow-x-auto rounded-md border border-border bg-bg-card">
        <table className="min-w-[1060px] w-full border-collapse text-sm">
          <thead className="bg-[#24242b] text-text-primary">
            <tr className="text-left">
              <th className="px-3 py-2 border-r border-border/80">Entry Date</th>
              <th className="px-3 py-2 border-r border-border/80">Entry Time</th>
              <th className="px-3 py-2 border-r border-border/80">Exit Date</th>
              <th className="px-3 py-2 border-r border-border/80">Exit Time</th>
              <th className="px-3 py-2 border-r border-border/80">Ticker</th>
              <th className="px-3 py-2 border-r border-border/80">Session</th>
              <th className="px-3 py-2 border-r border-border/80">Direction</th>
              <th className="px-3 py-2 border-r border-border/80">R</th>
              <th className="px-3 py-2 border-r border-border/80">Strategy</th>
              <th className="px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-text-muted">
                  No completed trades yet
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const rTone =
                  row.rValue == null
                    ? "neutral"
                    : row.rValue >= 0
                      ? "rpos"
                      : "rneg";

                const tickerTone =
                  row.ticker === "NQ"
                    ? "ticker-nq"
                    : row.ticker === "ES"
                      ? "ticker-es"
                      : row.ticker === "GC"
                        ? "ticker-gc"
                        : "neutral";

                return (
                  <tr key={row.id} className="border-t border-border/60 hover:bg-bg-card-hover/70">
                    <td className="px-3 py-2 font-medium text-text-secondary">{row.entryDate}</td>
                    <td className="px-3 py-2 font-mono text-text-secondary">{row.entryTime}</td>
                    <td className="px-3 py-2 font-medium text-text-secondary">{row.exitDate}</td>
                    <td className="px-3 py-2 font-mono text-text-secondary">{row.exitTime}</td>
                    <td className="px-3 py-2"><Pill label={row.ticker} tone={tickerTone} /></td>
                    <td className="px-3 py-2"><Pill label={row.session} /></td>
                    <td className="px-3 py-2">
                      <Pill label={row.direction} tone={row.direction === "Long" ? "long" : "short"} />
                    </td>
                    <td className="px-3 py-2">
                      {row.rValue == null ? (
                        <span className="text-text-muted">—</span>
                      ) : (
                        <Pill label={row.rValue.toFixed(1)} tone={rTone} />
                      )}
                    </td>
                    <td className="px-3 py-2"><Pill label={row.strategy} /></td>
                    <td className="px-3 py-2 text-text-muted">{row.notes || "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
