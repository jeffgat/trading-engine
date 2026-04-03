#!/usr/bin/env python3
"""ES ORB Discovery — 3-session parallel sweep with regime gate.

Base config per session:
- 15m ORB window (sweeps up to 1hr in 15m steps)
- RR=2.0, TP1=0.5 (halfway)
- 10% ATR stop OR 50% ORB stop (test both)
- 1% ATR min gap
- Both directions
- ATR 14
- 1 trade per asset per session (engine default)

Sweep priority: ORB window > RR/TP1/stop sizing >> min gap, ATR

Pre-holdout only (<2024-03). 4 parallel workers.
"""

from __future__ import annotations

import json
import sys
import time
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
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "es_orb_discovery_3session"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
N_WORKERS = 4


# ---------------------------------------------------------------------------
# Session base configs
# ---------------------------------------------------------------------------

# ORB windows: 15m base, sweep to 30m, 45m, 60m
# Stop modes: ATR-based (stop_atr_pct) vs ORB-based (stop_orb_pct)

# We build two base configs per session: one ATR-stop, one ORB-stop.
# The grid sweeps sizing params on top of each.

def _ny_session(orb_minutes: int, stop_mode: str) -> SessionConfig:
    orb_end = f"09:{30 + orb_minutes:02d}" if orb_minutes <= 30 else f"10:{orb_minutes - 30:02d}"
    entry_start = orb_end
    return SessionConfig(
        name="NY",
        orb_start="09:30", orb_end=orb_end,
        entry_start=entry_start, entry_end="12:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )


def _asia_session(orb_minutes: int, stop_mode: str) -> SessionConfig:
    orb_end = f"20:{orb_minutes:02d}"
    entry_start = orb_end
    return SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end=orb_end,
        entry_start=entry_start, entry_end="23:15",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )


def _ldn_session(orb_minutes: int, stop_mode: str) -> SessionConfig:
    orb_end = f"03:{orb_minutes:02d}"
    entry_start = orb_end
    return SessionConfig(
        name="LDN",
        orb_start="03:00", orb_end=orb_end,
        entry_start=entry_start, entry_end="07:00",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=10.0 if stop_mode == "atr" else 0.0,
        stop_orb_pct=50.0 if stop_mode == "orb" else 0.0,
        min_gap_atr_pct=1.0,
    )


SESSION_BUILDERS = {
    "NY": _ny_session,
    "Asia": _asia_session,
    "LDN": _ldn_session,
}

ORB_MINUTES = [15, 30, 45, 60]  # 15m steps up to 1hr


def build_all_configs(session_name: str) -> list[StrategyConfig]:
    """Build full config list for one session: ORB windows x stop modes x sizing params."""
    builder = SESSION_BUILDERS[session_name]
    prefix = session_name.lower()
    configs = []

    for orb_min in ORB_MINUTES:
        for stop_mode in ["atr", "orb"]:
            session = builder(orb_min, stop_mode)
            base = StrategyConfig(
                sessions=(session,),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=False,  # Discovery sweep — 5m resolution only for speed
                risk_usd=5000.0,
                direction_filter="both",
                rr=2.0,
                tp1_ratio=0.5,
                atr_length=14,
                name=f"ES {session_name} ORB{orb_min}m {stop_mode}-stop",
            )

            # Primary sweep: RR x TP1 x stop sizing x direction
            if stop_mode == "atr":
                stop_values = [5.0, 7.5, 10.0, 12.5, 15.0]
                stop_key = f"{prefix}_stop_atr_pct"
            else:
                stop_values = [25.0, 50.0, 75.0, 100.0]
                stop_key = f"{prefix}_stop_orb_pct"

            rrs = [2.0, 2.5, 3.0, 3.5]
            tp1s = [0.3, 0.4, 0.5, 0.6]
            directions = ["both", "long", "short"]

            from itertools import product as iprod
            for rr, tp1, direction, stop_v in iprod(rrs, tp1s, directions, stop_values):
                if tp1 * rr < 1.0:
                    continue
                try:
                    c = with_overrides(base,
                        rr=rr, tp1_ratio=tp1,
                        direction_filter=direction,
                        **{stop_key: stop_v},
                    )
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
        return [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS
        ]
    return gate


def compute_period_metrics(trades):
    filled = _filled_trades(trades)
    if not filled:
        return None
    full = compute_metrics(trades)
    l2 = compute_metrics([t for t in trades if "2022-03-01" <= t.date < HOLDOUT_START])
    l1 = compute_metrics([t for t in trades if "2023-03-01" <= t.date < HOLDOUT_START])
    return {"full": full, "last_2yr": l2, "last_1yr": l1}


def rank_score(m):
    if m is None:
        return -999
    f = m["full"]
    if f.get("total_trades", 0) < 50:
        return -999
    cal_f = float(f.get("calmar_ratio", 0) or 0)
    cal_2 = float(m["last_2yr"].get("calmar_ratio", 0) or 0)
    cal_1 = float(m["last_1yr"].get("calmar_ratio", 0) or 0)
    shp = float(f.get("sharpe_ratio", 0) or 0)
    neg = sum(1 for v in (f.get("r_by_year", {}) or {}).values() if float(v) < 0)
    return 0.40 * cal_f + 0.30 * cal_2 + 0.20 * cal_1 + 0.10 * shp - 1.0 * neg


