#!/usr/bin/env python3
"""ES NY LSI Discovery — Using NQ RR2/TP0.5 anchor.

Tests the proven NQ NY LSI RR2/TP0.5 config transplanted to ES.
Previous ES LSI tests used different anchors (RR=5.5/TP1=0.4) and
encountered destructive parameter interaction. This test uses the
exact NQ winner as the starting point.

Strategy workflow steps 1-4:
  Phase A: Baseline — exact NQ config on ES (both entry modes + directions)
  Phase B: Swing param sweep (n_left × n_right)
  Phase C: RR × TP1 grid (focused around NQ winner region)
  Phase D: DOW filter sweep
  Phase E: min_gap_atr_pct sweep
  Phase F: ATR length sweep
  Phase G: entry_end / flat_start sweep

Pre-holdout: 2016-01 to 2025-03-31 (holdout frozen at 2025-04-01).
Uses 1s magnifier for fill resolution.
"""

import dataclasses
import json
import sys
import time
from pathlib import Path
from statistics import median

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Constants ────────────────────────────────────────────────────────────
HOLDOUT_START = "2025-04-01"
END_DATE = "2025-03-31"

# ── Session: same as NQ winner ───────────────────────────────────────────
NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

# ── Anchor: exact NQ winner transplanted to ES ──────────────────────────
ANCHOR = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=ES,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(),  # No DOW filter yet — test all days first
    name="ES NY LSI NQ Anchor",
)


# ── Helpers ──────────────────────────────────────────────────────────────

def run_one(df, config, maps, df_1m, df_1s):
    """Run backtest, return metrics dict."""
    trades = run_backtest(df, config, end_date=END_DATE,
                          df_1m=df_1m, df_1s=df_1s, _maps=maps)
    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    med_stop = median(t.risk_points / ES.min_tick for t in filled) if filled else 0
    return {
        "trades": m["total_trades"],
        "win_rate": m["win_rate"],
        "net_r": m["total_r"],
        "max_dd_r": m["max_drawdown_r"],
        "calmar": m["calmar_ratio"],
        "sharpe": m["sharpe_ratio"],
        "pf": m["profit_factor"],
        "avg_r": m["avg_r"],
        "r_per_yr": m.get("avg_annual_r", m["total_r"] / 9.25),
        "med_stop_ticks": med_stop,
        "r_by_year": m.get("r_by_year", {}),
        "neg_years": sum(1 for v in m.get("r_by_year", {}).values() if v < 0),
    }


def pr(idx, total, label, r, elapsed=None):
    neg_str = f" ({r['neg_years']} neg yr)" if r["neg_years"] > 0 else ""
    elapsed_str = f"  [{elapsed:.1f}s]" if elapsed else ""
    print(
        f"  [{idx:>3}/{total}] {label:<40} "
        f"{r['trades']:>4}tr  {r['win_rate']:>5.1%}WR  "
        f"{r['net_r']:>+7.1f}R  DD {r['max_dd_r']:>6.1f}R  "
        f"Calm {r['calmar']:>7.2f}  Shrp {r['sharpe']:>5.2f}  "
        f"PF {r['pf']:>4.2f}{neg_str}{elapsed_str}",
        flush=True,
    )


def ranked(title, rows, top_n=None):
    rows_sorted = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)
    show = rows_sorted[:top_n] if top_n else rows_sorted
    print(f"\n{'=' * 145}", flush=True)
    print(f"  {title}", flush=True)
    print(f"{'=' * 145}", flush=True)
    print(
        f"  {'#':>3} {'Config':<40} {'Tr':>4} {'WR%':>6} {'NetR':>7} {'MaxDD':>7} "
        f"{'Calm':>7} {'Shrp':>6} {'PF':>5} {'R/yr':>6} {'NegYr':>5}",
        flush=True,
    )
    print(f"  {'-' * 139}", flush=True)
    for i, (label, r) in enumerate(show):
        print(
            f"  {i+1:>3} {label:<40} {r['trades']:>4} {r['win_rate']:>5.1%} "
            f"{r['net_r']:>+7.1f} {r['max_dd_r']:>7.1f} {r['calmar']:>7.2f} "
            f"{r['sharpe']:>6.2f} {r['pf']:>5.2f} {r['r_per_yr']:>6.1f} "
            f"{r['neg_years']:>5}",
            flush=True,
        )
    # R by year top 3
    print(f"\n  R by year — top 3:", flush=True)
    for i, (label, r) in enumerate(rows_sorted[:3]):
        rby = r["r_by_year"]
        years_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in sorted(rby.items()))
        print(f"    #{i+1} {label:<40} {years_str}", flush=True)
    return rows_sorted


