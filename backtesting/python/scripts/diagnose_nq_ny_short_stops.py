"""Diagnostic: Investigate NQ NY Short stop distance mechanics.

Concern: With stop_orb_pct=15%, the stop distance may be tiny relative to
NQ price action, causing TP1 to fire on trivial retracements and creating
artificially high win rates via breakeven stops.

Key: tp1_ratio=0.2, rr=2.0 → TP1 distance = risk_pts * rr * tp1_ratio = 0.4R
If stop is 5 pts → TP1 at 2 pts from entry. Any wiggle triggers TP1 → BE.
"""

import sys

sys.path.insert(0, "src")

from dataclasses import replace

import numpy as np

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter

# ---------------------------------------------------------------------------
# Config: NQ NY Short R10 anchor
# ---------------------------------------------------------------------------
NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",       # 20m ORB
    entry_start="09:50",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=2.0,
    stop_orb_pct=15.0,
    min_gap_orb_pct=7.0,
)

config = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    rr=2.0,
    tp1_ratio=0.2,
    atr_length=14,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    name="NQ NY Short R10 Stop Diagnostic",
)

# ---------------------------------------------------------------------------
# Load data & run backtest
# ---------------------------------------------------------------------------
print("Loading data...")
df = load_5m_data(NQ.data_file)
df_1m = load_1m_for_5m(NQ.data_file)
df_1s = load_1s_for_5m(NQ.data_file)

print(f"5m bars: {len(df):,}   1m bars: {len(df_1m) if df_1m is not None else 0:,}   1s bars: {len(df_1s) if df_1s is not None else 0:,}")

print("\nRunning backtest...")
trades = run_backtest(df, config, df_1m=df_1m, df_1s=df_1s)

# Apply DOW filter (Mon+Fri excluded)
trades = apply_dow_filter(trades, {0, 4})

# Separate filled trades
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
no_fills = len(trades) - len(filled)

print(f"\nTotal signals: {len(trades)}   Filled: {len(filled)}   No-fill: {no_fills}")

if not filled:
    print("No filled trades — nothing to diagnose.")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Derived arrays
# ---------------------------------------------------------------------------
stop_dist_pts = np.array([abs(t.entry_price - t.stop_price) for t in filled])
stop_dist_ticks = stop_dist_pts / NQ.min_tick  # 0.25 per tick

# TP1 distance: with rr and tp1_ratio
# TP1 price = entry ± risk_pts * rr * tp1_ratio (for shorts, entry - ...)
# Actually, the TP1 is stored in the trade result directly.
tp1_dist_pts = np.array([abs(t.entry_price - t.tp1_price) for t in filled])
tp2_dist_pts = np.array([abs(t.entry_price - t.tp2_price) for t in filled])

r_multiples = np.array([t.r_multiple for t in filled])
risk_points = np.array([t.risk_points for t in filled])
pnl_pts = np.array([t.pnl_points for t in filled])
entry_prices = np.array([t.entry_price for t in filled])

# ORB range proxy: stop distance / stop_orb_pct * 100
# stop_dist = orb_range * stop_orb_pct/100 → orb_range = stop_dist / (stop_orb_pct/100)
orb_range_est = stop_dist_pts / (NY_SESSION.stop_orb_pct / 100.0)

# USD per trade
pnl_usd = np.array([t.pnl_usd for t in filled])

# Exit types
exit_types = [EXIT_NAMES.get(t.exit_type, f"unknown_{t.exit_type}") for t in filled]
unique_exits = sorted(set(exit_types))

# ---------------------------------------------------------------------------
# Print percentile distributions
# ---------------------------------------------------------------------------
pctiles = [5, 10, 25, 50, 75, 90, 95]


def print_pctile_table(label: str, arr: np.ndarray, unit: str = ""):
    vals = np.percentile(arr, pctiles)
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    print(f"  {'Pctile':<10} {'Value':>12}  {unit}")
    print(f"  {'-'*40}")
    for p, v in zip(pctiles, vals):
        print(f"  {p:>5}th    {v:>12.2f}  {unit}")
    print(f"  {'':>6}Mean   {arr.mean():>12.2f}  {unit}")
    print(f"  {'':>6}Std    {arr.std():>12.2f}  {unit}")
    print(f"  {'':>6}Min    {arr.min():>12.2f}  {unit}")
    print(f"  {'':>6}Max    {arr.max():>12.2f}  {unit}")


print_pctile_table("STOP DISTANCE (points)", stop_dist_pts, "pts")
print_pctile_table("STOP DISTANCE (ticks)", stop_dist_ticks, "ticks")
print_pctile_table("TP1 DISTANCE from entry (points)", tp1_dist_pts, "pts")
print_pctile_table("TP2 DISTANCE from entry (points)", tp2_dist_pts, "pts")
print_pctile_table("RISK POINTS (from TradeResult)", risk_points, "pts")
print_pctile_table("REALIZED R-MULTIPLE per trade", r_multiples, "R")
print_pctile_table("PnL per trade (points)", pnl_pts, "pts")
print_pctile_table("ESTIMATED ORB RANGE (points)", orb_range_est, "pts")
print_pctile_table("ENTRY PRICE", entry_prices, "")

