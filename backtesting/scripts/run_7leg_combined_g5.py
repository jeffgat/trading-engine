#!/usr/bin/env python3
"""Run the 7-leg combined longs portfolio backtest with G5 gate.

Legs:
  1. NQ NY    — rr=3.5, stop=7.0% ATR-12, tp1=0.4, ORB=20m, entry<=12:00, excl-Fri
  2. NQ Asia  — rr=6.0, stop=100% ORB, tp1=0.3, ORB=15m, entry<=22:30, excl-Tue
  3. GC NY    — rr=9.0, stop=4.5% ATR-7, tp1=0.35, ORB=8m, entry<=12:00, excl-Fri+FOMC, ICF on
  4. ES NY    — rr=5.0, stop=5.0% ATR-7, tp1=0.2, ORB=15m, entry<=13:00, dual floor 3.0/3.0, excl-Thu
  5. ES Asia  — rr=1.5, stop=125% ORB, tp1=0.7, ORB=15m, entry<=03:00, dual floor 3.0/3.0
  6. NQ LDN   — rr=6.0, stop=1.5% ATR-10, tp1=0.7, ORB=30m, entry<=08:25, G5 gated
  7. NQ NY LSI — fvg_limit v2 2x (pulled from DB — LSI strategy not in engine)

G5 gate: Skip NQ LDN on days when either Asia leg (NQ Asia or ES Asia) hit TP1
the prior night. "TP1 hit" = exit_type in {tp1_tp2, tp1_be, tp1_eod}.

Usage:
    python scripts/run_7leg_combined_g5.py
    python scripts/run_7leg_combined_g5.py --start 2016-01-01 --end 2026-03-01
    python scripts/run_7leg_combined_g5.py --mc-sims 5000
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import (
    run_backtest, EXIT_NO_FILL, EXIT_NAMES,
    EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import save_backtest_result
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.analysis.gates import apply_dow_filter

# ── Data directory ──────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parents[3] / ".." / "backtests" / "python" / "data" / "raw"

# ── Remote DB API for pulling LSI trades ────────────────────────────────
DB_API = "http://143.110.148.234:8100"
LSI_RESULT_ID = "bt-nq-ny-lsi-fvg-limit-v2-long-2016-2026-fi-5302c0"

# ── Half-days ───────────────────────────────────────────────────────────
HALF_DAYS = (
    "20250703", "20251128", "20251224", "20250109", "20260119",
    "20240703", "20241129", "20241224",
)

TP1_EXIT_TYPES = {EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD}


# ── Leg definitions ─────────────────────────────────────────────────────

def _leg1_nq_ny():
    """Leg 1: NQ NY — rr=3.5, stop=7.0% ATR-12, tp1=0.4, ORB=20m, excl-Fri."""
    inst = get_instrument("NQ")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.4, atr_length=12,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg1 NQ NY",
    ), inst, {4}  # exclude Friday


def _leg2_nq_asia():
    """Leg 2: NQ Asia — rr=6.0, stop=100% ORB, tp1=0.3, ORB=15m, excl-Tue."""
    inst = get_instrument("NQ")
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=0.0,
        min_gap_atr_pct=0.0,
        stop_orb_pct=100.0,
        min_gap_orb_pct=10.0,
    )
    return StrategyConfig(
        rr=6.0, tp1_ratio=0.3, atr_length=5,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg2 NQ Asia",
    ), inst, {1}  # exclude Tuesday


def _leg3_gc_ny():
    """Leg 3: GC NY — rr=9.0, stop=4.5% ATR-7, tp1=0.35, ORB=8m, excl-Fri+FOMC, ICF on."""
    inst = get_instrument("GC")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:38",
        entry_start="09:38", entry_end="12:00",
        flat_start="13:30", flat_end="16:00",
        stop_atr_pct=4.5,
        min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        rr=9.0, tp1_ratio=0.35, atr_length=7,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        impulse_close_filter=True,
        half_days=HALF_DAYS,
        excluded_dates=FOMC_DATES,
        name="Leg3 GC NY",
    ), inst, {4}  # exclude Friday


def _leg4_es_ny():
    """Leg 4: ES NY — rr=5.0, stop=5.0% ATR-7, tp1=0.2, ORB=15m, dual floor, excl-Thu."""
    inst = get_instrument("ES")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.25,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, atr_length=7,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg4 ES NY",
    ), inst, {3}  # exclude Thursday


def _leg5_es_asia():
    """Leg 5: ES Asia — rr=1.5, stop=125% ORB, tp1=0.7, ORB=15m, dual floor."""
    inst = get_instrument("ES")
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_atr_pct=0.0,
        min_gap_atr_pct=0.0,
        stop_orb_pct=125.0,
        min_gap_orb_pct=0.0,  # uses ATR-based gap filter
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    # ES Asia uses min_gap_atr_pct=0.5 with ATR=14
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_atr_pct=0.0,
        stop_orb_pct=125.0,
        min_gap_atr_pct=0.5,
        min_gap_orb_pct=0.0,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    return StrategyConfig(
        rr=1.5, tp1_ratio=0.7, atr_length=14,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg5 ES Asia",
    ), inst, set()  # no DOW exclusion


def _leg6_nq_ldn():
    """Leg 6: NQ LDN — rr=6.0, stop=1.5% ATR-10, tp1=0.7, ORB=30m. G5 gated post-trade."""
    inst = get_instrument("NQ")
    session = SessionConfig(
        name="LDN",
        orb_start="03:00", orb_end="03:30",
        entry_start="03:30", entry_end="08:25",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=1.5,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=6.0, tp1_ratio=0.7, atr_length=10,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg6 NQ LDN",
    ), inst, set()  # no DOW exclusion; G5 gate applied separately


# ── Leg list ────────────────────────────────────────────────────────────

LEGS = [
    ("Leg 1: NQ NY",    _leg1_nq_ny,   "NQ"),
    ("Leg 2: NQ Asia",  _leg2_nq_asia,  "NQ"),
    ("Leg 3: GC NY",    _leg3_gc_ny,   "GC"),
    ("Leg 4: ES NY",    _leg4_es_ny,   "ES"),
    ("Leg 5: ES Asia",  _leg5_es_asia,  "ES"),
    ("Leg 6: NQ LDN",   _leg6_nq_ldn,  "NQ"),
]


# ── G5 Gate ─────────────────────────────────────────────────────────────

def apply_g5_gate(ldn_trades, nq_asia_trades, es_asia_trades):
    """G5 gate: Skip NQ LDN trades on days when either Asia leg hit TP1 the prior night.

    Asia sessions run the evening before the LDN session date. So for a LDN
    trade on date D, we check if NQ Asia or ES Asia on date D-1 (or the
    matching Asia session night) hit TP1.

    Since Asia sessions run 20:00-07:00 spanning overnight, the trade date
    stored is the date the session *started* (the evening). The LDN session
    on the *next calendar day* should be gated.
    """
    # Build a set of dates where any Asia leg hit TP1
    asia_tp1_dates = set()
    for t in nq_asia_trades + es_asia_trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        if t.exit_type in TP1_EXIT_TYPES:
            # Asia trade date is the evening start date.
            # LDN runs the next day. We need to map Asia date -> next trading day.
            asia_date = datetime.strptime(t.date, "%Y-%m-%d")
            # Add 1 day to get the LDN date that should be skipped
            from datetime import timedelta
            ldn_date = asia_date + timedelta(days=1)
            # Skip weekends: if Asia is Friday night, LDN is Monday
            while ldn_date.weekday() >= 5:  # Saturday=5, Sunday=6
                ldn_date += timedelta(days=1)
            asia_tp1_dates.add(ldn_date.strftime("%Y-%m-%d"))

    # Filter LDN trades
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
    print(f"  G5 gate: kept {total_filled - skipped}/{total_filled} LDN trades "
          f"(skipped {skipped} where Asia hit TP1)")

    return kept


# ── Pull LSI trades from DB ─────────────────────────────────────────────

def pull_lsi_trades_from_db(result_id, start_date=None, end_date=None):
    """Pull Leg 7 (NQ NY LSI) trades from the remote DB.

    The LSI strategy is not implemented in the backtesting engine, so we
    reuse the stored trades. These trades have 2x position sizing already
    applied in their r_multiple and pnl_usd values.
    """
    url = f"{DB_API}/api/backtests/{result_id}"
    print(f"  Fetching LSI trades from DB: {result_id}")

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    result = data.get("result", data)
    trades_raw = result.get("trades", [])
    if isinstance(trades_raw, str):
        trades_raw = json.loads(trades_raw)

    # Filter by date range if specified
    filtered = []
    for t in trades_raw:
        trade_date = t.get("date", "")
        if start_date and trade_date < start_date:
            continue
        if end_date and trade_date > end_date:
            continue
        filtered.append(t)

    filled = [t for t in filtered if t.get("exit_type") != "no_fill"]
    print(f"  Loaded {len(filled)} filled LSI trades ({len(filtered)} total)")

    return filtered


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="7-leg combined longs with G5 gate")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--mc-sims", type=int, default=2000, help="Monte Carlo simulations")
    parser.add_argument("--mc-seed", type=int, default=42, help="MC random seed")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    parser.add_argument("--name", default="NQ+GC+ES Combined Longs (7-Leg Gated G5 + NQ NY LSI 2x)",
                        help="Experiment name")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR

    # ── Load data ──────────────────────────────────────────────────────
    print("=" * 70)
    print("7-LEG COMBINED LONGS PORTFOLIO — G5 GATED + LSI 2x")
    print("=" * 70)
    print()

    data_cache = {}
    for symbol in ("NQ", "ES", "GC"):
        data_file = data_dir / f"{symbol}_5m.parquet"
        if not data_file.exists():
            data_file = data_dir / f"{symbol}_5m.csv"
        if not data_file.exists():
            print(f"ERROR: Data file not found for {symbol} in {data_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading {symbol} data: {data_file.name}")
        t0 = time.time()
        df = load_5m_data(str(data_file), start=args.start, end=args.end)
        data_cache[symbol] = df
        print(f"  {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    print()

    # ── Run Legs 1-6 ───────────────────────────────────────────────────
    all_trades = []
    leg_results = []
    nq_asia_trades = []
    es_asia_trades = []

    for leg_name, leg_fn, symbol in LEGS:
        config, inst, excluded_dow = leg_fn()
        df = data_cache[symbol]

        print("-" * 70)
        print(f"{leg_name}  ({symbol}, rr={config.rr}, tp1={config.tp1_ratio}, "
              f"stop={config.sessions[0].stop_atr_pct}% ATR"
              f"{f', stop_orb={config.sessions[0].stop_orb_pct}%' if config.sessions[0].stop_orb_pct > 0 else ''})")

        t0 = time.time()
        trades = run_backtest(df, config, start_date=args.start)

        # Apply DOW exclusion
        if excluded_dow:
            dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
            excluded_str = ", ".join(dow_names[d] for d in excluded_dow)
            trades = apply_dow_filter(trades, excluded_dow)
            print(f"  DOW exclusion: {excluded_str}")

        # Store Asia trades for G5 gate
        if "NQ Asia" in leg_name:
            nq_asia_trades = list(trades)
        elif "ES Asia" in leg_name:
            es_asia_trades = list(trades)

        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        elapsed = time.time() - t0
        print(f"  {len(filled)} filled trades [{elapsed:.1f}s]")

        metrics = compute_metrics(trades)
        _print_leg_summary(metrics)

        leg_results.append({
            "name": leg_name,
            "symbol": symbol,
            "config": config,
            "trades": trades,
            "filled": filled,
            "metrics": metrics,
        })

        # Apply G5 gate to NQ LDN (Leg 6)
        if "NQ LDN" in leg_name:
            trades = apply_g5_gate(trades, nq_asia_trades, es_asia_trades)
            filled_after_gate = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            metrics_gated = compute_metrics(trades)
            print(f"  After G5 gate: {len(filled_after_gate)} filled trades")
            _print_leg_summary(metrics_gated)
            leg_results[-1]["trades"] = trades
            leg_results[-1]["filled"] = filled_after_gate
            leg_results[-1]["metrics"] = metrics_gated

        all_trades.extend(leg_results[-1]["trades"])

    # ── Leg 7: Pull LSI trades from DB ─────────────────────────────────
    print("-" * 70)
    print("Leg 7: NQ NY LSI fvg_limit v2 2x  (from DB)")

    lsi_trades_raw = pull_lsi_trades_from_db(
        LSI_RESULT_ID,
        start_date=args.start,
        end_date=args.end,
    )
    lsi_filled = [t for t in lsi_trades_raw if t.get("exit_type") != "no_fill"]

    # Compute LSI metrics
    lsi_r = sum(t.get("r_multiple", 0) for t in lsi_filled)
    lsi_wins = sum(1 for t in lsi_filled if t.get("r_multiple", 0) > 0)
    lsi_wr = lsi_wins / len(lsi_filled) if lsi_filled else 0
    print(f"  {len(lsi_filled)} filled trades, WR={lsi_wr:.1%}, Net R={lsi_r:.1f}")

    leg_results.append({
        "name": "Leg 7: NQ NY LSI 2x",
        "symbol": "NQ",
        "config": None,
        "trades": lsi_trades_raw,
        "filled": lsi_filled,
        "metrics": {"total_trades": len(lsi_filled), "win_rate": lsi_wr, "total_r": lsi_r},
    })

    # ── Merge all trades ───────────────────────────────────────────────
    # Convert engine TradeResult objects to dicts for unified handling
    engine_trades_dicts = []
    for t in all_trades:
        engine_trades_dicts.append({
            "date": t.date,
            "session": t.session,
            "direction": "long" if t.direction == 1 else "short",
            "entry_price": round(t.entry_price, 4),
            "stop_price": round(t.stop_price, 4),
            "tp1_price": round(t.tp1_price, 4),
            "tp2_price": round(t.tp2_price, 4),
            "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
            "pnl_usd": round(t.pnl_usd, 2),
            "pnl_points": round(t.pnl_points, 4) if hasattr(t, "pnl_points") else 0,
            "r_multiple": round(t.r_multiple, 3),
            "qty": t.qty,
            "gap_size": round(t.gap_size, 4),
            "risk_points": round(t.risk_points, 4),
            "fill_time": getattr(t, "fill_time", ""),
            "exit_time": getattr(t, "exit_time", ""),
        })

    # LSI trades are already dicts from the DB
    combined_trades = engine_trades_dicts + lsi_trades_raw
    combined_trades.sort(key=lambda t: t["date"])

    # Remove no-fills for metrics
    combined_filled = [t for t in combined_trades if t.get("exit_type") != "no_fill"]

    print()
    print("=" * 70)
    print("COMBINED PORTFOLIO (7 Legs)")
    print("=" * 70)

    # Compute combined metrics from trade dicts
    r_arr = np.array([t["r_multiple"] for t in combined_filled], dtype=float)
    pnl_arr = np.array([t.get("pnl_usd", 0) for t in combined_filled], dtype=float)
    r_eq = np.cumsum(r_arr)
    r_pk = np.maximum.accumulate(r_eq)
    r_dd = r_eq - r_pk

    total_trades = len(combined_filled)
    wins = sum(1 for r in r_arr if r > 0)
    losses = sum(1 for r in r_arr if r <= 0)
    total_r = float(r_eq[-1]) if len(r_eq) > 0 else 0
    total_pnl = float(np.sum(pnl_arr))
    max_dd_r = float(np.min(r_dd)) if len(r_dd) > 0 else 0
    win_rate = wins / total_trades if total_trades > 0 else 0
    avg_r = float(np.mean(r_arr)) if len(r_arr) > 0 else 0

    # Win/loss averages
    win_r = r_arr[r_arr > 0]
    loss_r = r_arr[r_arr <= 0]
    avg_win = float(np.mean(win_r)) if len(win_r) > 0 else 0
    avg_loss = float(np.mean(loss_r)) if len(loss_r) > 0 else 0

    # Profit factor
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

    # Sortino
    neg_daily = daily_r[daily_r < 0]
    downside_std = float(np.std(neg_daily)) if len(neg_daily) > 0 else 0
    sortino = float(np.mean(daily_r) / downside_std * np.sqrt(252)) if downside_std > 0 else 0

    # Calmar (annualized return / max drawdown)
    n_years = len(set(r_by_date.keys())) / 252 if r_by_date else 1
    annual_r = total_r / n_years if n_years > 0 else 0
    calmar = abs(annual_r / max_dd_r) if max_dd_r != 0 else float("inf")

    # R by year
    r_by_year = {}
    for t in combined_filled:
        yr = t["date"][:4]
        r_by_year[yr] = r_by_year.get(yr, 0) + t["r_multiple"]

    # Max consecutive
    max_consec_wins = max_consec_losses = consec_w = consec_l = 0
    for r in r_arr:
        if r > 0:
            consec_w += 1
            consec_l = 0
            max_consec_wins = max(max_consec_wins, consec_w)
        else:
            consec_l += 1
            consec_w = 0
            max_consec_losses = max(max_consec_losses, consec_l)

    # No-fill count
    no_fills = sum(1 for t in combined_trades if t.get("exit_type") == "no_fill")

    summary = {
        "total_signals": len(combined_trades),
        "total_trades": total_trades,
        "no_fills": no_fills,
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
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "r_by_year": dict(sorted(r_by_year.items())),
        "risk_usd": 5000.0,
    }

    print(f"\n  Trades:          {total_trades}")
    print(f"  Win rate:        {win_rate:.1%}")
    print(f"  Total R:         {total_r:.1f}")
    print(f"  Avg R:           {avg_r:.3f}")
    print(f"  Profit Factor:   {profit_factor:.2f}")
    print(f"  Sharpe:          {sharpe:.3f}")
    print(f"  Sortino:         {sortino:.3f}")
    print(f"  Calmar:          {calmar:.2f}")
    print(f"  Max DD:          {max_dd_r:.1f}R")
    print(f"  Max Consec Wins: {max_consec_wins}")
    print(f"  Max Consec Loss: {max_consec_losses}")

    # Per-leg contribution
    print("\n  Per-leg contribution:")
    print(f"  {'Leg':<25} {'Trades':>7} {'WR':>7} {'Net R':>8}")
    print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*8}")
    for lr in leg_results:
        m = lr["metrics"]
        n = m.get("total_trades", len(lr.get("filled", [])))
        wr = m.get("win_rate", 0)
        tr = m.get("total_r", 0)
        print(f"  {lr['name']:<25} {n:>7} {wr:>6.1%} {tr:>8.1f}")
    print(f"  {'COMBINED':<25} {total_trades:>7} {win_rate:>6.1%} {total_r:>8.1f}")

    # R by year
    if r_by_year:
        print("\n  R by year:")
        for year, r in sorted(r_by_year.items()):
            print(f"    {year}: {r:>+8.1f}R")

    # ── Equity curve ───────────────────────────────────────────────────
    equity_curve = []
    cumulative = 0.0
    for t in combined_filled:
        cumulative += t.get("pnl_usd", 0)
        equity_curve.append({
            "date": t["date"],
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.get("pnl_usd", 0), 2),
        })

    # ── Monte Carlo ────────────────────────────────────────────────────
    if args.mc_sims > 0:
        print()
        print("=" * 70)
        print(f"MONTE CARLO — BOOTSTRAP ({args.mc_sims:,} sims)")
        print("=" * 70)

        # Build TradeResult-compatible objects for MC
        from orb_backtest.engine.simulator import TradeResult
        mc_trades = []
        for t in combined_filled:
            mc_trades.append(TradeResult(
                date=t["date"],
                session=t.get("session", "NY"),
                direction=1 if t.get("direction", "long") == "long" else -1,
                signal_bar=0,
                fill_bar=0,
                entry_price=t.get("entry_price", 0),
                stop_price=t.get("stop_price", 0),
                tp1_price=t.get("tp1_price", 0),
                tp2_price=t.get("tp2_price", 0),
                exit_type=1,  # placeholder
                exit_bar=0,
                pnl_points=t.get("pnl_points", 0),
                pnl_usd=t.get("pnl_usd", 0),
                r_multiple=t["r_multiple"],
                qty=t.get("qty", 1),
                half_qty=t.get("qty", 1) / 2,
                gap_size=t.get("gap_size", 0),
                risk_points=t.get("risk_points", 0),
                fill_time="",
                exit_time="",
            ))

        mc_config = MonteCarloConfig(
            n_simulations=args.mc_sims,
            method="bootstrap",
            seed=args.mc_seed,
        )

        t0 = time.time()
        mc_result = run_monte_carlo(mc_trades, mc_config, ruin_threshold=-10.0)
        print(f"  Completed in {time.time() - t0:.1f}s")

        p = mc_result.final_pnl_percentiles
        print(f"\n  Trades: {mc_result.n_trades}")
        print(f"  Final PnL (R):")
        print(f"    5th:  {p['p5']:>8.1f}R    50th: {p['p50']:>8.1f}R    95th: {p['p95']:>8.1f}R")
        print(f"    Actual: {mc_result.actual_final_pnl:>8.1f}R")

        p = mc_result.max_dd_percentiles
        print(f"  Max Drawdown (R):")
        print(f"    5th:  {p['p5']:>8.1f}R    50th: {p['p50']:>8.1f}R    95th: {p['p95']:>8.1f}R")
        print(f"    Actual: {mc_result.actual_max_drawdown:>8.1f}R")

        print(f"  Ruin probability: {mc_result.ruin_probability:.1%}  (P(DD < {mc_result.ruin_threshold}R))")

    # ── Build notes ────────────────────────────────────────────────────
    notes = (
        "7-leg portfolio: 6-Leg Gated G5 baseline + NQ NY LSI fvg_limit v2 2x.\n\n"
        "G5 gate: NQ LDN skipped on days when either Asia leg (NQ Asia or ES Asia) "
        "hit TP1 the prior night.\n\n"
        "Leg 1 — NQ NY Cont Long R11: stop=7.0%, rr=3.5, gap=2.5%, tp1=0.4, "
        "ORB=20m (09:30-09:50), entry<=12:00, flat=15:30, ATR=12, ICF=OFF, excl-Fri.\n\n"
        "Leg 2 — NQ Asia Cont Long R9: stop_orb=100%, rr=6.0, gap_orb=10%, tp1=0.3, "
        "ORB=15m (20:00-20:15), entry<=22:30, flat=04:00, ATR=5, ICF=OFF, excl-Tue.\n\n"
        "Leg 3 — GC NY Cont Long R3: stop=4.5%, rr=9.0, gap=3.0%, tp1=0.35, "
        "ORB=8m (09:30-09:38), entry<=12:00, flat=13:30, ATR=7, ICF=ON, excl-Fri+FOMC.\n\n"
        "Leg 4 — ES NY Cont Long Final: stop=5.0%, rr=5.0, gap=0.25%, tp1=0.2, "
        "ORB=15m (09:30-09:45), entry<=13:00, flat=15:50, ATR=7, ICF=OFF, dual floor 3.0/3.0, excl-Thu.\n\n"
        "Leg 5 — ES Asia Cont Long Final: stop_orb=125%, rr=1.5, gap=0.5%, tp1=0.7, "
        "ORB=15m (20:00-20:15), entry<=03:00, flat=07:00, ATR=14, ICF=OFF, dual floor 3.0/3.0.\n\n"
        "Leg 6 — NQ LDN Cont Long Final (G5 gated): stop=1.5%, rr=6.0, gap=1.0%, tp1=0.7, "
        "ORB=30m (03:00-03:30), entry<=08:25, flat=08:20, ATR=10, ICF=OFF. G5 gate applied.\n\n"
        "Leg 7 — NQ NY LSI fvg_limit v2 2x: rr=3.0, gap=5% ATR, tp1=0.3, "
        "ORB=5m (09:30-09:35), entry<=15:30, flat=15:50, ATR=10, "
        "DOW=Mon/Tue/Fri, 2x position size. Trades from DB."
    )

    # ── Save result ────────────────────────────────────────────────────
    result_dict = {
        "name": args.name,
        "notes": notes,
        "config": {
            "legs": [lr["name"] for lr in leg_results],
            "strategy": "continuation",
            "direction_filter": "long",
            "risk_usd": 5000.0,
            "instrument": "NQ",
        },
        "summary": summary,
        "equity_curve": equity_curve,
        "trades": combined_trades,
    }

    result_id = save_backtest_result(result_dict)
    print(f"\n  Results saved: {result_id}")
    print("  View in dashboard → Backtests tab")
    print("=" * 70)


# ── Output helpers ───────────────────────────────────────────────────────

def _print_leg_summary(m: dict):
    print(f"  WR={m['win_rate']:.1%}  Net R={m['total_r']:.1f}  "
          f"Sharpe={m['sharpe_ratio']:.3f}  Calmar={m.get('calmar_ratio', 0):.2f}  "
          f"Max DD={m['max_drawdown_r']:.1f}R  PF={m['profit_factor']:.2f}")


if __name__ == "__main__":
    main()