def describe_config(config):
    """Extract human-readable params from a config."""
    s = config.sessions[0]
    orb_min = _orb_minutes(s.orb_start, s.orb_end)
    stop_mode = "orb" if s.stop_orb_pct > 0 else "atr"
    stop_val = s.stop_orb_pct if stop_mode == "orb" else s.stop_atr_pct
    return {
        "orb_min": orb_min,
        "stop_mode": stop_mode,
        "stop_val": stop_val,
        "rr": config.rr,
        "tp1": config.tp1_ratio,
        "dir": config.direction_filter,
        "gap": s.min_gap_atr_pct,
        "atr": config.atr_length,
    }


def _orb_minutes(orb_start, orb_end):
    """Compute ORB window in minutes from time strings."""
    h1, m1 = map(int, orb_start.split(":"))
    h2, m2 = map(int, orb_end.split(":"))
    return (h2 * 60 + m2) - (h1 * 60 + m1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def run_session(name, df_5m, df_1m, df_1s, gate_fn):
    print(f"\n{'=' * 70}")
    print(f"SESSION: {name}")
    print(f"{'=' * 70}")

    configs = build_all_configs(name)
    print(f"  Total configs: {len(configs)} | Workers: {N_WORKERS}")

    t1 = time.time()
    results = run_sweep(
        df_5m, configs,
        n_workers=N_WORKERS,
        end_date=HOLDOUT_START,
        df_1m=df_1m, df_1s=df_1s,
        progress_fn=lambda i, n: print(f"    {i}/{n}", flush=True) if i % 200 == 0 else None,
    )
    elapsed = time.time() - t1
    print(f"  Sweep done: {len(results)} results [{elapsed:.0f}s, {elapsed/len(results):.1f}s/config]")

    # Score each config ungated + gated
    rows = []
    for config, trades in results:
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
        bs = max(s_ung, s_gat)

        if bm is None:
            continue

        desc = describe_config(config)
        f = bm["full"]

        rows.append({
            **desc,
            "best_variant": best,
            "trades": f.get("total_trades", 0),
            "net_r": round(float(f.get("total_r", 0)), 2),
            "calmar": round(float(f.get("calmar_ratio", 0) or 0), 4),
            "sharpe": round(float(f.get("sharpe_ratio", 0) or 0), 4),
            "max_dd": round(float(f.get("max_drawdown_r", 0)), 2),
            "win_rate": round(float(f.get("win_rate", 0)), 4),
            "pf": round(float(f.get("profit_factor", 0) or 0), 4),
            "avg_r": round(float(f.get("avg_r", 0)), 4),
            "l2_calmar": round(float(bm["last_2yr"].get("calmar_ratio", 0) or 0), 4),
            "l1_calmar": round(float(bm["last_1yr"].get("calmar_ratio", 0) or 0), 4),
            "l2_net_r": round(float(bm["last_2yr"].get("total_r", 0)), 2),
            "l1_net_r": round(float(bm["last_1yr"].get("total_r", 0)), 2),
            "score": round(bs, 4),
            "neg_years": sum(1 for v in (f.get("r_by_year", {}) or {}).values() if float(v) < 0),
            "r_by_year": {str(k): round(float(v), 2) for k, v in (f.get("r_by_year", {}) or {}).items()},
        })

    rows.sort(key=lambda r: r["score"], reverse=True)

    # Print top 25
    print(f"\n  TOP 25 ({name}) — {len(rows)} viable of {len(configs)}")
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
    print("ES ORB Discovery — 3-Session Parallel Sweep")
    print("=" * 70)
    print(f"Workers: {N_WORKERS} | Pre-holdout only (<{HOLDOUT_START})")
    print(f"ORB windows: 15/30/45/60m | Stop modes: ATR + ORB")
    print(f"RR sweep: 2.0/2.5/3.0/3.5 | TP1 sweep: 0.3/0.4/0.5/0.6")

    t0 = time.time()
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nLoading ES data (5m only — no bar magnifier for discovery)...", flush=True)
    df_5m = load_5m_data(ES.data_file)
    df_1m = None
    df_1s = None
    print(f"  5m={len(df_5m):,} [{time.time() - t0:.1f}s]")

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_calendar)

    all_results = {}

    for name in ["NY", "Asia", "LDN"]:
        rows = run_session(name, df_5m, df_1m, df_1s, gate_fn)
        all_results[name] = rows[:50]
        if rows:
            pd.DataFrame(rows[:50]).to_csv(output_dir / f"top50_{name.lower()}.csv", index=False)

    write_json(output_dir / "discovery_results.json", all_results)

    print(f"\n{'=' * 70}")
    print(f"Total time: {time.time() - t0:.0f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
