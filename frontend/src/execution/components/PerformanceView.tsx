import { useMemo, useState, useCallback } from "react";
import { CONFIG_COLORS } from "@/execution/lib/constants";
import type { ConfigResponse, TradeLogEntry, ComparisonCurvePoint } from "@/execution/lib/types";
import type { LiveTrade } from "@/execution/hooks/useLiveTrades";
import { useBacktestComparison } from "@/execution/hooks/useBacktestComparison";
import { EquityCurveComparison } from "@/execution/components/EquityCurveComparison";
import { BacktestWindowSlider } from "@/execution/components/BacktestWindowSlider";
import { DatePicker } from "@/shared/ui/date-picker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { ExecutionTabSkeleton } from "@/shared/ui/page-skeletons";

interface PerformanceViewProps {
  entries: TradeLogEntry[];
  loading: boolean;
  config: ConfigResponse | null;
  activeConfig: string;
  configNames: string[];
  setActiveConfig: (config: string) => void;
  dbTrades?: LiveTrade[];
  dbLoading?: boolean;
}

interface SessionCfg {
  rr?: number;
  tp1_ratio?: number;
  risk_usd?: number;
}

interface OpenTrade {
  id: string;
  session: string;
  config: string;
  leg: string;
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
  leg: string;
  ticker: string;
  session: string;
  config: string;
  direction: "Long" | "Short";
  rValue: number | null;
  usdValue: number | null;
  strategy: string;
  notes: string;
  sortTs: string;
}

const EXIT_EVENTS = new Set(["SL_HIT", "BE_HIT", "TP2_HIT", "TP2_DIRECT", "EOD_FLAT"]);
const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function splitTs(ts: string): { date: string; time: string } {
  if (!ts) return { date: "\u2014", time: "\u2014" };
  const cleaned = ts
    .replace("T", " ")
    .replace(/([+-]\d{2}:\d{2}|Z)$/, "")
    .trim();
  const [date = "\u2014", time = "\u2014"] = cleaned.split(" ");
  return { date, time };
}

function normalizeTicker(raw: string | null | undefined): string {
  const value = (raw ?? "").toUpperCase();
  if (value.includes("NQ")) return "NQ";
  if (value.includes("ES")) return "ES";
  if (value.includes("GC")) return "GC";
  return value || "\u2014";
}

