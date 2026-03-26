#!/usr/bin/env python3
"""Compare NQ_NY VWAP distance gate on FAST vs FAST_V2 merged profiles.

For each profile:
- Run NQ_NY baseline, +10% ATR VWAP distance, +15% ATR VWAP distance
- Report full-history, recent, and 2025 hold-out metrics
- Run fixed-parameter walk-forward OOS validation
- Measure whole-profile portfolio impact when only NQ_NY is changed
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import (
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics

from run_fast_v2_nq_context_filters import build_profile_legs

FULL_START = "2016-01-01"
WF_END = "2024-12-31"
RECENT_START = "2024-01-01"
HOLDOUT_START = "2025-01-01"
END_DATE = "2025-12-31"

PROFILES = ("FAST", "FAST_V2")
VWAP_GATES = (0.0, 10.0, 15.0)


def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    out = [t for t in trades if start <= t.date <= end]
    out.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return out


def run_leg(
    base_cfg: StrategyConfig,
    df_5m,
    df_1m,
    excluded_dow: tuple[int, ...],
    maps: dict,
    signal_cache: dict,
    *,
    min_vwap_distance_atr_pct: float,
) -> list[TradeResult]:
    cfg = with_overrides(base_cfg, min_vwap_distance_atr_pct=min_vwap_distance_atr_pct)
    trades = run_backtest(
        df_5m,
        cfg,
        start_date=FULL_START,
        end_date=END_DATE,
        df_1m=df_1m,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    if excluded_dow:
        trades = apply_dow_filter(trades, set(excluded_dow))
    trades = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    trades.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return trades


def metrics_line(trades: list[TradeResult], start: str, end: str) -> str:
    m = compute_metrics(filter_window(trades, start, end))
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:>5.2f} | "
        f"Calmar {m['calmar_ratio']:>5.2f}"
    )


def run_fixed_wf(base_cfg: StrategyConfig, df_5m, df_1m, excluded_dow: tuple[int, ...], gate_pct: float):
    cfg = with_overrides(base_cfg, min_vwap_distance_atr_pct=gate_pct)
    dow_gate = (lambda trades: apply_dow_filter(trades, set(excluded_dow))) if excluded_dow else None
    wf = run_walkforward(
        df_5m.loc[:WF_END],
        cfg,
        param_ranges={"min_vwap_distance_atr_pct": [gate_pct]},
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="sharpe",
        start_date=FULL_START,
        df_1m=df_1m.loc[:WF_END],
        gate_fn=dow_gate,
        progress_fn=lambda idx, total, status: print(
            f"      wf fold {idx + 1}/{total} [{status}] gate={gate_pct:.0f}%",
            flush=True,
        ),
    )
    return wf


def combined_profile_metrics(trade_map: dict[str, list[TradeResult]], start: str, end: str) -> dict:
    combined = []
    for trades in trade_map.values():
        combined.extend(filter_window(trades, start, end))
    combined.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return compute_metrics(combined)


def print_profile_summary(profile_name: str, results: dict[float, dict], portfolio_results: dict[float, dict]) -> None:
    print(f"\n{profile_name}")
    print("=" * len(profile_name))
    for gate_pct in VWAP_GATES:
        label = "baseline" if gate_pct == 0 else f"vwap>={gate_pct:.0f}%ATR"
        trades = results[gate_pct]["trades"]
        wf = results[gate_pct]["wf"]
        holdout_m = compute_metrics(filter_window(trades, HOLDOUT_START, END_DATE))
        print(f"\n  {label}")
        print(f"    full    {metrics_line(trades, FULL_START, END_DATE)}")
        print(f"    recent  {metrics_line(trades, RECENT_START, END_DATE)}")
        print(
            f"    holdout {holdout_m['total_trades']:>4} tr | WR {holdout_m['win_rate']:.1%} | "
            f"R {holdout_m['total_r']:>7.1f} | Sharpe {holdout_m['sharpe_ratio']:.2f} | Calmar {holdout_m['calmar_ratio']:.2f}"
        )
        oos_m = wf.combined_oos_metrics
        print(
            f"    wf oos  {oos_m['total_trades']:>4} tr | WR {oos_m['win_rate']:.1%} | "
            f"R {oos_m['total_r']:>7.1f} | Sharpe {oos_m['sharpe_ratio']:.2f} | "
            f"Calmar {oos_m['calmar_ratio']:.2f} | WFE {wf.walk_forward_efficiency:.2f}"
        )
        pm = portfolio_results[gate_pct]
        print(
            f"    profile {pm['total_trades']:>4} tr | WR {pm['win_rate']:.1%} | "
            f"R {pm['total_r']:>7.1f} | Sharpe {pm['sharpe_ratio']:.2f} | Calmar {pm['calmar_ratio']:.2f}"
        )


def main() -> None:
    t0 = time.time()
    print("NQ_NY VWAP Distance Gate — FAST vs FAST_V2")
    print("=" * 80)

    # Load all symbols needed across both profiles once.
    symbols = {"NQ", "ES", "GC"}
    data_cache = {}
    print("\nLoading data...")
    for symbol in sorted(symbols):
        df_5m = load_5m_data(f"{symbol}_5m.parquet", start=FULL_START, end=END_DATE)
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet", start=FULL_START, end=END_DATE)
        data_cache[symbol] = {"5m": df_5m, "1m": df_1m, "maps": build_maps(df_5m, df_1m)}
        print(f"  {symbol}: 5m={len(df_5m):,}, 1m={len(df_1m):,}")

    for profile_name in PROFILES:
        print(f"\nRunning profile {profile_name}...")
        legs = build_profile_legs(profile_name)

        configs_by_symbol: dict[str, list[StrategyConfig]] = {symbol: [] for symbol in symbols}
        for leg in legs.values():
            configs_by_symbol[leg.symbol].append(leg.config)
        ny_leg = legs["NQ_NY"]
        for gate_pct in VWAP_GATES:
            configs_by_symbol["NQ"].append(
                with_overrides(ny_leg.config, min_vwap_distance_atr_pct=gate_pct)
            )

        signal_cache_by_symbol: dict[str, dict] = {}
        for symbol, configs in configs_by_symbol.items():
            if not configs:
                continue
            print(f"  Pre-building signal cache for {symbol} ({len(configs)} configs)...")
            signal_cache_by_symbol[symbol] = build_signal_cache(data_cache[symbol]["5m"], configs)

        # Baseline all legs once for portfolio recombination.
        base_leg_trades: dict[str, list[TradeResult]] = {}
        for leg_name, leg in legs.items():
            df_5m = data_cache[leg.symbol]["5m"]
            df_1m = data_cache[leg.symbol]["1m"]
            print(f"  Baseline leg {leg_name}...")
            trades = run_backtest(
                df_5m,
                leg.config,
                start_date=FULL_START,
                end_date=END_DATE,
                df_1m=df_1m,
                _maps=data_cache[leg.symbol]["maps"],
                _signal_cache=signal_cache_by_symbol[leg.symbol],
            )
            if leg.excluded_dow:
                trades = apply_dow_filter(trades, set(leg.excluded_dow))
            trades = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            trades.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
            base_leg_trades[leg_name] = trades

        nq_5m = data_cache["NQ"]["5m"]
        nq_1m = data_cache["NQ"]["1m"]
        nq_maps = data_cache["NQ"]["maps"]
        nq_signal_cache = signal_cache_by_symbol["NQ"]

        results: dict[float, dict] = {}
        portfolio_results: dict[float, dict] = {}

        for gate_pct in VWAP_GATES:
            label = "baseline" if gate_pct == 0 else f"vwap>={gate_pct:.0f}%ATR"
            print(f"  Running NQ_NY {label}...")
            ny_trades = run_leg(
                ny_leg.config,
                nq_5m,
                nq_1m,
                ny_leg.excluded_dow,
                nq_maps,
                nq_signal_cache,
                min_vwap_distance_atr_pct=gate_pct,
            )
            print(f"  Walk-forward NQ_NY {label}...")
            wf = run_fixed_wf(ny_leg.config, nq_5m, nq_1m, ny_leg.excluded_dow, gate_pct)
            results[gate_pct] = {"trades": ny_trades, "wf": wf}

            profile_trade_map = dict(base_leg_trades)
            profile_trade_map["NQ_NY"] = ny_trades
            portfolio_results[gate_pct] = combined_profile_metrics(profile_trade_map, FULL_START, END_DATE)

        print_profile_summary(profile_name, results, portfolio_results)

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
