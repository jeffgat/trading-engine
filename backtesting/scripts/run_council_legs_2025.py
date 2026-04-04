#!/usr/bin/env python3
"""Run the 3 council-recommended legs to get 2025 calendar-year performance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result


def run_leg(name, instrument_sym, session, config_overrides, magnifier="1m"):
    """Run a single leg and print yearly breakdown."""
    inst = get_instrument(instrument_sym)
    data_file = inst.data_file

    config = StrategyConfig(
        sessions=(session,),
        instrument=inst,
        strategy="continuation",
        use_bar_magnifier=(magnifier != "off"),
        name=name,
        **config_overrides,
    )

    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  {instrument_sym} | RR={config.rr} | TP1={config.tp1_ratio} | Dir={config.direction_filter}")
    print(f"  Stop: ATR {session.stop_atr_pct}% / ORB {session.stop_orb_pct}%")
    print(f"  ORB: {session.orb_start}-{session.orb_end} | Entry: {session.entry_start}-{session.entry_end}")
    print(f"{'='*60}")

    print("Loading data...")
    df = load_5m_data(data_file, start="2020-01-01")
    df_1m = None
    df_1s = None
    if magnifier in ("1m", "1s"):
        df_1m = load_1m_for_5m(data_file)
    if magnifier == "1s":
        df_1s = load_1s_for_5m(data_file)
        if df_1s is None:
            print("  WARNING: 1s data not found, falling back to 1m only")

    print("Running backtest...")
    trades = run_backtest(df, config, start_date="2020-01-01", df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    metrics = compute_metrics(trades)

    print(f"\n  Total trades: {len(filled)}")
    print(f"  Net R: {metrics['total_r']:.1f}R")
    print(f"  Win rate: {metrics['win_rate']:.1%}")
    print(f"  Calmar: {metrics['calmar_ratio']:.2f}")
    print(f"  Max DD: {metrics['max_drawdown_r']:.1f}R")

    r_by_year = metrics.get("r_by_year", {})
    print(f"\n  R by Year:")
    for year in sorted(r_by_year.keys()):
        r = r_by_year[year]
        print(f"    {year}: {r:+.1f}R")

    # Save to DB
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"\n  Saved: {result_id}")

    return metrics


def main():
    # ── Leg 1: NQ Asia-B (Long, 15m ORB, ORB 100% stop, RR 3.5, TP1 0.6) ──
    nq_asia_session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",       # 15m ORB
        entry_start="20:15",
        entry_end="23:15",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=100.0,    # ORB 100%
        min_gap_orb_pct=10.0,  # Standard gap filter
    )
    run_leg(
        name="NQ Asia-B Council Leg (Long ORB100 RR3.5 TP0.6)",
        instrument_sym="NQ",
        session=nq_asia_session,
        config_overrides=dict(
            rr=3.5,
            tp1_ratio=0.6,
            atr_length=14,
            direction_filter="long",
            risk_usd=5000.0,
        ),
        magnifier="1m",
    )

    # ── Leg 2: GC Asia-1 (Both, 30m ORB, ORB 25% stop, RR 2.5, TP1 0.6) ──
    gc_asia_session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:30",       # 30m ORB
        entry_start="20:30",
        entry_end="23:15",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=25.0,     # ORB 25%
        min_gap_orb_pct=10.0,
    )
    run_leg(
        name="GC Asia-1 Council Leg (Both ORB25 RR2.5 TP0.6)",
        instrument_sym="GC",
        session=gc_asia_session,
        config_overrides=dict(
            rr=2.5,
            tp1_ratio=0.6,
            atr_length=14,
            direction_filter="both",
            risk_usd=5000.0,
        ),
        magnifier="1s",
    )

    # ── Leg 3: CL LDN-1 (Long, 30m ORB, ATR 8% stop, RR 3.5, TP1 0.6) ──
    cl_ldn_session = SessionConfig(
        name="LDN",
        orb_start="03:00",
        orb_end="03:30",       # 30m ORB
        entry_start="03:30",
        entry_end="07:00",
        flat_start="08:20",
        flat_end="08:25",
        stop_atr_pct=8.0,      # ATR 8%
        min_gap_atr_pct=0.25,  # Standard gap filter
    )
    run_leg(
        name="CL LDN-1 Council Leg (Long ATR8 RR3.5 TP0.6)",
        instrument_sym="CL",
        session=cl_ldn_session,
        config_overrides=dict(
            rr=3.5,
            tp1_ratio=0.6,
            atr_length=14,
            direction_filter="long",
            risk_usd=5000.0,
        ),
        magnifier="1m",
    )

    print("\n\nDone! All 3 legs saved to DB.")


if __name__ == "__main__":
    main()