function tickerFromEntry(entry: TradeLogEntry): string {
  return normalizeTicker(entry.asset || entry.session.split("_")[0]);
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
    if (rr == null || tp1 == null) return null;
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

function getUsdValue(rValue: number | null, cfg: SessionCfg | undefined): number | null {
  if (rValue == null) return null;
  const riskUsd = cfg?.risk_usd;
  if (riskUsd == null) return null;
  return rValue * riskUsd;
}

/** Build lookups by both "CONFIG:session" compound key and short session name.
 *  Compound key ensures FAST and SLOW configs with the same session resolve
 *  to their own risk_usd. Short key is a fallback (first match wins).
 *  Normalizes "ifvg" → "lsi" for display. */
function buildSessionLookups(config: ConfigResponse | null) {
  const cfgByKey: Record<string, SessionCfg> = {};
  const cfgByShort: Record<string, SessionCfg> = {};
  const typeByShort: Record<string, "continuation" | "lsi"> = {};
  const tickerByKey: Record<string, string> = {};
  const tickerByShort: Record<string, string> = {};
  if (config?.sessions) {
    for (const [key, cfg] of Object.entries(config.sessions)) {
      const configName = key.includes(":") ? key.split(":")[0] : "";
      const short = key.includes(":") ? key.split(":")[1] : key;
      const sessionCfg = cfg as SessionCfg & { signal_ticker?: string; exec_ticker?: string };
      const ticker = normalizeTicker(sessionCfg.signal_ticker || sessionCfg.exec_ticker || short.split("_")[0]);
      if (configName) {
        cfgByKey[`${configName}:${short}`] = sessionCfg;
        tickerByKey[`${configName}:${short}`] = ticker;
      }
      if (!cfgByShort[short]) {
        cfgByShort[short] = sessionCfg;
        typeByShort[short] = cfg.type === "continuation" ? "continuation" : "lsi";
        tickerByShort[short] = ticker;
      }
    }
  }
  return { cfgByKey, cfgByShort, typeByShort, tickerByKey, tickerByShort };
}

function buildRows(entries: TradeLogEntry[], config: ConfigResponse | null): PerfRow[] {
  const { cfgByKey, cfgByShort, typeByShort, tickerByKey, tickerByShort } = buildSessionLookups(config);
  const ordered = [...entries].reverse();
  // Key open trades by config:session to handle multiple configs
  const openByKey = new Map<string, OpenTrade>();
  const rows: PerfRow[] = [];

  for (const entry of ordered) {
    const entryConfig = entry.config ?? "";
    const tradeKey = `${entryConfig}:${entry.session}`;

    if (entry.event === "FILLED") {
      const dirRaw = (entry.details.dir || "").toLowerCase();
      const direction = dirRaw === "short" ? "Short" : "Long";
      openByKey.set(tradeKey, {
        id: `${tradeKey}-${entry.timestamp}`,
        session: entry.session,
        config: entryConfig,
        leg: entry.session,
        ticker: tickerFromEntry(entry) !== "\u2014"
          ? tickerFromEntry(entry)
          : tickerByKey[tradeKey] ?? tickerByShort[entry.session] ?? "\u2014",
        direction,
        entryTs: entry.timestamp,
      });
      continue;
    }

    if (!EXIT_EVENTS.has(entry.event)) continue;

    const open = openByKey.get(tradeKey);
    if (!open) continue;

    const entryParts = splitTs(open.entryTs);
    const exitParts = splitTs(entry.timestamp);
    const sessionCfg = cfgByKey[`${open.config}:${open.session}`] ?? cfgByShort[open.session] ?? {};
    const rValue = getRValue(entry.event, sessionCfg);

    const stratType = typeByShort[open.session];
    rows.push({
      id: `${open.id}-${entry.event}-${entry.timestamp}`,
      entryDate: entryParts.date,
      entryTime: entryParts.time,
      exitDate: exitParts.date,
      exitTime: exitParts.time,
      leg: open.leg,
      ticker: open.ticker,
      session: sessionLabel(open.session),
      config: open.config,
      direction: open.direction,
      rValue,
      usdValue: getUsdValue(rValue, sessionCfg),
      strategy: stratType === "lsi" ? "LSI" : "ORB",
      notes: "",
      sortTs: entry.timestamp,
    });
    openByKey.delete(tradeKey);
  }

  for (const open of openByKey.values()) {
    const entryParts = splitTs(open.entryTs);
    const openStratType = typeByShort[open.session];
    rows.push({
      id: `${open.id}-open`,
      entryDate: entryParts.date,
      entryTime: entryParts.time,
      exitDate: "\u2014",
      exitTime: "open",
      leg: open.leg,
      ticker: open.ticker,
      session: sessionLabel(open.session),
      config: open.config,
      direction: open.direction,
      rValue: null,
      usdValue: null,
      strategy: openStratType === "lsi" ? "LSI" : "ORB",
      notes: "active",
      sortTs: open.entryTs,
    });
  }

  rows.sort((a, b) => b.sortTs.localeCompare(a.sortTs));
  return rows;
}

/** Map DB exit_type to the R-value logic used by the log-based approach. */
function getDbRValue(trade: LiveTrade, config: ConfigResponse | null): number | null {
  // If the DB has a pre-computed r_result, use it
  if (trade.r_result != null) return trade.r_result;

  // Otherwise compute from exit_type + config rr/tp1_ratio
  const sessionKey = trade.session; // e.g. "NQ_NY"

  // Find matching session config
  let rr: number | undefined;
  let tp1: number | undefined;
  if (config?.sessions) {
    // Try compound key first (CONFIG:session), then short key
    const compoundKey = `${trade.config_name}:${sessionKey}`;
    const cfg = (config.sessions[compoundKey] ?? config.sessions[sessionKey]) as SessionCfg | undefined;
    rr = cfg?.rr;
    tp1 = cfg?.tp1_ratio;
  }

  const et = trade.exit_type;

  if (et === "sl") return -1;
  if (et === "tp1_be" || et === "tp1_eod") {
    if (rr == null || tp1 == null) return null;
    return 0.5 * rr * tp1;
  }
  if (et === "tp1_single") {
    if (rr == null || tp1 == null) return null;
    return rr * tp1;
  }
  if (et === "tp2_direct") {
    if (rr == null) return null;
    return rr;
  }
  if (et === "tp2" || et === "tp1_tp2") {
    if (rr == null || tp1 == null) return null;
    return 0.5 * rr * (1 + tp1);
  }
  if (et === "eod") return 0;
  return null;
}

function tickerFromSession(session: string): string {
  return normalizeTicker(session.split("_")[0]);
}

function tradeDirectionLabel(direction: number): "Long" | "Short" {
  return direction === 1 ? "Long" : "Short";
}

function directionMatches(entry: TradeLogEntry, trade: LiveTrade): boolean {
  const dirRaw = (entry.details.dir || entry.details.direction || "").toLowerCase();
  if (!dirRaw) return true;
  return trade.direction === 1
    ? dirRaw === "long" || dirRaw === "1"
    : dirRaw === "short" || dirRaw === "-1";
}

function findEntryLogForTrade(trade: LiveTrade, entries: TradeLogEntry[]): TradeLogEntry | undefined {
  const leg = trade.leg || trade.session;
  const config = trade.config_name || "";
  const entryDate = trade.date.length === 8
    ? `${trade.date.slice(0, 4)}-${trade.date.slice(4, 6)}-${trade.date.slice(6, 8)}`
    : trade.date;
  const exitTs = splitTs(trade.exit_timestamp);
  const exitSortable = `${exitTs.date} ${exitTs.time}`;

  return entries
    .filter((entry) => {
      if (entry.session !== leg && entry.session !== trade.session) return false;
      if ((entry.config || "") !== config) return false;
      if (!entry.timestamp.startsWith(entryDate)) return false;
      if (entry.timestamp > exitSortable) return false;
      if (entry.event !== "FILLED" && entry.event !== "HUNTER_SETUP") return false;
      return directionMatches(entry, trade);
    })
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0];
}

