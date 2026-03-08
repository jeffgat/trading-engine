import { useCallback, useEffect, useMemo, useState } from "react";
import type { BacktestConfig, SavedConfig } from "@/backtesting/lib/types";
import { useSavedConfigs, type SavedConfigInput } from "@/backtesting/hooks/useSavedConfigs";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionTag } from "./SessionTag";
import { StrategyTag } from "./StrategyTag";

type SessionDefaults = {
  name: string;
  orb_start: string;
  orb_end: string;
  entry_start: string;
  entry_end: string;
  flat_start: string;
  flat_end: string;
  rth_start?: string;
  stop_atr_pct?: number;
  min_gap_atr_pct?: number;
  stop_orb_pct?: number;
  min_gap_orb_pct?: number;
};

type InstrumentInfo = {
  symbol: string;
  point_value: number;
};

type ConfigFormState = {
  name: string;
  notes: string;
  instrument: string;
  sessions: string[];
  strategy: string;
  config: BacktestConfig;
};

const DEFAULT_CONFIG: BacktestConfig = {
  rr: 2.5,
  tp1_ratio: 0.5,
  risk_usd: 5000,
  atr_length: 14,
  min_qty: 1,
  qty_step: 1,
  direction_filter: "both",
  use_bar_magnifier: true,
};

const STRATEGY_OPTIONS = [
  { value: "continuation", label: "ORB" },
  { value: "lsi", label: "LSI" },
];

const INPUT_CLASS =
  "w-full rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-accent";

const SECTION_TITLE =
  "text-[11px] font-medium uppercase tracking-wider text-text-muted";

function sessionPrefix(name: string) {
  return name.toLowerCase();
}

function formatWindow(start: string, end: string) {
  if (!start || !end) return "";
  return `${start}-${end}`;
}

function parseNumber(value: string, fallback: number) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function defaultForm(): ConfigFormState {
  return {
    name: "",
    notes: "",
    instrument: "",
    sessions: ["NY"],
    strategy: "continuation",
    config: { ...DEFAULT_CONFIG },
  };
}

