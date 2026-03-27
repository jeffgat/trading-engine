#!/usr/bin/env python3
"""Run FAST and SLOW execution portfolio backtests.

Mirrors the exact strategy configs and risk_usd overrides from
execution/config/exec_configs.json. Produces two saved backtests
(one per exec config) for comparison against live performance.

Usage:
    python scripts/run_exec_portfolio.py
    python scripts/run_exec_portfolio.py --start 2016-01-01 --end 2026-01-01
    python scripts/run_exec_portfolio.py --config FAST
    python scripts/run_exec_portfolio.py --config SLOW
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import (
    run_backtest, EXIT_NO_FILL, EXIT_NAMES,
    EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, TradeResult,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import save_backtest_result
from orb_backtest.analysis.gates import apply_dow_filter

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

HALF_DAYS = (
    "20250703", "20251128", "20251224", "20250109", "20260119",
    "20240703", "20241129", "20241224",
)

TP1_EXIT_TYPES = {EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD}

# ── Leg definitions ─────────────────────────────────────────────────────
# Each returns (StrategyConfig, instrument_symbol, excluded_dow_set)
# risk_usd is set per-leg from the exec config overrides.


def leg_nq_ny(risk_usd):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=7.0, min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.4, atr_length=12,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("NQ"),
        direction_filter="long", half_days=HALF_DAYS,
        name="NQ_NY",
    ), "NQ", {4}  # excl Friday


def leg_nq_asia(risk_usd):
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_orb_pct=100.0, min_gap_orb_pct=10.0,
    )
    return StrategyConfig(
        rr=6.0, tp1_ratio=0.3, atr_length=5,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("NQ"),
        direction_filter="long", half_days=HALF_DAYS,
        name="NQ_Asia",
    ), "NQ", {1}  # excl Tuesday


def leg_gc_ny(risk_usd):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="12:00",
        flat_start="13:30", flat_end="16:00",
        stop_atr_pct=4.5, min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        rr=9.0, tp1_ratio=0.35, atr_length=7,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("GC"),
        direction_filter="long", impulse_close_filter=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
        name="GC_NY",
    ), "GC", {4}  # excl Friday


def leg_es_ny(risk_usd):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=0.25,
        min_stop_points=3.0, min_tp1_points=3.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, atr_length=7,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("ES"),
        direction_filter="long", half_days=HALF_DAYS,
        name="ES_NY",
    ), "ES", {3}  # excl Thursday


def leg_es_asia(risk_usd):
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_orb_pct=125.0, min_gap_atr_pct=0.5,
        min_stop_points=3.0, min_tp1_points=3.0,
    )
    return StrategyConfig(
        rr=1.5, tp1_ratio=0.7, atr_length=14,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("ES"),
        direction_filter="long", half_days=HALF_DAYS,
        name="ES_Asia",
    ), "ES", set()  # no DOW exclusion


def leg_nq_ldn(risk_usd):
    session = SessionConfig(
        name="LDN",
        orb_start="03:00", orb_end="03:30",
        entry_start="03:30", entry_end="08:25",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=1.5, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=6.0, tp1_ratio=0.7, atr_length=10,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("NQ"),
        direction_filter="long", half_days=HALF_DAYS,
        name="NQ_LDN",
    ), "NQ", set()  # G5 gate applied separately


def leg_nq_asia_lsi(risk_usd):
    session = SessionConfig(
        name="Asia",
        rth_start="20:00",
        entry_start="20:40", entry_end="23:30",
        flat_start="04:00", flat_end="07:00",
        min_gap_atr_pct=1.75,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=2.0, tp1_ratio=0.7, atr_length=40,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("NQ"),
        direction_filter="long", half_days=HALF_DAYS,
        lsi_n_left=8, lsi_n_right=2,
        lsi_fvg_window_left=15, lsi_fvg_window_right=2,
        lsi_entry_mode="close",
        name="NQ_Asia_LSI",
    ), "NQ", set()  # no DOW exclusion


def leg_nq_ny_lsi(risk_usd):
    session = SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35", entry_end="15:30",
        flat_start="15:50", flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=3.0, tp1_ratio=0.3, atr_length=10,
        risk_usd=risk_usd,
        sessions=(session,), instrument=get_instrument("NQ"),
        direction_filter="long", half_days=HALF_DAYS,
        lsi_n_left=8, lsi_n_right=60,
        lsi_fvg_window_left=20, lsi_fvg_window_right=5,
        lsi_entry_mode="fvg_limit",
        name="NQ_NY_LSI",
    ), "NQ", {2, 3}  # excl Wed, Thu


# ── Exec config definitions ────────────────────────────────────────────

EXEC_CONFIGS = {
    "FAST": {
        "legs": [
            ("NQ_NY",       leg_nq_ny,       200),
            ("NQ_Asia",     leg_nq_asia,     150),
            ("GC_NY",       leg_gc_ny,       250),
            ("ES_NY",       leg_es_ny,       250),
            ("ES_Asia",     leg_es_asia,     100),
            ("NQ_LDN",      leg_nq_ldn,      150),  # G5 gated
            ("NQ_Asia_LSI", leg_nq_asia_lsi, 250),
            ("NQ_NY_LSI",   leg_nq_ny_lsi,   250),  # 2x qty
        ],
        "qty_multipliers": {"NQ_NY_LSI": 2.0},
        "g5_gate": True,
    },
    "SLOW": {
        "legs": [
            ("NQ_NY",       leg_nq_ny,       159),
            ("NQ_Asia",     leg_nq_asia,     130),
            ("GC_NY",       leg_gc_ny,       90),
            ("NQ_Asia_LSI", leg_nq_asia_lsi, 161),
            ("NQ_NY_LSI",   leg_nq_ny_lsi,   200),  # 2x qty
        ],
        "qty_multipliers": {"NQ_NY_LSI": 2.0},
        "g5_gate": False,  # no LDN leg in SLOW
    },
}


# ── G5 Gate ─────────────────────────────────────────────────────────────

def apply_g5_gate(ldn_trades, asia_legs_trades):
    """Skip NQ LDN trades on days when any Asia leg hit TP1 the prior night."""
    asia_tp1_dates = set()
    for trades in asia_legs_trades:
        for t in trades:
            if t.exit_type == EXIT_NO_FILL:
                continue
            if t.exit_type in TP1_EXIT_TYPES:
                asia_date = datetime.strptime(t.date, "%Y-%m-%d")
                ldn_date = asia_date + timedelta(days=1)
                while ldn_date.weekday() >= 5:
                    ldn_date += timedelta(days=1)
                asia_tp1_dates.add(ldn_date.strftime("%Y-%m-%d"))

    kept = []
    skipped = 0
    for t in ldn_trades:
        if t.exit_type == EXIT_NO_FILL:
            kept.append(t)
            continue
        if t.date in asia_tp1_dates:
            skipped += 1
            continue
        kept.append(t)

    total_filled = sum(1 for t in ldn_trades if t.exit_type != EXIT_NO_FILL)
    print(f"    G5 gate: kept {total_filled - skipped}/{total_filled} "
          f"(skipped {skipped} where Asia hit TP1)")
    return kept


# ── Trade → dict conversion ────────────────────────────────────────────

def trade_to_dict(t: TradeResult, leg_name: str, qty_mult: float = 1.0) -> dict:
    r = t.r_multiple * qty_mult
    pnl = t.pnl_usd * qty_mult
    return {
        "date": t.date,
        "session": t.session,
        "leg": leg_name,
        "direction": "long" if t.direction == 1 else "short",
        "entry_price": round(t.entry_price, 4),
        "stop_price": round(t.stop_price, 4),
        "tp1_price": round(t.tp1_price, 4),
        "tp2_price": round(t.tp2_price, 4),
        "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
        "pnl_usd": round(pnl, 2),
        "pnl_points": round(t.pnl_points, 4) if hasattr(t, "pnl_points") else 0,
        "r_multiple": round(r, 3),
        "qty": t.qty * qty_mult,
        "gap_size": round(t.gap_size, 4),
        "risk_points": round(t.risk_points, 4),
        "fill_time": getattr(t, "fill_time", ""),
        "exit_time": getattr(t, "exit_time", ""),
    }


# ── Combined metrics from trade dicts ──────────────────────────────────

def compute_combined_metrics(combined_filled, risk_label):
    r_arr = np.array([t["r_multiple"] for t in combined_filled], dtype=float)
    pnl_arr = np.array([t.get("pnl_usd", 0) for t in combined_filled], dtype=float)
    r_eq = np.cumsum(r_arr)
    r_pk = np.maximum.accumulate(r_eq)
    r_dd = r_eq - r_pk

    total_trades = len(combined_filled)
    wins = int(np.sum(r_arr > 0))
    losses = total_trades - wins
    total_r = float(r_eq[-1]) if len(r_eq) > 0 else 0
    total_pnl = float(np.sum(pnl_arr))
    max_dd_r = float(np.min(r_dd)) if len(r_dd) > 0 else 0
    win_rate = wins / total_trades if total_trades > 0 else 0
    avg_r = float(np.mean(r_arr)) if len(r_arr) > 0 else 0

    win_r = r_arr[r_arr > 0]
    loss_r = r_arr[r_arr <= 0]
    avg_win = float(np.mean(win_r)) if len(win_r) > 0 else 0
    avg_loss = float(np.mean(loss_r)) if len(loss_r) > 0 else 0

    gross_profit = float(np.sum(win_r)) if len(win_r) > 0 else 0
    gross_loss = float(np.abs(np.sum(loss_r))) if len(loss_r) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe (annualized from daily R)
    r_by_date = {}
    for t in combined_filled:
        d = t["date"]
        r_by_date[d] = r_by_date.get(d, 0) + t["r_multiple"]
    daily_r = np.array(list(r_by_date.values()))
    sharpe = float(np.mean(daily_r) / np.std(daily_r) * np.sqrt(252)) if np.std(daily_r) > 0 else 0

    neg_daily = daily_r[daily_r < 0]
    downside_std = float(np.std(neg_daily)) if len(neg_daily) > 0 else 0
    sortino = float(np.mean(daily_r) / downside_std * np.sqrt(252)) if downside_std > 0 else 0

    n_years = len(set(r_by_date.keys())) / 252 if r_by_date else 1
    annual_r = total_r / n_years if n_years > 0 else 0
    calmar = abs(annual_r / max_dd_r) if max_dd_r != 0 else float("inf")

    r_by_year = {}
    for t in combined_filled:
        yr = t["date"][:4]
        r_by_year[yr] = r_by_year.get(yr, 0) + t["r_multiple"]

    max_cw = max_cl = cw = cl = 0
    for r in r_arr:
        if r > 0:
            cw += 1; cl = 0; max_cw = max(max_cw, cw)
        else:
            cl += 1; cw = 0; max_cl = max(max_cl, cl)

    return {
        "total_trades": total_trades,
        "win_count": wins,
        "loss_count": losses,
        "win_rate": win_rate,
        "total_pnl_usd": total_pnl,
        "avg_pnl_usd": total_pnl / total_trades if total_trades > 0 else 0,
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "total_r": total_r,
        "avg_r": avg_r,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_drawdown_r": max_dd_r,
        "max_drawdown_usd": float(np.min(np.cumsum(pnl_arr) - np.maximum.accumulate(np.cumsum(pnl_arr)))),
        "max_consecutive_wins": max_cw,
        "max_consecutive_losses": max_cl,
        "r_by_year": dict(sorted(r_by_year.items())),
        "risk_usd": risk_label,
    }


# ── Main ────────────────────────────────────────────────────────────────

def run_portfolio(config_name, exec_cfg, data_cache, start, end, risk_override=None):
    print("=" * 70)
    print(f"{config_name} EXECUTION PORTFOLIO")
    print("=" * 70)

    all_trade_dicts = []
    leg_summaries = []
    asia_leg_trades = {}  # for G5 gate

    for leg_name, leg_fn, risk_usd in exec_cfg["legs"]:
        if risk_override is not None:
            risk_usd = risk_override
        config, symbol, excluded_dow = leg_fn(risk_usd)
        df = data_cache[symbol]["5m"]
        df_1m = data_cache[symbol].get("1m")
        qty_mult = exec_cfg["qty_multipliers"].get(leg_name, 1.0)

        label = f"  {leg_name} ({symbol}, ${risk_usd}"
        if qty_mult > 1:
            label += f", {qty_mult:.0f}x"
        label += ")"
        print(label)

        t0 = time.time()
        trades = run_backtest(df, config, start_date=start, df_1m=df_1m)

        # DOW exclusion
        if excluded_dow:
            dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
            excl_str = "+".join(dow_names[d] for d in sorted(excluded_dow))
            trades = apply_dow_filter(trades, excluded_dow)
            print(f"    DOW excl: {excl_str}")

        # Store Asia trades for G5 gate
        if "Asia" in leg_name and "LSI" not in leg_name:
            asia_leg_trades[leg_name] = list(trades)

        # G5 gate for NQ_LDN
        if leg_name == "NQ_LDN" and exec_cfg.get("g5_gate"):
            asia_lists = [v for k, v in asia_leg_trades.items()]
            trades = apply_g5_gate(trades, asia_lists)

        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        elapsed = time.time() - t0

        # Convert to dicts with qty_mult applied
        trade_dicts = [trade_to_dict(t, leg_name, qty_mult) for t in trades]
        filled_dicts = [d for d in trade_dicts if d["exit_type"] != "no_fill"]

        # Leg metrics
        if filled_dicts:
            r_sum = sum(d["r_multiple"] for d in filled_dicts)
            wr = sum(1 for d in filled_dicts if d["r_multiple"] > 0) / len(filled_dicts)
        else:
            r_sum = 0
            wr = 0

        print(f"    {len(filled)} fills, WR={wr:.1%}, Net R={r_sum:.1f} [{elapsed:.1f}s]")

        leg_summaries.append({
            "name": leg_name,
            "symbol": symbol,
            "risk_usd": risk_usd,
            "qty_mult": qty_mult,
            "trades": len(filled),
            "win_rate": wr,
            "net_r": r_sum,
        })

        all_trade_dicts.extend(trade_dicts)

    # Sort by date
    all_trade_dicts.sort(key=lambda t: t["date"])
    combined_filled = [t for t in all_trade_dicts if t["exit_type"] != "no_fill"]

    # Combined metrics
    summary = compute_combined_metrics(combined_filled, config_name)

    # Print summary
    print()
    print(f"  {'Leg':<18} {'$Risk':>6} {'Mult':>5} {'Trades':>7} {'WR':>6} {'Net R':>8}")
    print(f"  {'-'*18} {'-'*6} {'-'*5} {'-'*7} {'-'*6} {'-'*8}")
    for ls in leg_summaries:
        mult_str = f"{ls['qty_mult']:.0f}x" if ls["qty_mult"] > 1 else ""
        print(f"  {ls['name']:<18} ${ls['risk_usd']:>5} {mult_str:>5} {ls['trades']:>7} "
              f"{ls['win_rate']:>5.1%} {ls['net_r']:>+8.1f}")
    print(f"  {'COMBINED':<18} {'':>6} {'':>5} {summary['total_trades']:>7} "
          f"{summary['win_rate']:>5.1%} {summary['total_r']:>+8.1f}")

    print(f"\n  Sharpe={summary['sharpe_ratio']:.3f}  Calmar={summary['calmar_ratio']:.2f}  "
          f"PF={summary['profit_factor']:.2f}  Max DD={summary['max_drawdown_r']:.1f}R")

    if summary["r_by_year"]:
        print("\n  R by year:")
        for yr, r in summary["r_by_year"].items():
            print(f"    {yr}: {r:>+8.1f}R")

    # Equity curve — store actual USD PnL so the frontend can display
    # both dollar equity and R (by dividing by risk_usd).
    equity_curve = []
    cum_pnl = 0.0
    for t in combined_filled:
        cum_pnl += t["pnl_usd"]
        equity_curve.append({
            "date": t["date"],
            "pnl_cumulative": round(cum_pnl, 2),
            "pnl_per_trade": round(t["pnl_usd"], 2),
        })

    # Build notes
    leg_notes = []
    for ls in leg_summaries:
        mult_str = f" {ls['qty_mult']:.0f}x" if ls["qty_mult"] > 1 else ""
        leg_notes.append(f"{ls['name']} ({ls['symbol']}, ${ls['risk_usd']}{mult_str})")
    notes = f"{config_name} execution portfolio — {len(leg_summaries)} legs.\n\n" + "\n".join(leg_notes)

    # Save
    risk_label_str = f" ${int(risk_override)}" if risk_override else ""
    result_dict = {
        "name": f"EXEC {config_name} Portfolio 10yr{risk_label_str}",
        "notes": notes,
        "config": {
            "legs": [ls["name"] for ls in leg_summaries],
            "strategy": "continuation+lsi",
            "direction_filter": "long",
            "risk_usd": risk_override or config_name,
            "instrument": "MULTI",
        },
        "summary": summary,
        "equity_curve": equity_curve,
        "trades": all_trade_dicts,
    }

    result_id = save_backtest_result(result_dict)
    print(f"\n  Saved: {result_id}")
    print()

    return result_id


def main():
    parser = argparse.ArgumentParser(description="FAST/SLOW execution portfolio backtests")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2026-01-01")
    parser.add_argument("--config", default=None, choices=["FAST", "SLOW"],
                        help="Run only one config (default: both)")
    parser.add_argument("--no-1m", action="store_true", help="Skip loading 1m data")
    parser.add_argument("--risk", type=float, default=None,
                        help="Override risk_usd for ALL legs (e.g. --risk 5000)")
    args = parser.parse_args()

    configs_to_run = [args.config] if args.config else ["FAST", "SLOW"]

    # Figure out which symbols we need
    needed_symbols = set()
    for cfg_name in configs_to_run:
        for _, leg_fn, risk in EXEC_CONFIGS[cfg_name]["legs"]:
            _, symbol, _ = leg_fn(1)  # dummy risk to get symbol
            needed_symbols.add(symbol)

    # Load data
    print("Loading data...")
    data_cache = {}
    for symbol in sorted(needed_symbols):
        data_file = DATA_DIR / f"{symbol}_5m.parquet"
        if not data_file.exists():
            data_file = DATA_DIR / f"{symbol}_5m.csv"

        t0 = time.time()
        df = load_5m_data(str(data_file), start=args.start, end=args.end)
        data_cache[symbol] = {"5m": df}
        print(f"  {symbol} 5m: {len(df):,} bars [{time.time() - t0:.1f}s]")

        if not args.no_1m:
            try:
                t0 = time.time()
                df_1m = load_1m_for_5m(str(data_file), start=args.start, end=args.end)
                data_cache[symbol]["1m"] = df_1m
                print(f"  {symbol} 1m: {len(df_1m):,} bars [{time.time() - t0:.1f}s]")
            except FileNotFoundError:
                print(f"  {symbol} 1m: not found (5m only)")

    print()

    # Run each config
    for cfg_name in configs_to_run:
        run_portfolio(cfg_name, EXEC_CONFIGS[cfg_name], data_cache, args.start, args.end,
                      risk_override=args.risk)


if __name__ == "__main__":
    main()
