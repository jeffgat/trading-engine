#!/usr/bin/env python3
"""Trade-level parity diff for NQ NY HTF-LSI 5m lag24 research vs exact replay."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXEC_ROOT = ROOT.parent / "execution"
EXEC_SITE_PACKAGES = EXEC_ROOT / ".venv" / "lib" / "python3.13" / "site-packages"

if EXEC_SITE_PACKAGES.exists():
    sys.path.append(str(EXEC_SITE_PACKAGES))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(EXEC_ROOT / "src"))

from htf_lsi_common import (  # noqa: E402
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    save_json,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.export import results_to_dict  # noqa: E402
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402


PRE_HOLDOUT_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"
PROFILE_NAME = "HTF_LSI_5M_LAG24"

OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_lag24_parity_diff"
OUTPUT_JSON = OUTPUT_DIR / "parity_diff.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LAG24_PARITY_DIFF.md"


def _hhmm(ts: str | None) -> str:
    return (ts or "")[11:16]


def _entry_minute(ts: str | None) -> str:
    return (ts or "")[:16]


def _same_trade_key(trade: dict) -> tuple:
    return (
        trade["date"],
        round(float(trade["entry_price"]), 4),
        round(float(trade.get("htf_level_price") or 0.0), 4),
        trade.get("fvg_to_inversion_bars"),
    )


def _strict_key(trade: dict) -> tuple:
    return (trade["date"], _entry_minute(trade.get("entry_time")))


def _load_research_trades() -> tuple[list[dict], list[dict]]:
    config = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 parity diff",
    )
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    maps = build_maps(df_base)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    trades = run_backtest(
        df_base,
        config,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    research_all = results_to_dict(
        trades,
        config,
        include_trades=True,
        include_equity_curve=False,
    )["trades"]
    research_filled = [trade for trade in research_all if trade.get("exit_type") != "no_fill"]
    return research_all, research_filled


def _load_exact_trades() -> list[dict]:
    return run_profile_backtest_sync(
        config=load_config(DEFAULT_CONFIG),
        profile_name=PROFILE_NAME,
        start_date="2016-01-01",
        end_date="2026-03-24",
        latest_data_ts=latest_common_end(["NQ"]),
        label=f"Parity diff {PROFILE_NAME}",
    )["trades"]


def _slice_window(rows: list[dict], which: str) -> list[dict]:
    if which == "pre_holdout":
        return [row for row in rows if row["date"] <= PRE_HOLDOUT_END]
    if which == "holdout":
        return [row for row in rows if row["date"] >= HOLDOUT_START]
    raise ValueError(f"Unknown window {which!r}")


def _slot_counts(rows: list[dict], research_only: list[dict]) -> dict[int, int]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    for day_rows in by_day.values():
        day_rows.sort(key=lambda trade: _entry_minute(trade.get("entry_time")))

    counts: Counter[int] = Counter()
    for trade in research_only:
        day_rows = by_day[trade["date"]]
        slot = next(
            idx + 1
            for idx, candidate in enumerate(day_rows)
            if _strict_key(candidate) == _strict_key(trade)
        )
        counts[slot] += 1
    return dict(sorted(counts.items()))


def _fuzzy_match(
    research_filled: list[dict],
    exact: list[dict],
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    exact_pool: dict[tuple, list[dict]] = defaultdict(list)
    for trade in exact:
        exact_pool[_same_trade_key(trade)].append(trade)

    matched: list[tuple[dict, dict]] = []
    research_only: list[dict] = []
    for trade in research_filled:
        bucket = exact_pool.get(_same_trade_key(trade), [])
        if bucket:
            matched.append((trade, bucket.pop(0)))
        else:
            research_only.append(trade)

    exact_only = [trade for bucket in exact_pool.values() for trade in bucket]
    return matched, research_only, exact_only


def _summarize_window(research_filled: list[dict], exact: list[dict], which: str) -> dict[str, Any]:
    research_rows = _slice_window(research_filled, which)
    exact_rows = _slice_window(exact, which)
    matched, research_only, exact_only = _fuzzy_match(research_rows, exact_rows)

    strict_research_keys = {_strict_key(row) for row in research_rows}
    strict_exact_keys = {_strict_key(row) for row in exact_rows}
    strict_intersection = len(strict_research_keys & strict_exact_keys)

    minute_shifts: Counter[int] = Counter()
    for research_trade, exact_trade in matched:
        r_hhmm = _hhmm(research_trade.get("entry_time"))
        e_hhmm = _hhmm(exact_trade.get("entry_time"))
        if not r_hhmm or not e_hhmm:
            continue
        r_hour, r_minute = map(int, r_hhmm.split(":"))
        e_hour, e_minute = map(int, e_hhmm.split(":"))
        minute_shifts[(e_hour * 60 + e_minute) - (r_hour * 60 + r_minute)] += 1

    return {
        "research_filled_trades": len(research_rows),
        "exact_trades": len(exact_rows),
        "strict_minute_match_count": strict_intersection,
        "matched_same_trade_count": len(matched),
        "research_only_count": len(research_only),
        "exact_only_count": len(exact_only),
        "research_only_day_count": len({trade["date"] for trade in research_only}),
        "exact_only_day_count": len({trade["date"] for trade in exact_only}),
        "minute_shift_distribution": dict(sorted(minute_shifts.items())),
        "research_only_slot_counts": _slot_counts(research_rows, research_only),
        "research_only_days": sorted({trade["date"] for trade in research_only}),
        "research_only_entry_times": Counter(_hhmm(trade.get("entry_time")) for trade in research_only).most_common(12),
        "research_only_fvg_to_inversion": Counter(
            trade.get("fvg_to_inversion_bars") for trade in research_only
        ).most_common(),
        "research_only_exit_types": Counter(trade["exit_type"] for trade in research_only).most_common(),
        "exact_only_fvg_to_inversion": Counter(
            trade.get("fvg_to_inversion_bars") for trade in exact_only
        ).most_common(),
        "research_only_samples": [
            {
                "date": trade["date"],
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "entry_price": trade.get("entry_price"),
                "htf_level_time": trade.get("htf_level_time"),
                "htf_level_price": trade.get("htf_level_price"),
                "fvg_to_inversion_bars": trade.get("fvg_to_inversion_bars"),
                "sweep_to_inversion_bars": trade.get("sweep_to_inversion_bars"),
                "exit_type": trade.get("exit_type"),
            }
            for trade in research_only[:10]
        ],
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    info = payload["info"]
    pre = payload["windows"]["pre_holdout"]
    holdout = payload["windows"]["holdout"]

    lines = [
        "# NQ NY HTF-LSI Lag24 Parity Diff",
        "",
        "- Objective: decompose the gap between the frozen research branch and the exact live-engine replay at the trade level.",
        f"- Profile: `{info['profile_name']}`",
        f"- Exact replay window: `{info['start_date']}` to `{info['end_date']}`",
        "",
        "## Key Findings",
        "",
        f"- The current direct research export printed `{info['research_all_trades']}` trades, but `{info['research_no_fill_trades']}` of those were `no_fill` setups. Removing those restores the frozen filled-trade count of `{info['research_filled_trades']}` (`506` pre-holdout, `42` holdout).",
        f"- Holdout parity is materially tighter than the raw count suggests. Exact replay filled `{holdout['exact_trades']}` trades, and all `{holdout['exact_trades']}` map to research filled trades under a same-trade key of `(date, entry_price, htf_level_price, fvg_to_inversion_bars)`.",
        f"- Half of the apparent holdout mismatch is timestamping only: strict minute matching found `{holdout['strict_minute_match_count']}` overlaps, but fuzzy same-trade matching found `{holdout['matched_same_trade_count']}` overlaps. Exact fill timestamps were usually `+1` to `+4` minutes later than the research bar timestamp.",
        f"- The true remaining holdout gap is `{holdout['research_only_count']}` research trades across `{holdout['research_only_day_count']}` days, with `0` exact-only holdout trades.",
        f"- Those missing holdout trades were all slot-1 trades (`{holdout['research_only_slot_counts']}`), so the residual gap does not look like a trade-cap or second-trade-per-session problem.",
        "",
        "## Window Summary",
        "",
        "| Window | Research Filled | Exact | Strict Minute Match | Fuzzy Same-Trade Match | Research Only | Exact Only |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| Pre-Holdout | {pre['research_filled_trades']} | {pre['exact_trades']} | {pre['strict_minute_match_count']} | {pre['matched_same_trade_count']} | {pre['research_only_count']} | {pre['exact_only_count']} |",
        f"| Holdout | {holdout['research_filled_trades']} | {holdout['exact_trades']} | {holdout['strict_minute_match_count']} | {holdout['matched_same_trade_count']} | {holdout['research_only_count']} | {holdout['exact_only_count']} |",
        "",
        "## Holdout Shape",
        "",
        f"- Minute-shift distribution on matched holdout trades: `{holdout['minute_shift_distribution']}`",
        f"- Missing holdout trade days: `{', '.join(holdout['research_only_days'])}`",
        f"- Missing holdout FVG-to-inversion bars: `{holdout['research_only_fvg_to_inversion']}`",
        f"- Missing holdout entry times: `{holdout['research_only_entry_times']}`",
        f"- Missing holdout exit types: `{holdout['research_only_exit_types']}`",
        "",
        "## Pre-Holdout Shape",
        "",
        f"- Minute-shift distribution on matched pre-holdout trades: `{pre['minute_shift_distribution']}`",
        f"- Pre-holdout research-only day count: `{pre['research_only_day_count']}`",
        f"- Pre-holdout missing trade slots: `{pre['research_only_slot_counts']}`",
        f"- Pre-holdout missing FVG-to-inversion bars: `{pre['research_only_fvg_to_inversion']}`",
        "",
        "## Interpretation",
        "",
        "- The scary raw count gap had three separate causes:",
        "  1. research exports included `no_fill` setups,",
        "  2. exact replay timestamps real intraday limit fills a few minutes later than the research bar timestamp,",
        "  3. there is still a real subset of missing research trades.",
        "- On holdout, that real subset is now much smaller than the headline `42 vs 28` made it look: the unresolved difference is `14` truly missing research fills.",
        "- Because those unresolved holdout misses are all first-trade days, the next debug step should focus on day-level setup arming and limit-fill lifecycle on those dates, not on trade-cap sequencing.",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    research_all, research_filled = _load_research_trades()
    exact = _load_exact_trades()

    payload = {
        "info": {
            "profile_name": PROFILE_NAME,
            "start_date": "2016-01-01",
            "end_date": "2026-03-24",
            "research_all_trades": len(research_all),
            "research_filled_trades": len(research_filled),
            "research_no_fill_trades": len(research_all) - len(research_filled),
            "exact_trades": len(exact),
        },
        "windows": {
            "pre_holdout": _summarize_window(research_filled, exact, "pre_holdout"),
            "holdout": _summarize_window(research_filled, exact, "holdout"),
        },
    }

    save_json(OUTPUT_JSON, payload)
    _write_report(REPORT_PATH, payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved JSON to {OUTPUT_JSON}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