function tickerFromConfig(
  config: ConfigResponse | null,
  configName: string,
  leg: string,
): string {
  const cfg = (config?.sessions?.[`${configName}:${leg}`] ?? config?.sessions?.[leg]) as
    | (SessionCfg & { signal_ticker?: string; exec_ticker?: string })
    | undefined;
  return normalizeTicker(cfg?.signal_ticker || cfg?.exec_ticker || leg.split("_")[0]);
}

function buildRowsFromDb(trades: LiveTrade[], config: ConfigResponse | null, entries: TradeLogEntry[]): PerfRow[] {
  return trades.map((t) => {
    const leg = t.leg || t.session;
    const entryLog = findEntryLogForTrade(t, entries);
    const entryTimestamp = t.entry_timestamp || entryLog?.timestamp || "";
    const entryParts = splitTs(entryTimestamp);
    const exitParts = splitTs(t.exit_timestamp);
    // Format YYYYMMDD → YYYY-MM-DD for entry date display
    const fallbackEntryDate = t.date.length === 8
      ? `${t.date.slice(0, 4)}-${t.date.slice(4, 6)}-${t.date.slice(6, 8)}`
      : t.date;
    const sessionParts = leg.split("_");
    const sessionLabel = sessionParts[1] ?? t.session;
    const stratType = leg.toLowerCase().includes("lsi") ? "LSI" : "ORB";
    const compoundKey = `${t.config_name}:${leg}`;
    const sessionCfg = (config?.sessions?.[compoundKey] ?? config?.sessions?.[leg] ?? config?.sessions?.[t.session]) as SessionCfg | undefined;
    const rValue = getDbRValue(t, config);
    const ticker = normalizeTicker(
      t.ticker
        || entryLog?.asset
        || tickerFromConfig(config, t.config_name, leg)
        || tickerFromSession(leg),
    );

    return {
      id: `db-${t.id}`,
      entryDate: entryParts.date === "\u2014" ? fallbackEntryDate : entryParts.date,
      entryTime: entryParts.time,
      exitDate: exitParts.date,
      exitTime: exitParts.time,
      leg,
      ticker,
      session: sessionLabel,
      config: t.config_name,
      direction: tradeDirectionLabel(t.direction),
      rValue,
      usdValue: getUsdValue(rValue, sessionCfg),
      strategy: stratType,
      notes: t.notes ?? "",
      sortTs: t.exit_timestamp,
    };
  }).sort((a, b) => b.sortTs.localeCompare(a.sortTs));
}

