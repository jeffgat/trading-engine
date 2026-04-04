#!/usr/bin/env python3
"""Sweep ATR length and DOW exclusion for each ALPHA_V1 leg."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ─── Data cache ───
_data_cache: dict[str, tuple] = {}


def get_data(symbol: str):
    if symbol not in _data_cache:
        inst = get_instrument(symbol)
        df = load_5m_data(inst.data_file, start="2020-01-01")
        df_1m = load_1m_for_5m(inst.data_file)
        _data_cache[symbol] = (df, df_1m)
    return _data_cache[symbol]


def run_one(name: str, symbol: str, session: SessionConfig, config_kw: dict) -> dict:
    inst = get_instrument(symbol)
    df, df_1m = get_data(symbol)
    config = StrategyConfig(
        sessions=(session,),
        instrument=inst,
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name=name,
        **config_kw,
    )
    trades = run_backtest(df, config, start_date="2020-01-01", df_1m=df_1m)
    return compute_metrics(trades)


def print_result(label: str, m: dict):
    r_by_year = m.get("r_by_year", {})
    years_str = " | ".join(f"{y}:{r_by_year[y]:+.1f}" for y in sorted(r_by_year))
    print(f"  {label:<45} Net:{m['total_r']:+7.1f}R  DD:{m['max_drawdown_r']:+6.1f}R  "
          f"Cal:{m['calmar_ratio']:6.2f}  WR:{m['win_rate']:.1%}  Trades:{m['total_trades']:4d}  | {years_str}")


def main():
    results = {}

    # ═══════════════════════════════════════════════════════════════
    # LEG 1: NQ NY LSI — ATR 10 vs 14, DOW Wed+Thu vs none
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 120)
    print("LEG 1: NQ NY LSI")
    print("=" * 120)

    ny_lsi_session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:30",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=5.0,
    )

    lsi_base = dict(
        strategy="lsi",
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.34,
        lsi_n_left=8,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
    )

    for atr in [10, 14]:
        for dow_label, dow_excl in [("Wed+Thu", (2, 3)), ("None", ())]:
            label = f"ATR={atr:2d}  DOW_excl={dow_label}"
            tag = "CURRENT" if atr == 10 and dow_label == "Wed+Thu" else ""
            m = run_one(
                f"NQ NY LSI ATR{atr} DOW_{dow_label}",
                "NQ", ny_lsi_session,
                {**lsi_base, "atr_length": atr, "excluded_days": dow_excl},
            )
            if tag:
                label = f"{label}  *** CURRENT ***"
            print_result(label, m)

    # ═══════════════════════════════════════════════════════════════
    # LEG 2: NQ Asia ORB — ATR 5 vs 14, DOW Tue vs none
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 120)
    print("LEG 2: NQ Asia ORB")
    print("=" * 120)

    asia_nq_session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_orb_pct=100.0, min_gap_orb_pct=10.0,
    )

    cont_nq_base = dict(
        strategy="continuation",
        direction_filter="long",
        rr=6.0,
        tp1_ratio=0.3,
    )

    for atr in [5, 14]:
        for dow_label, dow_excl in [("Tue", (1,)), ("None", ())]:
            label = f"ATR={atr:2d}  DOW_excl={dow_label}"
            tag = "CURRENT" if atr == 5 and dow_label == "Tue" else ""
            m = run_one(
                f"NQ Asia ORB ATR{atr} DOW_{dow_label}",
                "NQ", asia_nq_session,
                {**cont_nq_base, "atr_length": atr, "excluded_days": dow_excl},
            )
            if tag:
                label = f"{label}  *** CURRENT ***"
            print_result(label, m)

    # ═══════════════════════════════════════════════════════════════
    # LEG 3: ES Asia ORB — Already ATR 14, no DOW filter
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 120)
    print("LEG 3: ES Asia ORB — No sweep needed (already ATR 14, no DOW filter)")
    print("=" * 120)

    asia_es_session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_orb_pct=125.0, min_gap_atr_pct=0.5,
        min_stop_points=3.0, min_tp1_points=3.0,
    )

    m = run_one(
        "ES Asia ORB ATR14 No DOW (baseline)",
        "ES", asia_es_session,
        dict(strategy="continuation", direction_filter="long", rr=1.5, tp1_ratio=0.7, atr_length=14),
    )
    print_result("ATR=14  DOW_excl=None  *** CURRENT ***", m)

    # ═══════════════════════════════════════════════════════════════
    # LEG 4: ES NY ORB — ATR 7 vs 14, DOW Thu vs none
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 120)
    print("LEG 4: ES NY ORB")
    print("=" * 120)

    ny_es_session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=0.25,
        min_stop_points=3.0, min_tp1_points=3.0,
    )

    cont_es_base = dict(
        strategy="continuation",
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
    )

    for atr in [7, 14]:
        for dow_label, dow_excl in [("Thu", (3,)), ("None", ())]:
            label = f"ATR={atr:2d}  DOW_excl={dow_label}"
            tag = "CURRENT" if atr == 7 and dow_label == "Thu" else ""
            m = run_one(
                f"ES NY ORB ATR{atr} DOW_{dow_label}",
                "ES", ny_es_session,
                {**cont_es_base, "atr_length": atr, "excluded_days": dow_excl},
            )
            if tag:
                label = f"{label}  *** CURRENT ***"
            print_result(label, m)

    print("\n\nDone.")


if __name__ == "__main__":
    main()