def main():
    t_start = time.time()

    print("=" * 80, flush=True)
    print("ES NY LSI DISCOVERY — NQ RR2/TP0.5 ANCHOR", flush=True)
    print("=" * 80, flush=True)
    print(f"Thesis: Transplant the proven NQ NY LSI RR2/TP0.5 config to ES.", flush=True)
    print(f"Previous ES LSI tests used RR=5.5/TP1=0.4 → NO-GO (Calmar 5.87).", flush=True)
    print(f"This tests the NQ winner anchor directly.", flush=True)
    print(f"Pre-holdout: 2016 to {END_DATE}", flush=True)
    print(flush=True)

    # ── Load data ────────────────────────────────────────────────────────
    print("Loading ES data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("ES_5m.parquet")
    df_1m = load_1m_for_5m("ES_5m.parquet")
    df_1s = load_1s_for_5m("ES_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}" if df_1s is not None
          else f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: not available", flush=True)
    print(f"  Setup in {time.time() - t_start:.1f}s\n", flush=True)

    all_results = {}

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE A: Baseline — NQ config on ES (entry modes × directions)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"{'─' * 80}", flush=True)
    print("PHASE A: Baseline (NQ config transplanted to ES)", flush=True)
    print(f"{'─' * 80}", flush=True)

    baseline_combos = [
        ("fvg_limit long", "fvg_limit", "long"),
        ("fvg_limit short", "fvg_limit", "short"),
        ("fvg_limit both", "fvg_limit", "both"),
        ("close long", "close", "long"),
        ("close short", "close", "short"),
        ("close both", "close", "both"),
    ]

    baseline_rows = []
    total = len(baseline_combos)
    for idx, (label, em, df_) in enumerate(baseline_combos, 1):
        cfg = dataclasses.replace(ANCHOR, lsi_entry_mode=em, direction_filter=df_,
                                   name=f"ES NY LSI {label}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        baseline_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["baseline"] = baseline_rows
    baseline_sorted = ranked("PHASE A: BASELINE", baseline_rows)

    # Determine best entry mode and direction for subsequent phases
    best_base_label, best_base_r = baseline_sorted[0]
    best_em = "fvg_limit" if "fvg_limit" in best_base_label else "close"
    best_dir = "long" if "long" in best_base_label else ("short" if "short" in best_base_label else "both")
    print(f"\n  → Best baseline: {best_base_label} (Calmar {best_base_r['calmar']:.2f})", flush=True)

    # Check structural viability
    if best_base_r["calmar"] < 1.0 or best_base_r["trades"] < 50:
        print(f"\n  ⚠ STRUCTURALLY DEAD — best Calmar {best_base_r['calmar']:.2f}, {best_base_r['trades']} trades", flush=True)
        print(f"  Strategy is not structurally alive. Proceeding with sweeps anyway for completeness.", flush=True)

    # Update anchor for subsequent phases
    anchor = dataclasses.replace(ANCHOR, lsi_entry_mode=best_em, direction_filter=best_dir)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE B: Swing param sweep (n_left × n_right)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE B: Swing param sweep (n_left × n_right) [{best_em} {best_dir}]", flush=True)
    print(f"{'─' * 80}", flush=True)

    N_LEFT_VALUES = [3, 5, 8, 10, 12, 15, 20, 25]
    N_RIGHT_VALUES = [20, 30, 45, 60, 78, 90, 120]

    swing_rows = []
    total = len(N_LEFT_VALUES) * len(N_RIGHT_VALUES)
    idx = 0
    for nl in N_LEFT_VALUES:
        for nr in N_RIGHT_VALUES:
            idx += 1
            label = f"nL={nl} nR={nr}"
            cfg = dataclasses.replace(anchor, lsi_n_left=nl, lsi_n_right=nr,
                                       name=f"ES NY LSI nL{nl} nR{nr}")
            t1 = time.time()
            r = run_one(df_5m, cfg, maps, df_1m, df_1s)
            swing_rows.append((label, r))
            pr(idx, total, label, r, time.time() - t1)

    all_results["swing"] = swing_rows
    swing_sorted = ranked("PHASE B: SWING PARAM SWEEP", swing_rows, top_n=20)

    parts = swing_sorted[0][0].split()
    best_nl = int(parts[0].split("=")[1])
    best_nr = int(parts[1].split("=")[1])
    print(f"\n  → Best swing: n_left={best_nl}, n_right={best_nr} (Calmar {swing_sorted[0][1]['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE C: RR × TP1 grid (focused)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE C: RR × TP1 grid (at nL={best_nl}, nR={best_nr})", flush=True)
    print(f"{'─' * 80}", flush=True)

    RR_VALUES = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5, 4.0, 5.0]
    TP1_VALUES = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]

    valid_combos = [(rr, tp1) for rr in RR_VALUES for tp1 in TP1_VALUES if tp1 * rr >= 1.0]
    total = len(valid_combos)
    print(f"  {total} valid combinations", flush=True)

    rr_rows = []
    idx = 0
    for rr, tp1 in valid_combos:
        idx += 1
        label = f"RR={rr:.2f} TP1={tp1:.2f}"
        try:
            cfg = dataclasses.replace(anchor, rr=rr, tp1_ratio=tp1,
                                       lsi_n_left=best_nl, lsi_n_right=best_nr,
                                       name=f"ES NY LSI RR{rr} TP{tp1}")
        except ValueError:
            continue
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        rr_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["rr_tp1"] = rr_rows
    rr_sorted = ranked("PHASE C: RR × TP1 GRID", rr_rows, top_n=20)

    parts = rr_sorted[0][0].split()
    best_rr = float(parts[0].split("=")[1])
    best_tp1 = float(parts[1].split("=")[1])
    print(f"\n  → Best RR×TP1: RR={best_rr}, TP1={best_tp1} (Calmar {rr_sorted[0][1]['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE D: DOW filter sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE D: DOW filter sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    DOW_COMBOS = {
        "No filter": (),
        "Thu excl": (3,),
        "Wed+Thu excl": (2, 3),
        "Mon excl": (0,),
        "Fri excl": (4,),
        "Mon+Thu excl": (0, 3),
        "Mon+Fri excl": (0, 4),
        "MTF only": (2, 3),
        "Tue+Wed+Thu excl": (1, 2, 3),
    }

    dow_rows = []
    total = len(DOW_COMBOS)
    for idx, (label, excl_days) in enumerate(DOW_COMBOS.items(), 1):
        cfg = dataclasses.replace(anchor, lsi_n_left=best_nl, lsi_n_right=best_nr,
                                   rr=best_rr, tp1_ratio=best_tp1,
                                   excluded_days=excl_days,
                                   name=f"ES NY LSI DOW {label}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        dow_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["dow"] = dow_rows
    dow_sorted = ranked("PHASE D: DOW FILTER SWEEP", dow_rows)

    best_dow_label = dow_sorted[0][0]
    best_excl = DOW_COMBOS[best_dow_label]
    print(f"\n  → Best DOW: {best_dow_label} (Calmar {dow_sorted[0][1]['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE E: min_gap_atr_pct sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE E: min_gap_atr_pct sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    GAP_VALUES = [0.0, 1.0, 2.0, 3.0, 3.75, 4.0, 5.0, 6.0, 7.5, 10.0]

    gap_rows = []
    total = len(GAP_VALUES)
    for idx, gap in enumerate(GAP_VALUES, 1):
        label = f"gap={gap:.1f}%"
        ny_sess = dataclasses.replace(NY_SESSION, min_gap_atr_pct=gap)
        cfg = dataclasses.replace(anchor, sessions=(ny_sess,),
                                   lsi_n_left=best_nl, lsi_n_right=best_nr,
                                   rr=best_rr, tp1_ratio=best_tp1,
                                   excluded_days=best_excl,
                                   name=f"ES NY LSI gap{gap}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        gap_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["gap"] = gap_rows
    gap_sorted = ranked("PHASE E: MIN_GAP_ATR_PCT SWEEP", gap_rows)

    best_gap = float(gap_sorted[0][0].split("=")[1].rstrip("%"))
    print(f"\n  → Best gap: {best_gap}% (Calmar {gap_sorted[0][1]['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE F: ATR length sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE F: ATR length sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    ATR_VALUES = [5, 7, 10, 12, 14, 16, 20, 25, 30]

    atr_rows = []
    total = len(ATR_VALUES)
    for idx, atr in enumerate(ATR_VALUES, 1):
        label = f"ATR={atr}"
        ny_sess = dataclasses.replace(NY_SESSION, min_gap_atr_pct=best_gap)
        cfg = dataclasses.replace(anchor, sessions=(ny_sess,), atr_length=atr,
                                   lsi_n_left=best_nl, lsi_n_right=best_nr,
                                   rr=best_rr, tp1_ratio=best_tp1,
                                   excluded_days=best_excl,
                                   name=f"ES NY LSI ATR{atr}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        atr_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["atr"] = atr_rows
    atr_sorted = ranked("PHASE F: ATR LENGTH SWEEP", atr_rows)

    best_atr = int(atr_sorted[0][0].split("=")[1])
    print(f"\n  → Best ATR: {best_atr} (Calmar {atr_sorted[0][1]['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE G: entry_end / flat_start sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE G: entry_end and flat_start sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    EE_VALUES = ["11:00", "12:00", "13:00", "14:00", "15:00", "15:30"]
    FLAT_VALUES = ["14:00", "15:00", "15:30", "15:50"]

    time_rows = []
    total = len(EE_VALUES) + len(FLAT_VALUES)
    idx = 0

    # entry_end sweep (flat_start fixed)
    for ee in EE_VALUES:
        idx += 1
        label = f"entry_end={ee}"
        ny_sess = dataclasses.replace(NY_SESSION, entry_end=ee, min_gap_atr_pct=best_gap)
        cfg = dataclasses.replace(anchor, sessions=(ny_sess,), atr_length=best_atr,
                                   lsi_n_left=best_nl, lsi_n_right=best_nr,
                                   rr=best_rr, tp1_ratio=best_tp1,
                                   excluded_days=best_excl,
                                   name=f"ES NY LSI ee{ee}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        time_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    # flat_start sweep (entry_end fixed at best or default)
    for fs in FLAT_VALUES:
        idx += 1
        label = f"flat_start={fs}"
        ny_sess = dataclasses.replace(NY_SESSION, flat_start=fs, min_gap_atr_pct=best_gap)
        cfg = dataclasses.replace(anchor, sessions=(ny_sess,), atr_length=best_atr,
                                   lsi_n_left=best_nl, lsi_n_right=best_nr,
                                   rr=best_rr, tp1_ratio=best_tp1,
                                   excluded_days=best_excl,
                                   name=f"ES NY LSI fs{fs}")
        t1 = time.time()
        r = run_one(df_5m, cfg, maps, df_1m, df_1s)
        time_rows.append((label, r))
        pr(idx, total, label, r, time.time() - t1)

    all_results["time_windows"] = time_rows
    ranked("PHASE G: TIME WINDOW SWEEP", time_rows)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}", flush=True)
    print("FINAL SUMMARY — ES NY LSI DISCOVERY (NQ ANCHOR)", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"\n  NQ reference: 588 tr, 61.1% WR, +126.4R, DD -7.6R, Calmar 16.72, Sharpe 3.65", flush=True)
    print(f"  Previous ES LSI best: 544 tr, 47.4% WR, +53.5R, DD -9.1R, Calmar 5.87, PF 1.20", flush=True)
    print(flush=True)

    for phase_name, rows in all_results.items():
        best = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)[0]
        label, r = best
        print(
            f"  Best {phase_name:<15}: {label:<40} "
            f"Calmar {r['calmar']:>7.2f}  {r['trades']}tr  {r['net_r']:+.1f}R  "
            f"DD {r['max_dd_r']:.1f}R  Sharpe {r['sharpe']:.2f}  NegYr {r['neg_years']}",
            flush=True,
        )

    # Structural viability check
    overall_best = max(
        ((l, r) for rows in all_results.values() for l, r in rows),
        key=lambda x: x[1]["calmar"],
    )
    label, r = overall_best
    print(f"\n  OVERALL BEST: {label}", flush=True)
    print(f"    Calmar {r['calmar']:.2f} | {r['trades']} trades | {r['win_rate']:.1%} WR | "
          f"+{r['net_r']:.1f}R | DD {r['max_dd_r']:.1f}R | PF {r['pf']:.2f} | "
          f"Sharpe {r['sharpe']:.2f} | {r['neg_years']} neg years", flush=True)

    if r["calmar"] >= 5.0 and r["neg_years"] <= 2 and r["pf"] >= 1.20:
        print(f"\n  ✓ STRUCTURALLY ALIVE — proceed to discovery-pipeline (step 5)", flush=True)
    elif r["calmar"] >= 2.0 and r["trades"] >= 100:
        print(f"\n  ⚠ MARGINAL — edge exists but weak. Consider whether to proceed.", flush=True)
    else:
        print(f"\n  ✗ STRUCTURALLY DEAD — edge does not survive on ES. NO-GO.", flush=True)

    # ── Save ─────────────────────────────────────────────────────────────
    output_path = ROOT / "data" / "results" / "es_ny_lsi_discovery_nq_anchor.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def convert(obj):
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    save_data = {
        "info": {
            "description": "ES NY LSI discovery using NQ RR2/TP0.5 anchor",
            "nq_reference": "Calmar 16.72, 588 tr, +126.4R, Sharpe 3.646",
            "prev_es_lsi_best": "Calmar 5.87, 544 tr, +53.5R, PF 1.20",
            "holdout_start": HOLDOUT_START,
            "end_date": END_DATE,
        },
        "phases": {
            phase: [{"label": l, **{k: v for k, v in r.items() if k != "r_by_year"}}
                    for l, r in rows]
            for phase, rows in all_results.items()
        },
    }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}", flush=True)
    print(f"Total time: {time.time() - t_start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
