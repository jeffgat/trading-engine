#!/usr/bin/env python3
"""NQ Asia ORB dual-model optimization: Aggressive (fast) vs Wide (slow).

Two distinct pockets of success for NQ Asia continuation:
  1. Aggressive — tight stops, high R:R, ~43% WR, ~0.16R/trade
  2. Wide — wide stops, low R:R, ~78% WR, ~0.05R/trade

Steps:
  1. Pre-sweep: determine best ORB window (10m vs 15m) and ATR length (5 vs 14) per model
  2. Full grid sweep for each model (~2000-2500 combos each)
  3. Rank by Sharpe, Net R, DD, prop viability
  4. Save top configs to DB as PRE-PIPELINE
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def no_thursday_gate(trades):
    """Filter out Thursday trades (dayofweek == 3)."""
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def gated_metrics(trades):
    """Apply no-Thursday gate, return (metrics, gated_trades) or (None, []) if too few fills."""
    gated = no_thursday_gate(trades)
    filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 10:
        return None, gated
    return compute_metrics(gated), gated


def build_asia_session(orb_end, stop, gap, maxgap):
    """Build an Asia session config with given params."""
    return replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end=orb_end,
        entry_start=orb_end,
        entry_end="23:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=gap,
        max_gap_atr_pct=maxgap,
        max_gap_points=0.0,  # disable points-based filter; ATR only
    )


def build_config(orb_end, atr_length, stop, gap, maxgap, rr, tp1):
    """Build a full StrategyConfig for NQ Asia."""
    asia = build_asia_session(orb_end, stop, gap, maxgap)
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=rr,
        tp1_ratio=tp1,
        use_bar_magnifier=True,
        atr_length=atr_length,
    )


def extract_row(config, metrics):
    """Extract flat dict from config + metrics for ranking tables."""
    sess = config.sessions[0]
    return {
        "stop": sess.stop_atr_pct,
        "gap": sess.min_gap_atr_pct,
        "maxgap": sess.max_gap_atr_pct,
        "rr": config.rr,
        "tp1": config.tp1_ratio,
        "trades": metrics["total_trades"],
        "wr": metrics["win_rate"],
        "net_r": round(metrics["total_r"], 1),
        "max_dd_r": round(metrics["max_drawdown_r"], 1),
        "sharpe": round(metrics["sharpe_ratio"], 3),
        "pf": round(metrics["profit_factor"], 2),
        "calmar": round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "long": metrics.get("long_trades", 0),
        "short": metrics.get("short_trades", 0),
        "long_wr": metrics.get("long_win_rate", 0),
        "short_wr": metrics.get("short_win_rate", 0),
        "r_by_year": metrics.get("r_by_year", {}),
        "_config": config,
    }


def print_header(title):
    print(f"\n{'=' * 100}")
    print(title)
    print("=" * 100)


TABLE_HDR = (
    f"{'#':>3} | {'stop%':>5} | {'gap%':>5} | {'maxg%':>5} | {'rr':>4} | {'tp1':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'DD R':>6} | {'Sharpe':>7} | "
    f"{'PF':>5} | {'Calmar':>7} | {'R/trd':>6} | {'L':>4} | {'S':>4}"
)


def print_table(rows, label, n=5):
    """Print a ranking table."""
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(TABLE_HDR)
    print("-" * len(TABLE_HDR))
    for i, r in enumerate(rows[:n], 1):
        print(
            f"{i:>3} | {r['stop']:>5.1f} | {r['gap']:>5.2f} | {r['maxgap']:>5.1f} | "
            f"{r['rr']:>4.1f} | {r['tp1']:>4.2f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>6.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | "
            f"{r['r_per_trade']:>6.4f} | {r['long']:>4} | {r['short']:>4}"
        )


def print_year_breakdown(row):
    """Print year-by-year R and direction split for a result row."""
    print(f"    Year-by-year R:")
    for yr, r in sorted(row.get("r_by_year", {}).items()):
        print(f"      {yr}: {r:>7.1f}R")
    print(f"    Direction: {row['long']}L / {row['short']}S, "
          f"Long WR={row['long_wr']:.1%}, Short WR={row['short_wr']:.1%}")


def sweep_progress(done, total):
    if done % 200 == 0 or done == total:
        print(f"\r  {done:,}/{total:,}", end="", flush=True)


def run_model_sweep(label, df, df_1m, base_config, param_ranges, min_trades=50):
    """Run a full grid sweep and return ranked results."""
    configs = generate_param_grid(base_config, param_ranges)
    print(describe_grid(param_ranges))
    print(f"\nRunning {len(configs):,} configs with 8 workers...", flush=True)

    t0 = time.time()
    raw = run_sweep(df, configs, n_workers=8, start_date=START_DATE,
                    df_1m=df_1m, progress_fn=sweep_progress)
    print(f"\n  Completed in {time.time() - t0:.0f}s", flush=True)

    results = []
    for cfg, trades in raw:
        m, _ = gated_metrics(trades)
        if m is not None and m["total_trades"] >= min_trades:
            results.append(extract_row(cfg, m))

    print(f"  Valid results: {len(results):,} (of {len(raw):,})")

    by_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    by_net_r = sorted(results, key=lambda r: r["net_r"], reverse=True)
    by_dd = sorted(results, key=lambda r: r["max_dd_r"], reverse=True)
    prop = sorted(
        [r for r in results if r["sharpe"] >= 1.5 and r["max_dd_r"] > -10],
        key=lambda r: r["net_r"], reverse=True,
    )

    print_table(by_sharpe, f"{label}: Best Sharpe")
    print_table(by_net_r, f"{label}: Best Net R")
    print_table(by_dd, f"{label}: Lowest DD")
    print_table(prop, f"{label}: Prop Viable (Sharpe>1.5, DD>-10R)")

    if by_sharpe:
        print(f"\n  #1 Sharpe details:")
        print_year_breakdown(by_sharpe[0])

    return {
        "by_sharpe": by_sharpe,
        "by_net_r": by_net_r,
        "by_dd": by_dd,
        "prop": prop,
        "all": results,
        "n_configs": len(configs),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("NQ Asia ORB Dual-Model Optimization")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("\nLoading NQ data...", flush=True)
    t_start = time.time()
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars [{time.time() - t_start:.1f}s]")

    # ------------------------------------------------------------------
    # Model baselines
    # ------------------------------------------------------------------
    agg_base = dict(stop=4.5, gap=1.0, maxgap=11.0, rr=3.5, tp1=0.5)
    wide_base = dict(stop=5.75, gap=1.25, maxgap=11.0, rr=1.5, tp1=0.2)

    # ------------------------------------------------------------------
    # STEP 1: Session pre-sweep (ORB window × ATR length)
    # ------------------------------------------------------------------
    print_header("STEP 1: SESSION SETTINGS PRE-SWEEP")

    presweep = [
        ("10m", "20:10", 5),
        ("10m", "20:10", 14),
        ("15m", "20:15", 5),
        ("15m", "20:15", 14),
    ]

    best_sessions = {}  # model_name -> (orb_end, atr_length)

    for model_name, base in [("AGGRESSIVE", agg_base), ("WIDE", wide_base)]:
        print(f"\n  {model_name} model pre-sweep:")
        best_sharpe = -999
        best_combo = None

        for label, orb_end, atr_len in presweep:
            cfg = build_config(
                orb_end, atr_len,
                base["stop"], base["gap"], base["maxgap"],
                base["rr"], base["tp1"],
            )
            trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
            m, _ = gated_metrics(trades)
            if m is None:
                print(f"    ORB {label}, ATR {atr_len:>2}: <10 fills, skip")
                continue

            print(
                f"    ORB {label}, ATR {atr_len:>2}: "
                f"trades={m['total_trades']:>4}, WR={m['win_rate']:.1%}, "
                f"R={m['total_r']:>6.1f}, DD={m['max_drawdown_r']:>5.1f}R, "
                f"Sharpe={m['sharpe_ratio']:.3f}"
            )

            if m["sharpe_ratio"] > best_sharpe:
                best_sharpe = m["sharpe_ratio"]
                best_combo = (orb_end, atr_len)

        best_sessions[model_name] = best_combo
        print(f"  --> Best: ORB {'10m' if best_combo[0] == '20:10' else '15m'}, "
              f"ATR {best_combo[1]} (Sharpe {best_sharpe:.3f})")

    agg_orb, agg_atr = best_sessions["AGGRESSIVE"]
    wide_orb, wide_atr = best_sessions["WIDE"]

    # ------------------------------------------------------------------
    # STEP 2A: Aggressive model full sweep
    # ------------------------------------------------------------------
    print_header("STEP 2A: AGGRESSIVE MODEL FULL SWEEP")
    print(f"  Session: ORB {'10m' if agg_orb == '20:10' else '15m'}, ATR {agg_atr}")

    agg_config = build_config(
        agg_orb, agg_atr,
        agg_base["stop"], agg_base["gap"], agg_base["maxgap"],
        agg_base["rr"], agg_base["tp1"],
    )

    agg_ranges = {
        "asia_stop_atr_pct": [3.0, 3.5, 4.0, 4.5, 5.0],
        "asia_min_gap_atr_pct": [0.5, 0.75, 1.0, 1.25, 1.5],
        "asia_max_gap_atr_pct": [5.0, 8.0, 11.0, 15.0],
        "rr": [2.5, 3.0, 3.5, 4.0, 5.0],
        "tp1_ratio": [0.3, 0.4, 0.5, 0.6],
    }

    agg = run_model_sweep("AGGRESSIVE", df, df_1m, agg_config, agg_ranges)

    # ------------------------------------------------------------------
    # STEP 2B: Wide model full sweep
    # ------------------------------------------------------------------
    print_header("STEP 2B: WIDE MODEL FULL SWEEP")
    print(f"  Session: ORB {'10m' if wide_orb == '20:10' else '15m'}, ATR {wide_atr}")

    wide_config = build_config(
        wide_orb, wide_atr,
        wide_base["stop"], wide_base["gap"], wide_base["maxgap"],
        wide_base["rr"], wide_base["tp1"],
    )

    wide_ranges = {
        "asia_stop_atr_pct": [4.5, 5.0, 5.75, 6.5, 7.0],
        "asia_min_gap_atr_pct": [0.75, 1.0, 1.25, 1.5],
        "asia_max_gap_atr_pct": [5.0, 7.0, 8.0, 9.0, 11.0],
        "rr": [1.0, 1.25, 1.5, 1.75, 2.0],
        "tp1_ratio": [0.1, 0.15, 0.2, 0.25, 0.3],
    }

    wide = run_model_sweep("WIDE", df, df_1m, wide_config, wide_ranges)

    # ------------------------------------------------------------------
    # STEP 3: Save winners to DB
    # ------------------------------------------------------------------
    print_header("STEP 3: SAVE WINNERS TO DB")

    saved = []

    def save_winner(row, name):
        cfg = with_overrides(row["_config"], name=name)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        result = results_to_dict(trades, cfg, include_equity_curve=True)
        result["notes"] = (
            f"stop={row['stop']:.1f}%, gap={row['gap']:.2f}%, "
            f"maxgap={row['maxgap']:.1f}%, rr={row['rr']:.1f}, tp1={row['tp1']:.2f}. "
            f"{row['trades']} trades, {row['wr']:.1%} WR, {row['net_r']:.1f}R, "
            f"{row['max_dd_r']:.1f}R DD, Sharpe {row['sharpe']:.3f}"
        )
        rid = save_backtest_result(result)
        print(f"  Saved: {rid} — {name}")
        saved.append((name, rid, row))

    # Best aggressive by Sharpe
    if agg["by_sharpe"]:
        save_winner(agg["by_sharpe"][0], "NQ ASIA Aggressive PRE-PIPELINE")

    # Best aggressive for prop (if different)
    if agg["prop"] and (not agg["by_sharpe"] or agg["prop"][0] is not agg["by_sharpe"][0]):
        save_winner(agg["prop"][0], "NQ ASIA Aggressive Prop PRE-PIPELINE")

    # Best wide by Sharpe
    if wide["by_sharpe"]:
        save_winner(wide["by_sharpe"][0], "NQ ASIA Wide PRE-PIPELINE")

    # Best wide for prop (if different)
    if wide["prop"] and (not wide["by_sharpe"] or wide["prop"][0] is not wide["by_sharpe"][0]):
        save_winner(wide["prop"][0], "NQ ASIA Wide Prop PRE-PIPELINE")

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print_header("FINAL SUMMARY")

    elapsed = time.time() - t_start
    print(f"Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"Aggressive: {agg['n_configs']:,} combos, {len(agg['all']):,} valid")
    print(f"Wide:       {wide['n_configs']:,} combos, {len(wide['all']):,} valid")
    print()

    for name, rid, r in saved:
        print(f"  {name}")
        print(f"    ID:     {rid}")
        print(f"    Config: stop={r['stop']:.1f}%, gap={r['gap']:.2f}%, "
              f"maxgap={r['maxgap']:.1f}%, rr={r['rr']:.1f}, tp1={r['tp1']:.2f}")
        print(f"    Perf:   {r['trades']} trades, {r['wr']:.1%} WR, "
              f"{r['net_r']:.1f}R, {r['max_dd_r']:.1f}R DD, Sharpe {r['sharpe']:.3f}")
        print()

    # Verify distinct parameter spaces
    if agg["by_sharpe"] and wide["by_sharpe"]:
        a = agg["by_sharpe"][0]
        w = wide["by_sharpe"][0]
        print(f"  Parameter space check:")
        print(f"    Aggressive: stop={a['stop']:.1f}%, rr={a['rr']:.1f}, WR={a['wr']:.1%}")
        print(f"    Wide:       stop={w['stop']:.1f}%, rr={w['rr']:.1f}, WR={w['wr']:.1%}")
        overlap = a["stop"] == w["stop"] and a["rr"] == w["rr"]
        print(f"    Overlap: {'WARNING' if overlap else 'None (good)'}")


if __name__ == "__main__":
    main()