function formatUpdated(ts: string) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ConfigsDashboard() {
  const { configs, loading, error, createConfig, updateConfig, deleteConfig } = useSavedConfigs();
  const [form, setForm] = useState<ConfigFormState>(defaultForm());
  const [activeId, setActiveId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [sessions, setSessions] = useState<SessionDefaults[]>([]);

  const isLsi = form.strategy === "lsi";

  useEffect(() => {
    const load = async () => {
      try {
        const [instRes, sessRes] = await Promise.all([
          fetch("/bt-api/instruments"),
          fetch("/bt-api/sessions"),
        ]);
        if (instRes.ok) {
          const json = await instRes.json();
          setInstruments(json.result ?? json);
        }
        if (sessRes.ok) {
          const json = await sessRes.json();
          setSessions(json.result ?? json);
        }
      } catch {
        // ignore loading failures
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!form.instrument && instruments.length > 0) {
      setForm((prev) => ({
        ...prev,
        instrument: instruments[0].symbol,
        config: { ...prev.config, instrument: instruments[0].symbol, point_value: instruments[0].point_value },
      }));
    }
  }, [form.instrument, instruments]);

  const sessionOptions = useMemo(() => sessions.map((s) => s.name), [sessions]);

  const applySessionDefaults = useCallback((nextSessions: string[]) => {
    setForm((prev) => {
      const nextConfig: BacktestConfig = { ...prev.config };
      nextSessions.forEach((name) => {
        const prefix = sessionPrefix(name);
        const defaults = sessions.find((s) => s.name === name);
        if (!defaults) return;
        const orbWindow = formatWindow(defaults.orb_start, defaults.orb_end);
        const entryWindow = formatWindow(defaults.entry_start, defaults.entry_end);
        const flatWindow = formatWindow(defaults.flat_start, defaults.flat_end);
        if (orbWindow && nextConfig[`${prefix}_orb_window`] == null) {
          nextConfig[`${prefix}_orb_window`] = orbWindow;
        }
        if (entryWindow && nextConfig[`${prefix}_entry_window`] == null) {
          nextConfig[`${prefix}_entry_window`] = entryWindow;
        }
        if (flatWindow && nextConfig[`${prefix}_flat_window`] == null) {
          nextConfig[`${prefix}_flat_window`] = flatWindow;
        }
        if (defaults.rth_start && nextConfig[`${prefix}_rth_start`] == null) {
          nextConfig[`${prefix}_rth_start`] = defaults.rth_start;
        }
        if (defaults.stop_atr_pct != null && nextConfig[`${prefix}_stop_atr_pct`] == null) {
          nextConfig[`${prefix}_stop_atr_pct`] = defaults.stop_atr_pct;
        }
        if (defaults.min_gap_atr_pct != null && nextConfig[`${prefix}_min_gap_atr_pct`] == null) {
          nextConfig[`${prefix}_min_gap_atr_pct`] = defaults.min_gap_atr_pct;
        }
        if (defaults.stop_orb_pct != null && nextConfig[`${prefix}_stop_orb_pct`] == null) {
          nextConfig[`${prefix}_stop_orb_pct`] = defaults.stop_orb_pct;
        }
        if (defaults.min_gap_orb_pct != null && nextConfig[`${prefix}_min_gap_orb_pct`] == null) {
          nextConfig[`${prefix}_min_gap_orb_pct`] = defaults.min_gap_orb_pct;
        }
      });
      return { ...prev, sessions: nextSessions, config: nextConfig };
    });
  }, [sessions]);

  const handleField = (key: keyof ConfigFormState, value: string | string[]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleConfigNumber = (key: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      config: { ...prev.config, [key]: parseNumber(value, Number(prev.config[key]) || 0) },
    }));
  };

  const handleConfigText = (key: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      config: { ...prev.config, [key]: value },
    }));
  };

  const handleConfigToggle = (key: string, checked: boolean) => {
    setForm((prev) => ({
      ...prev,
      config: { ...prev.config, [key]: checked },
    }));
  };

  const setStrategy = (nextStrategy: string) => {
    setForm((prev) => ({
      ...prev,
      strategy: nextStrategy,
      config: { ...prev.config, strategy: nextStrategy },
    }));
  };

  const setInstrument = (symbol: string) => {
    const inst = instruments.find((i) => i.symbol === symbol);
    setForm((prev) => ({
      ...prev,
      instrument: symbol,
      config: {
        ...prev.config,
        instrument: symbol,
        point_value: inst?.point_value ?? prev.config.point_value,
      },
    }));
  };

  const loadConfigIntoForm = useCallback((config: SavedConfig) => {
    setActiveId(config.id);
    setForm({
      name: config.name ?? "",
      notes: config.notes ?? "",
      instrument: config.instrument,
      sessions: config.sessions ?? [],
      strategy: config.strategy ?? "continuation",
      config: {
        ...DEFAULT_CONFIG,
        ...config.config,
        instrument: config.instrument,
        strategy: config.strategy,
      },
    });
  }, []);

  const handleNew = () => {
    setActiveId(null);
    setForm(defaultForm());
    if (instruments.length > 0) {
      setInstrument(instruments[0].symbol);
    }
  };

  const handleDuplicate = () => {
    setActiveId(null);
    setForm((prev) => ({ ...prev, name: `${prev.name || "Config"} Copy` }));
  };

  const buildPayload = (): SavedConfigInput | null => {
    if (!form.name.trim() || !form.instrument || form.sessions.length === 0) {
      setSaveError("name, instrument, and at least one session are required.");
      return null;
    }
    const base: BacktestConfig = {
      ...form.config,
      instrument: form.instrument,
      strategy: form.strategy,
    };

    const config: BacktestConfig = {};
    const allowedPrefixes = form.sessions.map((s) => `${sessionPrefix(s)}_`);
    Object.entries(base).forEach(([key, value]) => {
      if (value == null) return;
      const isSessionKey = allowedPrefixes.some((p) => key.startsWith(p));
      if (key.startsWith("lsi_") && !isLsi) return;
      if (!isSessionKey && key.includes("_") && (key.endsWith("_window") || key.endsWith("_atr_pct") || key.endsWith("_orb_pct") || key.endsWith("_rth_start"))) {
        return;
      }
      if (isSessionKey || !key.startsWith("lsi_")) {
        config[key] = value;
      }
    });

    return {
      name: form.name.trim(),
      notes: form.notes.trim() || null,
      instrument: form.instrument,
      sessions: form.sessions,
      strategy: form.strategy,
      config,
    };
  };

  const handleSave = async () => {
    const payload = buildPayload();
    if (!payload) return;
    setSaveError(null);
    setSaveLoading(true);
    try {
      if (activeId) {
        const result = await updateConfig(activeId, payload);
        if (!result) setSaveError("failed to update config.");
      } else {
        const result = await createConfig(payload);
        if (result?.id) setActiveId(result.id);
        if (!result) setSaveError("failed to create config.");
      }
    } finally {
      setSaveLoading(false);
    }
  };

  const handleDelete = async () => {
    if (deleteId == null) return;
    await deleteConfig(deleteId);
    if (activeId === deleteId) handleNew();
    setDeleteId(null);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Configs</h1>
          <p className="text-xs text-text-muted">Save reusable ORB/LSI parameter sets.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleNew}
            className="rounded-md border border-border bg-bg-secondary px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card-hover"
          >
            New
          </button>
          <button
            onClick={handleDuplicate}
            className="rounded-md border border-border bg-bg-secondary px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card-hover"
          >
            Duplicate
          </button>
          <button
            onClick={handleSave}
            disabled={saveLoading}
            className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            {saveLoading ? "Saving..." : activeId ? "Save Changes" : "Save Config"}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="mb-4 rounded-md border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
          {saveError}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-bg-card p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className={SECTION_TITLE}>name</label>
                <input
                  className={INPUT_CLASS}
                  value={form.name}
                  onChange={(e) => handleField("name", e.target.value)}
                />
              </div>
              <div>
                <label className={SECTION_TITLE}>strategy</label>
                <select
                  className={INPUT_CLASS}
                  value={form.strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                >
                  {STRATEGY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={SECTION_TITLE}>instrument</label>
                <select
                  className={INPUT_CLASS}
                  value={form.instrument}
                  onChange={(e) => setInstrument(e.target.value)}
                >
                  {instruments.map((inst) => (
                    <option key={inst.symbol} value={inst.symbol}>{inst.symbol}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={SECTION_TITLE}>sessions</label>
                <div className="flex flex-wrap gap-2 pt-1">
                  {sessionOptions.map((s) => (
                    <label key={s} className="flex items-center gap-1 text-xs text-text-secondary">
                      <input
                        type="checkbox"
                        checked={form.sessions.includes(s)}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...form.sessions, s]
                            : form.sessions.filter((sess) => sess !== s);
                          applySessionDefaults(next);
                        }}
                        className="h-3 w-3 accent-accent"
                      />
                      {s}
                    </label>
                  ))}
                </div>
              </div>
              <div className="sm:col-span-2">
                <label className={SECTION_TITLE}>notes</label>
                <textarea
                  className={`${INPUT_CLASS} min-h-[64px]`}
                  value={form.notes}
                  onChange={(e) => handleField("notes", e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-bg-card p-4">
            <h3 className="mb-3 text-sm font-medium text-text-secondary">Shared Params</h3>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <div>
                <label className={SECTION_TITLE}>risk usd</label>
                <input
                  type="number"
                  className={INPUT_CLASS}
                  value={form.config.risk_usd ?? ""}
                  onChange={(e) => handleConfigNumber("risk_usd", e.target.value)}
                />
              </div>
              <div>
                <label className={SECTION_TITLE}>rr</label>
                <input
                  type="number"
                  className={INPUT_CLASS}
                  value={form.config.rr ?? ""}
                  onChange={(e) => handleConfigNumber("rr", e.target.value)}
                />
              </div>
              <div>
                <label className={SECTION_TITLE}>tp1 ratio</label>
                <input
                  type="number"
                  className={INPUT_CLASS}
                  value={form.config.tp1_ratio ?? ""}
                  onChange={(e) => handleConfigNumber("tp1_ratio", e.target.value)}
                />
              </div>
              <div>
                <label className={SECTION_TITLE}>atr length</label>
                <input
                  type="number"
                  className={INPUT_CLASS}
                  value={form.config.atr_length ?? ""}
                  onChange={(e) => handleConfigNumber("atr_length", e.target.value)}
                />
              </div>
              <div>
                <label className={SECTION_TITLE}>direction</label>
                <select
                  className={INPUT_CLASS}
                  value={(form.config.direction_filter as string) ?? "both"}
                  onChange={(e) => handleConfigText("direction_filter", e.target.value)}
                >
                  <option value="both">Both</option>
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </div>
              <div>
                <label className={SECTION_TITLE}>bar magnifier</label>
                <select
                  className={INPUT_CLASS}
                  value={form.config.use_bar_magnifier ? "on" : "off"}
                  onChange={(e) => handleConfigToggle("use_bar_magnifier", e.target.value === "on")}
                >
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </div>
            </div>
          </div>

          {!isLsi && (
            <div className="rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">ORB Params</h3>
              <div className="space-y-3">
                {form.sessions.map((s) => {
                  const prefix = sessionPrefix(s);
                  return (
                    <div key={s} className="rounded-md border border-border/50 bg-bg-secondary/40 p-3">
                      <div className="mb-2 flex items-center gap-2">
                        <SessionTag session={s} />
                        <span className="text-[10px] text-text-muted">{prefix.toUpperCase()}</span>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <label className={SECTION_TITLE}>stop atr %</label>
                          <input
                            type="number"
                            className={INPUT_CLASS}
                            value={form.config[`${prefix}_stop_atr_pct`] ?? ""}
                            onChange={(e) => handleConfigNumber(`${prefix}_stop_atr_pct`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>min gap atr %</label>
                          <input
                            type="number"
                            className={INPUT_CLASS}
                            value={form.config[`${prefix}_min_gap_atr_pct`] ?? ""}
                            onChange={(e) => handleConfigNumber(`${prefix}_min_gap_atr_pct`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>orb window</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_orb_window`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_orb_window`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>entry window</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_entry_window`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_entry_window`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>flat window</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_flat_window`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_flat_window`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>stop orb %</label>
                          <input
                            type="number"
                            className={INPUT_CLASS}
                            value={form.config[`${prefix}_stop_orb_pct`] ?? ""}
                            onChange={(e) => handleConfigNumber(`${prefix}_stop_orb_pct`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>min gap orb %</label>
                          <input
                            type="number"
                            className={INPUT_CLASS}
                            value={form.config[`${prefix}_min_gap_orb_pct`] ?? ""}
                            onChange={(e) => handleConfigNumber(`${prefix}_min_gap_orb_pct`, e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {isLsi && (
            <div className="rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">LSI Params</h3>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
                <div>
                  <label className={SECTION_TITLE}>swing n left</label>
                  <input
                    type="number"
                    className={INPUT_CLASS}
                    value={form.config.lsi_n_left ?? ""}
                    onChange={(e) => handleConfigNumber("lsi_n_left", e.target.value)}
                  />
                </div>
                <div>
                  <label className={SECTION_TITLE}>swing n right</label>
                  <input
                    type="number"
                    className={INPUT_CLASS}
                    value={form.config.lsi_n_right ?? ""}
                    onChange={(e) => handleConfigNumber("lsi_n_right", e.target.value)}
                  />
                </div>
                <div>
                  <label className={SECTION_TITLE}>fvg window left</label>
                  <input
                    type="number"
                    className={INPUT_CLASS}
                    value={form.config.lsi_fvg_window_left ?? ""}
                    onChange={(e) => handleConfigNumber("lsi_fvg_window_left", e.target.value)}
                  />
                </div>
                <div>
                  <label className={SECTION_TITLE}>fvg window right</label>
                  <input
                    type="number"
                    className={INPUT_CLASS}
                    value={form.config.lsi_fvg_window_right ?? ""}
                    onChange={(e) => handleConfigNumber("lsi_fvg_window_right", e.target.value)}
                  />
                </div>
                <div>
                  <label className={SECTION_TITLE}>stop mode</label>
                  <select
                    className={INPUT_CLASS}
                    value={String(form.config.lsi_stop_mode ?? "absolute")}
                    onChange={(e) => handleConfigText("lsi_stop_mode", e.target.value)}
                  >
                    <option value="absolute">absolute</option>
                    <option value="fvg">fvg</option>
                  </select>
                </div>
                <div>
                  <label className={SECTION_TITLE}>entry mode</label>
                  <select
                    className={INPUT_CLASS}
                    value={String(form.config.lsi_entry_mode ?? "close")}
                    onChange={(e) => handleConfigText("lsi_entry_mode", e.target.value)}
                  >
                    <option value="close">close</option>
                    <option value="fvg_limit">fvg_limit</option>
                  </select>
                </div>
                <div>
                  <label className={SECTION_TITLE}>first fvg only</label>
                  <select
                    className={INPUT_CLASS}
                    value={form.config.lsi_first_fvg_only ? "on" : "off"}
                    onChange={(e) => handleConfigToggle("lsi_first_fvg_only", e.target.value === "on")}
                  >
                    <option value="off">off</option>
                    <option value="on">on</option>
                  </select>
                </div>
                <div>
                  <label className={SECTION_TITLE}>clean path</label>
                  <select
                    className={INPUT_CLASS}
                    value={form.config.lsi_clean_path ? "on" : "off"}
                    onChange={(e) => handleConfigToggle("lsi_clean_path", e.target.value === "on")}
                  >
                    <option value="off">off</option>
                    <option value="on">on</option>
                  </select>
                </div>
                <div>
                  <label className={SECTION_TITLE}>be swing n left</label>
                  <input
                    type="number"
                    className={INPUT_CLASS}
                    value={form.config.lsi_be_swing_n_left ?? ""}
                    onChange={(e) => handleConfigNumber("lsi_be_swing_n_left", e.target.value)}
                  />
                </div>
                <div>
                  <label className={SECTION_TITLE}>cancel on swing</label>
                  <select
                    className={INPUT_CLASS}
                    value={form.config.lsi_cancel_on_swing ? "on" : "off"}
                    onChange={(e) => handleConfigToggle("lsi_cancel_on_swing", e.target.value === "on")}
                  >
                    <option value="off">off</option>
                    <option value="on">on</option>
                  </select>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {form.sessions.map((s) => {
                  const prefix = sessionPrefix(s);
                  return (
                    <div key={s} className="rounded-md border border-border/50 bg-bg-secondary/40 p-3">
                      <div className="mb-2 flex items-center gap-2">
                        <SessionTag session={s} />
                        <span className="text-[10px] text-text-muted">{prefix.toUpperCase()}</span>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <label className={SECTION_TITLE}>rth start</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_rth_start`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_rth_start`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>entry window</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_entry_window`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_entry_window`, e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={SECTION_TITLE}>flat window</label>
                          <input
                            className={INPUT_CLASS}
                            value={String(form.config[`${prefix}_flat_window`] ?? "")}
                            onChange={(e) => handleConfigText(`${prefix}_flat_window`, e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border bg-bg-card">
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="text-sm font-medium text-text-secondary">Saved Configs</h2>
            <span className="text-xs text-text-muted">{configs.length} total</span>
          </div>
          {loading && (
            <div className="px-4 pb-4 text-xs text-text-muted">Loading configs...</div>
          )}
          {error && (
            <div className="px-4 pb-4 text-xs text-loss">{error}</div>
          )}
          {!loading && configs.length === 0 && (
            <div className="px-4 pb-4 text-xs text-text-muted">No configs saved yet.</div>
          )}
          <div className="divide-y divide-border/60">
            {configs.map((item) => (
              <button
                key={item.id}
                onClick={() => loadConfigIntoForm(item)}
                className={`flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-bg-card-hover ${
                  activeId === item.id ? "bg-accent/10" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-text-primary">{item.name}</div>
                  <div className="text-[10px] text-text-muted">{formatUpdated(item.updated_at)}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                  <span className="font-medium text-text-secondary">{item.instrument}</span>
                  <StrategyTag strategy={item.strategy} />
                  <div className="flex gap-1">
                    {item.sessions.map((s) => (
                      <SessionTag key={s} session={s} />
                    ))}
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteId(item.id);
                    }}
                    className="rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1 text-[10px] font-medium text-red-400 transition-colors hover:bg-red-500/20"
                  >
                    Delete
                  </button>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <ConfirmDeleteDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null); }}
        onConfirm={handleDelete}
        title="Delete config?"
        description="This config will be permanently removed."
      />
    </div>
  );
}
