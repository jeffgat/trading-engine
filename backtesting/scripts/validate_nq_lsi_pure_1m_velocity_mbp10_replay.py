#!/usr/bin/env python3
"""Replay fetched DBN order-book files through the live pure 1m velocity sizer.

This validates the implementation path that live trading will use:

1. raw DataBento MBP-1/MBP-10 records
2. top-of-book samples
3. OrderbookFeatureCache
4. frozen OrderbookVelocityTierSizer

The pure 1m velocity survivor only needs best bid/ask, so MBP-1 should be able
to reproduce the same feature path as MBP-10. The default mode checks one
holdout trade from each frozen tier so the test is fast while still covering
low/mid/high behavior. Use ``--sample-mode all`` for a full holdout replay.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import databento as db
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
EXECUTION_SRC = REPO_ROOT / "execution" / "src"
if str(EXECUTION_SRC) not in sys.path:
    sys.path.insert(0, str(EXECUTION_SRC))

from trader.orderbook_features import (  # noqa: E402
    DynamicSizingContext,
    OrderbookFeatureCache,
    OrderbookVelocityTierSizer,
)

import download_orderbook_data as dl  # noqa: E402


DEFAULT_SCHEMA = "mbp-10"
RUN_SLUG_TEMPLATE = "nq_ny_lsi_pure_1m_velocity_{safe_schema}_replay_validation_20260516"
DEFAULT_REPLAY_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_risk_tiers_20260515"
    / "trade_risk_tier_replay.csv"
)
DEFAULT_WINDOWS_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_pure_1m_mbp10_fetch_20260516"
    / "holdout_morning_prefix_windows.csv"
)

FEATURE = "confirm_last_10s_mid_velocity_ticks_per_second"
OVERLAY = "pure_1m_long_confirm_last_velocity"
CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"
WEIGHT_PROFILE = "tier_0p5_1_1p5"
SUPPORTED_SCHEMAS = ("mbp-1", "mbp-10")


@dataclass(frozen=True)
class ReplayTrade:
    trade_uid: str
    date: str
    signal_start: datetime
    signal_end: datetime
    direction: int
    expected_feature_value: float
    expected_tier: str
    expected_weight: float
    r_multiple: float


def parse_signal_start(value: str) -> datetime:
    return pd.Timestamp(value).tz_localize(dl.ET).to_pydatetime()


def timeframe_delta(value: str) -> timedelta:
    if not value.endswith("m"):
        raise ValueError(f"Unsupported timeframe {value!r}")
    return timedelta(minutes=int(value[:-1]))


def load_trades(path: Path, *, sample_mode: str) -> list[ReplayTrade]:
    frame = pd.read_csv(path)
    mask = (
        frame["candidate"].eq(CANDIDATE)
        & frame["overlay"].eq(OVERLAY)
        & frame["feature"].eq(FEATURE)
        & frame["weight_profile"].eq(WEIGHT_PROFILE)
        & frame["period"].eq("holdout")
    )
    selected = frame.loc[mask].drop_duplicates("trade_uid").copy()
    if selected.empty:
        raise SystemExit(f"No holdout rows found for {CANDIDATE} in {path}")

    if sample_mode == "representative":
        selected = (
            selected.sort_values(["feature_tier", "date", "signal_start"])
            .groupby("feature_tier", as_index=False)
            .head(1)
            .sort_values(["date", "signal_start"])
        )
    elif sample_mode != "all":
        raise ValueError(f"Unsupported sample mode {sample_mode!r}")

    trades: list[ReplayTrade] = []
    for row in selected.itertuples(index=False):
        start = parse_signal_start(row.signal_start)
        end = start + timeframe_delta(row.timeframe)
        trades.append(
            ReplayTrade(
                trade_uid=str(row.trade_uid),
                date=str(row.date),
                signal_start=start,
                signal_end=end,
                direction=int(row.direction),
                expected_feature_value=float(row.feature_value),
                expected_tier=str(row.feature_tier),
                expected_weight=float(row.risk_weight),
                r_multiple=float(row.r_multiple),
            )
        )
    return trades


def safe_schema_name(schema: str) -> str:
    return schema.replace("-", "")


def default_run_slug(schema: str) -> str:
    return RUN_SLUG_TEMPLATE.format(safe_schema=safe_schema_name(schema))


def default_output_dir(schema: str) -> Path:
    return ROOT / "data" / "results" / default_run_slug(schema)


def chunk_by_date(windows_csv: Path, *, schema: str) -> dict[str, dl.DownloadChunk]:
    chunks = dl.build_window_csv_chunks(
        windows_csv=windows_csv,
        requested_symbols=[],
        schema=schema,
        stype_in="continuous",
        output_root=dl.OUTPUT_ROOT,
        limit=None,
    )
    by_date: dict[str, dl.DownloadChunk] = {}
    for chunk in chunks:
        start_et = dl.parse_timestamp_to_et(chunk.start)
        by_date[start_et.date().isoformat()] = chunk
    return by_date


def ns_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC)


def decode_dbn_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0.0:
        return None
    return price / 1_000_000_000 if abs(price) >= 1_000_000.0 else price


def level_price(level: Any, *, pretty_attr: str, raw_attr: str) -> float | None:
    pretty = getattr(level, pretty_attr, None)
    if pretty is not None:
        return decode_dbn_price(pretty)
    return decode_dbn_price(getattr(level, raw_attr, None))


def replay_trade(trade: ReplayTrade, chunk: dl.DownloadChunk) -> dict[str, Any]:
    path = Path(chunk.output_path)
    if not path.exists():
        raise FileNotFoundError(path)

    cache = OrderbookFeatureCache(retention_seconds=90.0)
    sizer = OrderbookVelocityTierSizer()
    signal_end_utc = trade.signal_end.astimezone(UTC)
    signal_end_ns = int(signal_end_utc.timestamp() * 1_000_000_000)
    records_seen = 0
    samples_added = 0

    def on_record(record: Any) -> None:
        nonlocal records_seen, samples_added
        if int(record.ts_event) >= signal_end_ns:
            raise StopIteration
        records_seen += 1
        levels = getattr(record, "levels", None)
        if not levels:
            return
        top = levels[0]
        bid = level_price(top, pretty_attr="pretty_bid_px", raw_attr="bid_px")
        ask = level_price(top, pretty_attr="pretty_ask_px", raw_attr="ask_px")
        if bid is None or ask is None:
            return
        cache.add_top_of_book(
            symbol="NQ",
            timestamp=ns_to_datetime(int(record.ts_event)),
            bid=bid,
            ask=ask,
            instrument_id=int(record.instrument_id),
            raw_symbol="NQ.c.0",
        )
        samples_added += 1

    store = db.DBNStore.from_file(path)
    try:
        store.replay(on_record)
    except StopIteration:
        pass

    decision = sizer.decision_from_cache(
        DynamicSizingContext(
            symbol="NQ",
            direction=trade.direction,
            signal_start=trade.signal_start.astimezone(UTC),
            signal_end=signal_end_utc,
            config_name=CANDIDATE,
            session="NQ_NY_LSI",
        ),
        cache,
    )
    feature_diff = (
        None
        if decision.feature_value is None
        else float(decision.feature_value - trade.expected_feature_value)
    )
    return {
        **asdict(trade),
        "signal_start": trade.signal_start.isoformat(),
        "signal_end": trade.signal_end.isoformat(),
        "dbn_path": str(path),
        "dbn_bytes": path.stat().st_size,
        "records_seen": records_seen,
        "samples_added": samples_added,
        "actual_feature_value": decision.feature_value,
        "actual_tier": decision.tier,
        "actual_weight": decision.risk_weight,
        "coverage": decision.coverage,
        "sample_count": decision.sample_count,
        "active": decision.active,
        "reason": decision.reason,
        "feature_diff": feature_diff,
        "tier_match": decision.tier == trade.expected_tier,
        "weight_match": abs(decision.risk_weight - trade.expected_weight) < 1e-12,
        "feature_match": feature_diff is not None and abs(feature_diff) < 1e-9,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-csv", type=Path, default=DEFAULT_REPLAY_CSV)
    parser.add_argument("--windows-csv", type=Path, default=DEFAULT_WINDOWS_CSV)
    parser.add_argument("--schema", choices=SUPPORTED_SCHEMAS, default=DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sample-mode", choices=["representative", "all"], default="representative")
    args = parser.parse_args()

    trades = load_trades(args.replay_csv, sample_mode=args.sample_mode)
    chunks = chunk_by_date(args.windows_csv, schema=args.schema)
    rows = []
    for trade in trades:
        chunk = chunks.get(trade.date)
        if chunk is None:
            raise SystemExit(f"No fetched morning-prefix chunk for {trade.date}")
        print(f"Replaying {trade.date} {trade.expected_tier} {trade.signal_start.isoformat()}", flush=True)
        rows.append(replay_trade(trade, chunk))

    output_dir = args.output_dir or default_output_dir(args.schema)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(rows)
    result_path = output_dir / "replay_validation.csv"
    result.to_csv(result_path, index=False)

    exact_feature_passed = bool(result["feature_match"].all())
    sizing_passed = bool(
        result["tier_match"].all()
        and result["weight_match"].all()
        and result["active"].all()
    )
    max_abs_feature_diff = None
    if result["feature_diff"].notna().any():
        max_abs_feature_diff = float(result["feature_diff"].abs().max())

    summary = {
        "run_slug": output_dir.name,
        "schema": args.schema,
        "sample_mode": args.sample_mode,
        "trades_checked": int(len(result)),
        "feature_matches": int(result["feature_match"].sum()),
        "tier_matches": int(result["tier_match"].sum()),
        "weight_matches": int(result["weight_match"].sum()),
        "exact_feature_passed": exact_feature_passed,
        "sizing_passed": sizing_passed,
        "all_passed": sizing_passed,
        "max_abs_feature_diff": max_abs_feature_diff,
        "output_csv": str(result_path),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if sizing_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