function formatUsdValue(value: number | null): string {
  if (value == null) return "\u2014";
  return USD_FORMATTER.format(value);
}

function Pill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "long" | "short" | "rpos" | "rneg" | "ticker-nq" | "ticker-es" | "ticker-gc" | "session-ny" | "session-ldn" | "session-asia" | "strat-orb" | "strat-lsi";
}) {
  const toneClasses: Record<string, string> = {
    "ticker-nq": "bg-info/20 text-info border-info/30",
    "ticker-es": "bg-loss/20 text-loss border-loss/30",
    "ticker-gc": "bg-warning/20 text-warning border-warning/30",
    long: "bg-profit/20 text-profit border-profit/30",
    short: "bg-loss/20 text-loss border-loss/30",
    rpos: "bg-profit/15 text-profit border-profit/30",
    rneg: "bg-loss/15 text-loss border-loss/30",
    "session-ny": "bg-info/15 text-info border-info/35",
    "session-ldn": "bg-profit/10 text-profit border-profit/30",
    "session-asia": "bg-gold-400/15 text-gold-300 border-gold-400/30",
    "strat-orb": "bg-profit/10 text-profit border-profit/30",
    "strat-lsi": "bg-info/10 text-info border-info/30",
    neutral: "bg-bg-tertiary text-text-secondary border-border",
  };
  const toneClass = toneClasses[tone] ?? toneClasses.neutral;

  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs ${toneClass}`}>
      {label}
    </span>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  allLabel,
  options,
  widthClass = "w-[140px]",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  allLabel: string;
  options: string[];
  widthClass?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-text-muted font-medium uppercase tracking-wide">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className={widthClass}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ALL">{allLabel}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/* ---------- Unique sorted values from rows ---------- */
function uniqueValues(rows: PerfRow[], key: keyof PerfRow): string[] {
  const set = new Set<string>();
  for (const row of rows) {
    const v = row[key];
    if (v != null && v !== "" && v !== "\u2014") set.add(String(v));
  }
  return [...set].sort();
}

/* ---------- Build live equity curve from closed trade rows ---------- */
function buildLiveEquityCurve(rows: PerfRow[]): { date: string; r_cumulative: number; r_per_trade: number }[] {
  const closed = rows
    .filter((r) => r.rValue != null)
    .sort((a, b) => a.sortTs.localeCompare(b.sortTs));
  let cum = 0;
  return closed.map((r) => {
    cum += r.rValue!;
    return { date: r.entryDate, r_cumulative: cum, r_per_trade: r.rValue! };
  });
}

/* ---------- Merge backtest + live curves into comparison data ---------- */
function mergeEquityCurves(
  backtestCurve: { date: string; r: number }[],
  liveCurve: { date: string; r_cumulative: number; r_per_trade: number }[],
  liveOffset: number,
): ComparisonCurvePoint[] {
  const map = new Map<string, ComparisonCurvePoint>();

  // Add backtest points
  for (const p of backtestCurve) {
    map.set(p.date, { date: p.date, backtest_r: p.r });
  }

  // Add live points as a continuation from the historical replay. Backtest R
  // and live R are both per-trade/per-leg R multiples, so this preserves the
  // same normalization while keeping the badge/card as raw realized live R.
  for (const p of liveCurve) {
    const existing = map.get(p.date) ?? { date: p.date };
    existing.live_r = liveOffset + p.r_cumulative;
    existing.live_r_per_trade = p.r_per_trade;
    existing._rawLiveR = p.r_cumulative;
    map.set(p.date, existing);
  }

  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function PerformanceView({ entries, loading, config, activeConfig, configNames, setActiveConfig, dbTrades, dbLoading }: PerformanceViewProps) {
  // Use DB trades when available, fall back to log-based rows
  const useDb = (dbTrades?.length ?? 0) > 0;
  const allRows = useMemo(() => {
    if (useDb && dbTrades) return buildRowsFromDb(dbTrades, config, entries);
    return buildRows(entries, config);
  }, [useDb, dbTrades, entries, config]);

  // Config-level filter (from the header pills)
  const configRows = useMemo(() => {
    if (activeConfig === "ALL") return allRows;
    return allRows.filter((row) => row.config === activeConfig);
  }, [allRows, activeConfig]);

  // Local filters
  const [legFilter, setLegFilter] = useState<string>("ALL");
  const [strategyFilter, setStrategyFilter] = useState<string>("ALL");
  const [sessionFilter, setSessionFilter] = useState<string>("ALL");
  const [tickerFilter, setTickerFilter] = useState<string>("ALL");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");

  // Derive unique options from configRows (so they respect the config pill)
  const legs = useMemo(() => uniqueValues(configRows, "leg"), [configRows]);
  const strategies = useMemo(() => uniqueValues(configRows, "strategy"), [configRows]);
  const sessions = useMemo(() => uniqueValues(configRows, "session"), [configRows]);
  const tickers = useMemo(() => uniqueValues(configRows, "ticker"), [configRows]);

  // Apply all filters
  const rows = useMemo(() => {
    let filtered = configRows;
    if (legFilter !== "ALL") filtered = filtered.filter((r) => r.leg === legFilter);
    if (strategyFilter !== "ALL") filtered = filtered.filter((r) => r.strategy === strategyFilter);
    if (sessionFilter !== "ALL") filtered = filtered.filter((r) => r.session === sessionFilter);
    if (tickerFilter !== "ALL") filtered = filtered.filter((r) => r.ticker === tickerFilter);
    if (dateFrom) filtered = filtered.filter((r) => r.entryDate >= dateFrom);
    if (dateTo) filtered = filtered.filter((r) => r.entryDate <= dateTo);
    return filtered;
  }, [configRows, legFilter, strategyFilter, sessionFilter, tickerFilter, dateFrom, dateTo]);

  // Summary stats (only closed trades with realized values)
  const { totalR, totalUsd, closedCount, winCount } = useMemo(() => {
    let r = 0;
    let usd = 0;
    let closed = 0;
    let wins = 0;
    for (const row of rows) {
      if (row.rValue != null) {
        r += row.rValue;
        closed++;
        if (row.rValue > 0) wins++;
      }
      if (row.usdValue != null) {
        usd += row.usdValue;
      }
    }
    return { totalR: r, totalUsd: usd, closedCount: closed, winCount: wins };
  }, [rows]);

  const winRate = closedCount > 0 ? (winCount / closedCount) * 100 : 0;

  // Backtest comparison
  const { mappings, setMapping, backtestCurves, loading: btLoading, errors: btErrors } = useBacktestComparison();

  // Determine which configs to show charts for
  const visibleConfigs = useMemo(() => {
    if (activeConfig !== "ALL") return [activeConfig];
    return Object.keys(CONFIG_COLORS);
  }, [activeConfig]);

  // Backtest window slider state
  const today = new Date().toISOString().slice(0, 10);
  const [btWindowStart, setBtWindowStart] = useState<string>("");
  const [btWindowEnd, setBtWindowEnd] = useState<string>("");

  // Derive the full date range of all loaded backtest curves
  const btOriginalBounds = useMemo(() => {
    let earliest = today;
    for (const cfg of visibleConfigs) {
      const curve = backtestCurves[cfg]?.curve;
      if (curve?.length && curve[0].date < earliest) earliest = curve[0].date;
    }
    return { start: earliest, end: today };
  }, [backtestCurves, visibleConfigs, today]);

  const effectiveBtStart = btWindowStart || btOriginalBounds.start;
  const effectiveBtEnd = btWindowEnd || btOriginalBounds.end;

  const handleBtWindowChange = useCallback((start: string, end: string) => {
    setBtWindowStart(start);
    setBtWindowEnd(end);
  }, []);

  const handleBtWindowReset = useCallback(() => {
    setBtWindowStart("");
    setBtWindowEnd("");
  }, []);

  // Build comparison data per config (filtered by backtest window)
  const { comparisonByConfig, rawLiveRByConfig, backtestRByConfig } = useMemo(() => {
    const comparison: Record<string, ComparisonCurvePoint[]> = {};
    const rawLiveR: Record<string, number> = {};
    const backtestR: Record<string, number> = {};
    for (const cfg of visibleConfigs) {
      const mapping = mappings[cfg];
      const btData = backtestCurves[cfg];
      if (!mapping?.deployDate) continue;

      // Filter backtest curve by window
      const fullCurve = btData?.curve ?? [];
      const windowedCurve = fullCurve.filter(
        (p) => p.date >= effectiveBtStart && p.date <= effectiveBtEnd,
      );

      // Re-baseline from the cumulative R immediately before the window.
      // Using the first in-window trade would accidentally drop that trade.
      let baseR = 0;
      for (const p of fullCurve) {
        if (p.date < effectiveBtStart) baseR = p.r;
        else break;
      }
      const rebasedCurve = windowedCurve.map((p) => ({ date: p.date, r: p.r - baseR }));

      // Backtest total R for the visible window
      if (rebasedCurve.length > 0) {
        backtestR[cfg] = rebasedCurve[rebasedCurve.length - 1].r;
      }

      // Build live curve from rows filtered to this config
      const cfgRows = allRows.filter((r) => r.config === cfg);
      const liveCurve = buildLiveEquityCurve(cfgRows);

      // Raw live cumulative R (independent of backtest window)
      if (liveCurve.length > 0) {
        rawLiveR[cfg] = liveCurve[liveCurve.length - 1].r_cumulative;
      }

      // Continue live from the last available rebased backtest value on or
      // before deploy. Exact replays often end before the selected deploy date
      // because local historical data stops at the latest common market date.
      let rebasedRAtDeploy = 0;
      for (const p of rebasedCurve) {
        if (p.date <= mapping.deployDate) rebasedRAtDeploy = p.r;
        else break;
      }

      if (rebasedCurve.length || liveCurve.length) {
        comparison[cfg] = mergeEquityCurves(
          rebasedCurve,
          liveCurve,
          rebasedRAtDeploy,
        );
      }
    }
    return { comparisonByConfig: comparison, rawLiveRByConfig: rawLiveR, backtestRByConfig: backtestR };
  }, [visibleConfigs, mappings, backtestCurves, allRows, effectiveBtStart, effectiveBtEnd]);

  if (loading && dbLoading) {
    return <ExecutionTabSkeleton tab="performance" />;
  }

  const hasActiveFilters =
    activeConfig !== "ALL" || legFilter !== "ALL" || strategyFilter !== "ALL" || sessionFilter !== "ALL" || tickerFilter !== "ALL" || dateFrom !== "" || dateTo !== "";

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="rounded-md border border-border bg-bg-card p-3 space-y-2.5">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {configNames.length > 0 && (
            <FilterSelect
              label="Config"
              value={activeConfig}
              onChange={setActiveConfig}
              allLabel="All Configs"
              options={configNames}
              widthClass="w-[180px]"
            />
          )}

          <FilterSelect
            label="Leg"
            value={legFilter}
            onChange={setLegFilter}
            allLabel="All Legs"
            options={legs}
            widthClass="w-[170px]"
          />

          <FilterSelect
            label="Strategy"
            value={strategyFilter}
            onChange={setStrategyFilter}
            allLabel="All Strategies"
            options={strategies}
            widthClass="w-[150px]"
          />

          <FilterSelect
            label="Session"
            value={sessionFilter}
            onChange={setSessionFilter}
            allLabel="All Sessions"
            options={sessions}
            widthClass="w-[150px]"
          />

          <FilterSelect
            label="Ticker"
            value={tickerFilter}
            onChange={setTickerFilter}
            allLabel="All Tickers"
            options={tickers}
            widthClass="w-[130px]"
          />

          {/* Date range */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-text-muted font-medium uppercase tracking-wide">Date</span>
            <DatePicker value={dateFrom} onChange={setDateFrom} placeholder="From" />
            <span className="text-text-muted text-xs">{"\u2013"}</span>
            <DatePicker value={dateTo} onChange={setDateTo} placeholder="To" />
          </div>

          {/* Clear filters */}
          {hasActiveFilters && (
            <button
              onClick={() => {
                setActiveConfig("ALL");
                setLegFilter("ALL");
                setStrategyFilter("ALL");
                setSessionFilter("ALL");
                setTickerFilter("ALL");
                setDateFrom("");
                setDateTo("");
              }}
              className="text-[11px] text-text-muted hover:text-loss transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="text-sm text-text-muted">
        {rows.length} closed/open trades
      </div>

      <div className="overflow-x-auto overflow-y-auto max-h-[800px] rounded-md border border-border bg-bg-card">
        <table className="min-w-[1380px] w-full border-collapse text-sm">
          <thead className="bg-bg-tertiary text-text-primary sticky top-0 z-10">
            <tr className="text-left">
              <th className="px-3 py-2 border-r border-border/80">Entry Date</th>
              <th className="px-3 py-2 border-r border-border/80">Entry Time</th>
              <th className="px-3 py-2 border-r border-border/80">Exit Date</th>
              <th className="px-3 py-2 border-r border-border/80">Exit Time</th>
              <th className="px-3 py-2 border-r border-border/80">Config</th>
              <th className="px-3 py-2 border-r border-border/80">Leg</th>
              <th className="px-3 py-2 border-r border-border/80">Ticker</th>
              <th className="px-3 py-2 border-r border-border/80">Session</th>
              <th className="px-3 py-2 border-r border-border/80">Direction</th>
              <th className="px-3 py-2 border-r border-border/80">R</th>
              <th className="px-3 py-2 border-r border-border/80">$</th>
              <th className="px-3 py-2">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-4 py-10 text-center text-text-muted">
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

                const configColorClasses = row.config
                  ? CONFIG_COLORS[row.config] ?? "bg-text-muted/20 text-text-muted border-text-muted/30"
                  : "";

                return (
                  <tr key={row.id} className="border-t border-border/60 hover:bg-bg-card-hover/70">
                    <td className="px-3 py-2 font-medium text-text-secondary">{row.entryDate}</td>
                    <td className="px-3 py-2 font-mono text-text-secondary">{row.entryTime}</td>
                    <td className="px-3 py-2 font-medium text-text-secondary">{row.exitDate}</td>
                    <td className="px-3 py-2 font-mono text-text-secondary">{row.exitTime}</td>
                    <td className="px-3 py-2">
                      {row.config ? (
                        <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${configColorClasses}`}>
                          {row.config}
                        </span>
                      ) : (
                        <span className="text-text-muted">\u2014</span>
                      )}
                    </td>
                    <td className="px-3 py-2"><Pill label={row.leg} /></td>
                    <td className="px-3 py-2"><Pill label={row.ticker} tone={tickerTone} /></td>
                    <td className="px-3 py-2"><Pill label={row.session} tone={
                      row.session === "NY" ? "session-ny"
                        : row.session === "LDN" ? "session-ldn"
                        : row.session === "ASIA" ? "session-asia"
                        : "neutral"
                    } /></td>
                    <td className="px-3 py-2">
                      <Pill label={row.direction} tone={row.direction === "Long" ? "long" : "short"} />
                    </td>
                    <td className="px-3 py-2">
                      {row.rValue == null ? (
                        <span className="text-text-muted">\u2014</span>
                      ) : (
                        <Pill label={row.rValue.toFixed(1)} tone={rTone} />
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-text-secondary">
                      {formatUsdValue(row.usdValue)}
                    </td>
                    <td className="px-3 py-2"><Pill label={row.strategy} tone={row.strategy === "LSI" ? "strat-lsi" : "strat-orb"} /></td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Backtest Comparison Settings */}
      <div className="rounded-md border border-border bg-bg-card p-3">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          {visibleConfigs.map((cfg) => {
            const mapping = mappings[cfg] ?? { backtestId: "", deployDate: "" };
            const isLoading = btLoading[cfg];
            const error = btErrors[cfg];
            const colorClass = CONFIG_COLORS[cfg] ?? "";
            return (
              <div key={cfg} className="flex items-end gap-2">
                <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${colorClass}`}>
                  {cfg}
                </span>
                <div className="flex flex-col gap-0.5">
                  <label className="text-[10px] text-text-muted uppercase tracking-wide">Backtest ID</label>
                  <input
                    type="text"
                    value={mapping.backtestId}
                    onChange={(e) => setMapping(cfg, { ...mapping, backtestId: e.target.value })}
                    placeholder="bt-..."
                    className="w-48 rounded border border-border bg-bg-secondary px-2 py-1 text-xs text-text-secondary font-mono focus:outline-none focus:border-accent/60"
                  />
                </div>
                <div className="flex flex-col gap-0.5">
                  <label className="text-[10px] text-text-muted uppercase tracking-wide">Deploy Date</label>
                  <DatePicker
                    value={mapping.deployDate}
                    onChange={(v) => setMapping(cfg, { ...mapping, deployDate: v })}
                    placeholder="Deploy date"
                  />
                </div>
                {isLoading && <span className="text-[11px] text-text-muted animate-pulse">Loading...</span>}
                {error && <span className="text-[11px] text-loss">{error}</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Charts */}
      <div className="space-y-3">
        {/* Backtest window slider */}
        {Object.values(backtestCurves).some((c) => c?.curve.length) && (
          <BacktestWindowSlider
            startDate={effectiveBtStart}
            originalStart={btOriginalBounds.start}
            originalEnd={btOriginalBounds.end}
            onChange={handleBtWindowChange}
            onReset={handleBtWindowReset}
          />
        )}

        {/* Charts for each visible config */}
        {visibleConfigs.map((cfg) => {
          const data = comparisonByConfig[cfg];
          const mapping = mappings[cfg];
          if (!data?.length) return null;
          return (
            <EquityCurveComparison
              key={cfg}
              data={data}
              deployDate={mapping?.deployDate ?? ""}
              configName={cfg}
              liveR={rawLiveRByConfig[cfg] ?? null}
              backtestR={backtestRByConfig[cfg] ?? null}
            />
          );
        })}
      </div>

      {/* Summary stats */}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-md border border-border bg-bg-card px-4 py-3 flex-1">
          <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1">Total R</div>
          <div className={`text-lg font-mono font-semibold ${totalR > 0 ? "text-profit" : totalR < 0 ? "text-loss" : "text-text-secondary"}`}>
            {totalR > 0 ? "+" : ""}{totalR.toFixed(1)}R
          </div>
        </div>
        <div className="rounded-md border border-border bg-bg-card px-4 py-3 flex-1">
          <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1">PnL</div>
          <div className={`text-lg font-mono font-semibold ${totalUsd > 0 ? "text-profit" : totalUsd < 0 ? "text-loss" : "text-text-secondary"}`}>
            {totalUsd > 0 ? "+" : ""}{USD_FORMATTER.format(totalUsd)}
          </div>
        </div>
        <div className="rounded-md border border-border bg-bg-card px-4 py-3 flex-1">
          <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1">Trades Taken</div>
          <div className="text-lg font-mono font-semibold text-text-primary">
            {rows.length}
          </div>
        </div>
        <div className="rounded-md border border-border bg-bg-card px-4 py-3 flex-1">
          <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1">Win Rate</div>
          <div className={`text-lg font-mono font-semibold ${winRate >= 50 ? "text-profit" : winRate > 0 ? "text-loss" : "text-text-secondary"}`}>
            {closedCount > 0 ? `${winRate.toFixed(0)}%` : "\u2014"}
          </div>
        </div>
        <div className="rounded-md border border-border bg-bg-card px-4 py-3 flex-1">
          <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1">Avg R</div>
          <div className={`text-lg font-mono font-semibold ${totalR > 0 ? "text-profit" : totalR < 0 ? "text-loss" : "text-text-secondary"}`}>
            {closedCount > 0 ? `${(totalR / closedCount).toFixed(2)}R` : "\u2014"}
          </div>
        </div>
      </div>
    </div>
  );
}