# ---------------------------------------------------------------------------
# TP1 distance in ticks
# ---------------------------------------------------------------------------
tp1_dist_ticks = tp1_dist_pts / NQ.min_tick
print_pctile_table("TP1 DISTANCE from entry (ticks)", tp1_dist_ticks, "ticks")

# ---------------------------------------------------------------------------
# Exit type breakdown
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  EXIT TYPE BREAKDOWN")
print(f"{'='*65}")
print(f"  {'Exit Type':<15} {'Count':>6} {'Pct':>7} {'Avg R':>8} {'Med R':>8} {'Avg PnL pts':>12}")
print(f"  {'-'*60}")

for et in unique_exits:
    mask = [i for i, e in enumerate(exit_types) if e == et]
    count = len(mask)
    pct = 100.0 * count / len(filled)
    avg_r = r_multiples[mask].mean()
    med_r = np.median(r_multiples[mask])
    avg_pnl = pnl_pts[mask].mean()
    print(f"  {et:<15} {count:>6} {pct:>6.1f}% {avg_r:>8.3f} {med_r:>8.3f} {avg_pnl:>12.2f}")

# ---------------------------------------------------------------------------
# Win/Loss breakdown
# ---------------------------------------------------------------------------
wins = r_multiples > 0
losses = r_multiples < 0
scratch = r_multiples == 0

print(f"\n{'='*65}")
print(f"  WIN / LOSS SUMMARY")
print(f"{'='*65}")
print(f"  Wins:     {wins.sum():>5}  ({100*wins.mean():.1f}%)")
print(f"  Losses:   {losses.sum():>5}  ({100*losses.mean():.1f}%)")
print(f"  Scratch:  {scratch.sum():>5}  ({100*scratch.mean():.1f}%)")
print(f"  Total R:  {r_multiples.sum():>8.2f}")
print(f"  Avg R:    {r_multiples.mean():>8.4f}")
print(f"  Med R:    {np.median(r_multiples):>8.4f}")

# ---------------------------------------------------------------------------
# Stop distance buckets
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  STOP DISTANCE BUCKETS")
print(f"{'='*65}")

buckets = [
    ("< 2 pts (8 ticks)", stop_dist_pts < 2),
    ("< 3 pts (12 ticks)", stop_dist_pts < 3),
    ("< 5 pts (20 ticks)", stop_dist_pts < 5),
    ("< 10 pts (40 ticks)", stop_dist_pts < 10),
    ("< 15 pts (60 ticks)", stop_dist_pts < 15),
    ("< 20 pts (80 ticks)", stop_dist_pts < 20),
    ("< 30 pts (120 ticks)", stop_dist_pts < 30),
    ("< 50 pts (200 ticks)", stop_dist_pts < 50),
    (">= 50 pts", stop_dist_pts >= 50),
]

print(f"  {'Bucket':<30} {'Count':>6} {'Pct':>7} {'Avg R':>8} {'WR':>7}")
print(f"  {'-'*60}")
for label, mask in buckets:
    count = mask.sum()
    pct = 100.0 * count / len(filled) if count > 0 else 0
    avg_r = r_multiples[mask].mean() if count > 0 else 0
    wr = 100.0 * (r_multiples[mask] > 0).mean() if count > 0 else 0
    print(f"  {label:<30} {count:>6} {pct:>6.1f}% {avg_r:>8.3f} {wr:>6.1f}%")

# ---------------------------------------------------------------------------
# TP1 distance buckets (how far does price need to move for TP1?)
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  TP1 DISTANCE BUCKETS (how far price must move for partial fill)")
print(f"{'='*65}")

tp1_buckets = [
    ("< 1 pt (4 ticks)", tp1_dist_pts < 1),
    ("< 2 pts (8 ticks)", tp1_dist_pts < 2),
    ("< 3 pts (12 ticks)", tp1_dist_pts < 3),
    ("< 5 pts (20 ticks)", tp1_dist_pts < 5),
    ("< 10 pts (40 ticks)", tp1_dist_pts < 10),
    ("< 20 pts (80 ticks)", tp1_dist_pts < 20),
    (">= 20 pts", tp1_dist_pts >= 20),
]

print(f"  {'Bucket':<30} {'Count':>6} {'Pct':>7}")
print(f"  {'-'*45}")
for label, mask in tp1_buckets:
    count = mask.sum()
    pct = 100.0 * count / len(filled) if count > 0 else 0
    print(f"  {label:<30} {count:>6} {pct:>6.1f}%")

# ---------------------------------------------------------------------------
# NQ spread/slippage context
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  SPREAD / SLIPPAGE CONTEXT (NQ)")
print(f"{'='*65}")
print(f"  NQ typical spread: 0.25 - 0.50 pts (1-2 ticks)")
print(f"  NQ typical slippage: 0.25 - 1.00 pts (1-4 ticks)")
print(f"  Round-trip cost (spread+slip): ~1-3 pts")
print(f"  Commission: ${NQ.commission}/contract/side")
print(f"")
print(f"  Median stop distance:  {np.median(stop_dist_pts):.2f} pts = {np.median(stop_dist_ticks):.0f} ticks")
print(f"  Median TP1 distance:   {np.median(tp1_dist_pts):.2f} pts = {np.median(tp1_dist_ticks):.0f} ticks")

