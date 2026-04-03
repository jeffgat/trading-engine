#!/usr/bin/env python3
"""NQ ORB Discovery — 3-session SEQUENTIAL sweep WITH bar magnifier.

Uses hierarchical 5m→1m→1s magnifier for accurate fill/exit simulation.
Runs sequential (not parallel) because pickling 1s maps to workers is slower
than running single-threaded with pre-built maps (~3.9s/config vs ~9s/config).

Grid: 4 ORB windows x 2 stop modes x 4 RR x 4 TP1 x 3 directions x 4-5 stops
= ~1,296 configs per session x 3 sessions = ~3,888 total.
Estimated time: ~4-5 hours total.
"""

from __future__ import annotations

import json
import sys
import time
from itertools import product as iprod
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_START,
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest, build_maps, build_signal_cache
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "nq_orb_discovery_3session_mag"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}


# ---------------------------------------------------------------------------
# Session builders
# ---------------------------------------------------------------------------

def _ny_session(orb_minutes, stop_mode):
    orb_end = f"09:{30 + orb_minutes:02d}" if orb_minutes <= 30 else f"10:{orb_minutes - 30:02d}"
    return SessionConfig(
        name="NY", orb_start="09:30", orb_end=orb_end,
        entry_start=orb_end, entry_end="12:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )

def _asia_session(orb_minutes, stop_mode):
    orb_end = f"20:{orb_minutes:02d}"
    return SessionConfig(
        name="Asia", orb_start="20:00", orb_end=orb_end,
        entry_start=orb_end, entry_end="23:15",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )

def _ldn_session(orb_minutes, stop_mode):
    orb_end = f"03:{orb_minutes:02d}"
    return SessionConfig(
        name="LDN", orb_start="03:00", orb_end=orb_end,
        entry_start=orb_end, entry_end="07:00",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )


SESSION_BUILDERS = {"NY": _ny_session, "Asia": _asia_session, "LDN": _ldn_session}
ORB_MINUTES = [15, 30, 45, 60]


def build_all_configs(session_name):
    builder = SESSION_BUILDERS[session_name]
    prefix = session_name.lower()
    configs = []
    for orb_min in ORB_MINUTES:
        for stop_mode in ["atr", "orb"]:
            session = builder(orb_min, stop_mode)
            base = StrategyConfig(
                sessions=(session,), instrument=NQ, strategy="continuation",
                use_bar_magnifier=True,  # MAGNIFIER ON
                risk_usd=5000.0, direction_filter="both",
                rr=2.0, tp1_ratio=0.5, atr_length=14,
                name=f"NQ {session_name} ORB{orb_min}m {stop_mode}",
            )
            if stop_mode == "atr":
                stop_values = [5.0, 7.5, 10.0, 12.5, 15.0]
                stop_key = f"{prefix}_stop_atr_pct"
            else:
                stop_values = [25.0, 50.0, 75.0, 100.0]
                stop_key = f"{prefix}_stop_orb_pct"

            for rr, tp1, direction, stop_v in iprod(
                [2.0, 2.5, 3.0, 3.5], [0.3, 0.4, 0.5, 0.6],
                ["both", "long", "short"], stop_values,
            ):
                if tp1 * rr < 1.0:
                    continue
                try:
                    c = with_overrides(base, rr=rr, tp1_ratio=tp1,
                        direction_filter=direction, **{stop_key: stop_v})
                    configs.append(c)
                except (ValueError, TypeError):
                    continue
    return configs


# ---------------------------------------------------------------------------
# Gate + metrics
# ---------------------------------------------------------------------------

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def compute_period_metrics(trades):
    filled = _filled_trades(trades)
    if not filled: return None
    full = compute_metrics(trades)
    l2 = compute_metrics([t for t in trades if "2022-03-01" <= t.date < HOLDOUT_START])
    l1 = compute_metrics([t for t in trades if "2023-03-01" <= t.date < HOLDOUT_START])
    return {"full": full, "last_2yr": l2, "last_1yr": l1}


def rank_score(m):
    if m is None: return -999
    f = m["full"]
    if f.get("total_trades", 0) < 50: return -999
    cal_f = float(f.get("calmar_ratio", 0) or 0)
    cal_2 = float(m["last_2yr"].get("calmar_ratio", 0) or 0)
    cal_1 = float(m["last_1yr"].get("calmar_ratio", 0) or 0)
    shp = float(f.get("sharpe_ratio", 0) or 0)
    neg = sum(1 for v in (f.get("r_by_year", {}) or {}).values() if float(v) < 0)
    return 0.40 * cal_f + 0.30 * cal_2 + 0.20 * cal_1 + 0.10 * shp - 1.0 * neg


def describe_config(config):
    s = config.sessions[0]
    h1, m1 = map(int, s.orb_start.split(":"))
    h2, m2 = map(int, s.orb_end.split(":"))
    orb_min = (h2 * 60 + m2) - (h1 * 60 + m1)
    stop_mode = "orb" if s.stop_orb_pct > 0 else "atr"
    stop_val = s.stop_orb_pct if stop_mode == "orb" else s.stop_atr_pct
    return {"orb_min": orb_min, "stop_mode": stop_mode, "stop_val": stop_val,
            "rr": config.rr, "tp1": config.tp1_ratio, "dir": config.direction_filter}


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_session(name, df_5m, maps, signal_caches, gate_fn):
    print(f"\n{'=' * 70}")
    print(f"SESSION: {name} (bar magnifier ON, sequential)")
    print(f"{'=' * 70}")

    configs = build_all_configs(name)
    print(f"  Configs: {len(configs)}")

    # Build signal cache for this session's configs
    if name not in signal_caches:
        print(f"  Building signal cache for {name}...", flush=True)
        signal_caches[name] = build_signal_cache(df_5m, configs)

    sig_cache = signal_caches[name]
    t1 = time.time()
    rows = []

    for i, config in enumerate(configs):
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t1
            rate = (i + 1) / elapsed
            eta = (len(configs) - i - 1) / rate / 60
            print(f"    {i+1}/{len(configs)} [{elapsed:.0f}s, ~{eta:.0f}min remaining]", flush=True)

        trades = run_backtest(df_5m, config, end_date=HOLDOUT_START, _maps=maps, _signal_cache=sig_cache)
        filled = _filled_trades(trades)
        if len(filled) < 50:
            continue

        m_ung = compute_period_metrics(trades)
        gated = gate_fn(trades)
        m_gat = compute_period_metrics(gated)
        s_ung = rank_score(m_ung)
        s_gat = rank_score(m_gat)
        best = "gated" if s_gat > s_ung else "ungated"
        bm = m_gat if best == "gated" else m_ung
        if bm is None:
            continue
        f = bm["full"]
        desc = describe_config(config)
        rows.append({
            **desc, "best_variant": best,
            "trades": f.get("total_trades", 0),
            "net_r": round(float(f.get("total_r", 0)), 2),
            "calmar": round(float(f.get("calmar_ratio", 0) or 0), 4),
            "sharpe": round(float(f.get("sharpe_ratio", 0) or 0), 4),
            "max_dd": round(float(f.get("max_drawdown_r", 0)), 2),
            "win_rate": round(float(f.get("win_rate", 0)), 4),
            "pf": round(float(f.get("profit_factor", 0) or 0), 4),
            "l2_calmar": round(float(bm["last_2yr"].get("calmar_ratio", 0) or 0), 4),
            "l1_calmar": round(float(bm["last_1yr"].get("calmar_ratio", 0) or 0), 4),
            "score": round(max(s_ung, s_gat), 4),
            "neg_years": sum(1 for v in (f.get("r_by_year", {}) or {}).values() if float(v) < 0),
            "r_by_year": {str(k): round(float(v), 2) for k, v in (f.get("r_by_year", {}) or {}).items()},
        })

    elapsed = time.time() - t1
    rows.sort(key=lambda r: r["score"], reverse=True)
    print(f"  Done: {len(rows)} viable of {len(configs)} [{elapsed:.0f}s, {elapsed/len(configs):.1f}s/config]")

    # Print top 25
    print(f"\n  TOP 25 ({name}) — bar magnifier ON")
    print(f"  {'#':>3s} {'ORB':>4s} {'SMode':>5s} {'SVal':>5s} {'RR':>4s} {'TP1':>4s} {'Dir':>5s} | {'Var':>6s} {'Tr':>5s} {'NetR':>7s} {'Cal':>6s} {'Shp':>5s} {'DD':>6s} {'WR':>5s} {'L2C':>5s} {'L1C':>5s} {'Neg':>3s} {'Scr':>5s}")
    print(f"  {'-' * 110}")
    for i, r in enumerate(rows[:25]):
        print(
            f"  {i+1:3d} {r['orb_min']:3d}m {r['stop_mode']:>5s} {r['stop_val']:5.0f} "
            f"{r['rr']:4.1f} {r['tp1']:4.1f} {r['dir']:>5s} | "
            f"{r['best_variant']:>6s} {r['trades']:5d} {r['net_r']:+7.1f} {r['calmar']:6.2f} "
            f"{r['sharpe']:5.2f} {r['max_dd']:+6.1f} {r['win_rate']:.0%} "
            f"{r['l2_calmar']:5.2f} {r['l1_calmar']:5.2f} {r['neg_years']:3d} {r['score']:5.2f}"
        )
    return rows


def main():
    print("NQ ORB Discovery — 3-Session Sequential Sweep WITH Bar Magnifier")
    print("=" * 70)
    print(f"Magnifier: 5m → 1m → 1s (hierarchical, drill on ambiguous bars)")
    print(f"Pre-holdout only (<{HOLDOUT_START})")

    t0 = time.time()
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nLoading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    df_1m = load_1m_for_5m(NQ.data_file)
    df_1s = load_1s_for_5m(NQ.data_file)
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,} | 1s={len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    print("\nBuilding bar maps (once)...", flush=True)
    t_maps = time.time()
    maps = build_maps(df_5m, df_1m, None, df_1s)
    print(f"  Maps built [{time.time() - t_maps:.1f}s]")

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    all_results = {}
    signal_caches = {}

    for name in ["NY", "Asia", "LDN"]:
        rows = run_session(name, df_5m, maps, signal_caches, gate_fn)
        all_results[name] = rows[:50]
        if rows:
            pd.DataFrame(rows[:50]).to_csv(output_dir / f"top50_{name.lower()}.csv", index=False)

    write_json(output_dir / "discovery_results.json", all_results)

    print(f"\n{'=' * 70}")
    print(f"Total time: {time.time() - t0:.0f}s ({(time.time() - t0)/60:.1f} min)")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