if np.median(stop_dist_pts) < 5:
    print(f"\n  *** WARNING: Median stop < 5 pts — stops are within noise range ***")
    print(f"  *** Slippage alone could stop you out on fills ***")
elif np.median(stop_dist_pts) < 10:
    print(f"\n  ** CAUTION: Median stop < 10 pts — tight for NQ **")
    print(f"  ** Slippage is a meaningful fraction of risk **")
else:
    print(f"\n  Stop distances appear reasonable for NQ.")

if np.median(tp1_dist_pts) < 3:
    print(f"  *** WARNING: Median TP1 < 3 pts — nearly any move triggers TP1 ***")
    print(f"  *** This explains the high win rate: most trades hit TP1 → BE ***")
elif np.median(tp1_dist_pts) < 5:
    print(f"  ** CAUTION: Median TP1 < 5 pts — TP1 triggers easily on NQ **")

# ---------------------------------------------------------------------------
# R distribution for tp1_be trades specifically
# ---------------------------------------------------------------------------
tp1_be_mask = [i for i, e in enumerate(exit_types) if e == "tp1_be"]
if tp1_be_mask:
    tp1_be_r = r_multiples[tp1_be_mask]
    tp1_be_pnl = pnl_pts[tp1_be_mask]
    tp1_be_stop = stop_dist_pts[tp1_be_mask]
    print(f"\n{'='*65}")
    print(f"  TP1+BE TRADE ANALYSIS (breakeven after partial)")
    print(f"{'='*65}")
    print(f"  Count:        {len(tp1_be_mask)}")
    print(f"  Avg R:        {tp1_be_r.mean():.4f}")
    print(f"  Total R:      {tp1_be_r.sum():.2f}")
    print(f"  Avg PnL pts:  {tp1_be_pnl.mean():.2f}")
    print(f"  Avg stop pts: {tp1_be_stop.mean():.2f}")
    print(f"")
    print(f"  These trades earn ~{tp1_be_r.mean():.3f}R each (half-position at TP1,")
    print(f"  other half closed at breakeven). With tp1_ratio={config.tp1_ratio},")
    print(f"  the theoretical R is: 0.5 * {config.tp1_ratio} * {config.rr} = {0.5 * config.tp1_ratio * config.rr:.3f}R")
    print(f"  (minus commission)")

# ---------------------------------------------------------------------------
# Calmar & overall metrics
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  OVERALL METRICS (from compute_metrics)")
print(f"{'='*65}")
metrics = compute_metrics(filled)
for key in ["total_trades", "win_rate", "net_r", "avg_r", "sharpe", "calmar",
            "max_dd_r", "profit_factor", "avg_annual_r"]:
    if key in metrics:
        val = metrics[key]
        if isinstance(val, float):
            print(f"  {key:<20} {val:>10.4f}")
        else:
            print(f"  {key:<20} {val:>10}")

# ---------------------------------------------------------------------------
# Summary verdict
# ---------------------------------------------------------------------------
print(f"\n{'='*65}")
print(f"  VERDICT: IS THE HIGH WIN RATE SUSPICIOUS?")
print(f"{'='*65}")

med_stop = np.median(stop_dist_pts)
med_tp1 = np.median(tp1_dist_pts)
pct_be = 100.0 * len(tp1_be_mask) / len(filled) if tp1_be_mask else 0
pct_small_stop = 100.0 * (stop_dist_pts < 10).sum() / len(filled)

print(f"  Median stop:        {med_stop:.1f} pts ({med_stop/NQ.min_tick:.0f} ticks)")
print(f"  Median TP1:         {med_tp1:.1f} pts ({med_tp1/NQ.min_tick:.0f} ticks)")
print(f"  % trades w/ stop<10pts: {pct_small_stop:.1f}%")
print(f"  % trades exit=tp1_be:   {pct_be:.1f}%")
print(f"  Total R:            {r_multiples.sum():.2f}")
print(f"  Avg R per trade:    {r_multiples.mean():.4f}")
print()

if med_stop < 5:
    print("  CONCLUSION: HIGHLY SUSPICIOUS — stops are in the noise.")
    print("  The strategy is essentially: enter, get TP1 on any wiggle,")
    print("  move to breakeven, and scratch the second half. Wins are")
    print("  microscopic and would be eaten by real-world slippage.")
elif med_stop < 10:
    print("  CONCLUSION: SUSPICIOUS — stops are very tight for NQ.")
    print("  TP1 fires easily, inflating win rate. Real-world execution")
    print("  costs would significantly erode the small per-trade edge.")
elif med_stop < 20:
    print("  CONCLUSION: BORDERLINE — stops are on the tight side but")
    print("  potentially viable. Review TP1 distance and per-trade R.")
else:
    print("  CONCLUSION: Stop distances appear reasonable for NQ.")
    print("  Win rate may be genuine if the strategy has real edge.")

print()
