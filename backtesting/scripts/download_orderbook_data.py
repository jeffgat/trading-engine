#!/usr/bin/env python3
"""Download historical DataBento order-book data for futures research.

Defaults are tuned for the LSI impulse project:

- dataset: GLBX.MDP3
- schema: mbp-10 by default; mbp-1 is supported for top-of-book velocity tests
- symbology: continuous contracts (for example NQ.c.0)
- storage: compressed DBN under data/raw/orderbook/

MBP-1 is sufficient for best-bid/ask midpoint velocity. MBP-10 remains useful
for deeper depth/absorption variants because it carries top-10 levels while
staying much smaller than full MBO.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "data" / "raw" / "orderbook"
DATASET = "GLBX.MDP3"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

CONTINUOUS_SYMBOL_MAP = {
    "NQ": "NQ.c.0",
    "MNQ": "MNQ.c.0",
    "ES": "ES.c.0",
    "MES": "MES.c.0",
    "YM": "YM.c.0",
    "MYM": "MYM.c.0",
    "RTY": "RTY.c.0",
    "GC": "GC.v.0",
    "MGC": "MGC.v.0",
    "CL": "CL.c.0",
    "MCL": "MCL.c.0",
    "SI": "SI.v.0",
    "6B": "6B.c.0",
}

PARENT_SYMBOL_MAP = {
    symbol: f"{symbol}.FUT"
    for symbol in CONTINUOUS_SYMBOL_MAP
}


@dataclass(frozen=True)
class DownloadChunk:
    symbol: str
    databento_symbol: str
    schema: str
    stype_in: str
    start: str
    end: str
    output_path: str


def get_api_key() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=True)
        except ImportError:
            with env_path.open() as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip().strip("\"'")

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit(
            "ERROR: DATABENTO_API_KEY is not set. Add it to backtesting/.env or export it in this shell."
        )
    return key


def parse_hhmm(value: str) -> dtime:
    try:
        hh, mm = value.split(":", 1)
        return dtime(int(hh), int(mm))
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Expected HH:MM, got {value!r}") from exc


def resolve_symbol(symbol: str, stype_in: str) -> str:
    symbol = symbol.upper()
    if stype_in == "continuous":
        return CONTINUOUS_SYMBOL_MAP[symbol]
    if stype_in == "parent":
        return PARENT_SYMBOL_MAP[symbol]
    return symbol


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp_to_et(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ET)
    return ts.astimezone(ET)


def chunk_file_name(
    *,
    symbol: str,
    schema: str,
    stype_in: str,
    start_et: datetime,
    end_et: datetime,
    limit: int | None,
) -> str:
    safe_schema = schema.replace("-", "")
    limit_part = f"_limit{limit}" if limit else ""
    return (
        f"{symbol}_{safe_schema}_{stype_in}_"
        f"{start_et:%Y%m%d_%H%M%S}_to_{end_et:%Y%m%d_%H%M%S}_ET"
        f"{limit_part}.dbn.zst"
    )


def build_rth_chunks(
    *,
    symbol: str,
    databento_symbol: str,
    schema: str,
    stype_in: str,
    start_date: date,
    end_date: date,
    rth_start: dtime,
    rth_end: dtime,
    output_dir: Path,
    limit: int | None,
) -> list[DownloadChunk]:
    chunks: list[DownloadChunk] = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        start_et = datetime.combine(day, rth_start, tzinfo=ET)
        end_et = datetime.combine(day, rth_end, tzinfo=ET)
        if end_et <= start_et:
            raise ValueError("rth_end must be after rth_start for RTH-only downloads")
        output_path = output_dir / chunk_file_name(
            symbol=symbol,
            schema=schema,
            stype_in=stype_in,
            start_et=start_et,
            end_et=end_et,
            limit=limit,
        )
        chunks.append(
            DownloadChunk(
                symbol=symbol,
                databento_symbol=databento_symbol,
                schema=schema,
                stype_in=stype_in,
                start=utc_iso(start_et),
                end=utc_iso(end_et),
                output_path=str(output_path),
            )
        )
    return chunks


def build_calendar_chunks(
    *,
    symbol: str,
    databento_symbol: str,
    schema: str,
    stype_in: str,
    start_date: date,
    end_date: date,
    chunk_days: int,
    output_dir: Path,
    limit: int | None,
) -> list[DownloadChunk]:
    chunks: list[DownloadChunk] = []
    current = start_date
    while current < end_date:
        chunk_end = min(current + timedelta(days=chunk_days), end_date)
        start_et = datetime.combine(current, dtime(0, 0), tzinfo=ET)
        end_et = datetime.combine(chunk_end, dtime(0, 0), tzinfo=ET)
        output_path = output_dir / chunk_file_name(
            symbol=symbol,
            schema=schema,
            stype_in=stype_in,
            start_et=start_et,
            end_et=end_et,
            limit=limit,
        )
        chunks.append(
            DownloadChunk(
                symbol=symbol,
                databento_symbol=databento_symbol,
                schema=schema,
                stype_in=stype_in,
                start=utc_iso(start_et),
                end=utc_iso(end_et),
                output_path=str(output_path),
            )
        )
        current = chunk_end
    return chunks


def build_window_csv_chunks(
    *,
    windows_csv: Path,
    requested_symbols: list[str],
    schema: str,
    stype_in: str,
    output_root: Path,
    limit: int | None,
) -> list[DownloadChunk]:
    chunks: list[DownloadChunk] = []
    with windows_csv.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{windows_csv} is empty")
        required = {"start", "end"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{windows_csv} missing required columns: {sorted(missing)}")

        for row_idx, row in enumerate(reader, start=2):
            row_symbol = (row.get("symbol") or "").strip().upper()
            symbols = [row_symbol] if row_symbol else requested_symbols
            if not symbols:
                raise ValueError(
                    f"{windows_csv}:{row_idx} has no symbol column value; "
                    "provide a symbol column or positional symbols."
                )
            start_et = parse_timestamp_to_et(row["start"].strip())
            end_et = parse_timestamp_to_et(row["end"].strip())
            if end_et <= start_et:
                raise ValueError(f"{windows_csv}:{row_idx} end must be after start")

            for symbol in symbols:
                if stype_in in {"continuous", "parent"} and symbol not in CONTINUOUS_SYMBOL_MAP:
                    raise ValueError(
                        f"Unsupported mapped symbol {symbol!r}; use --stype-in raw_symbol for custom symbols."
                    )
                databento_symbol = resolve_symbol(symbol, stype_in)
                output_dir = output_root / symbol / schema
                output_path = output_dir / chunk_file_name(
                    symbol=symbol,
                    schema=schema,
                    stype_in=stype_in,
                    start_et=start_et,
                    end_et=end_et,
                    limit=limit,
                )
                chunks.append(
                    DownloadChunk(
                        symbol=symbol,
                        databento_symbol=databento_symbol,
                        schema=schema,
                        stype_in=stype_in,
                        start=utc_iso(start_et),
                        end=utc_iso(end_et),
                        output_path=str(output_path),
                    )
                )
    return chunks


def estimate_chunk(client, chunk: DownloadChunk, *, limit: int | None) -> dict:
    payload = {
        "dataset": DATASET,
        "symbols": [chunk.databento_symbol],
        "schema": chunk.schema,
        "stype_in": chunk.stype_in,
        "start": chunk.start,
        "end": chunk.end,
    }
    if limit:
        payload["limit"] = limit
    return {
        "record_count": client.metadata.get_record_count(**payload),
        "billable_size": client.metadata.get_billable_size(**payload),
        "cost": client.metadata.get_cost(**payload),
    }


def estimated_totals(rows: list[dict]) -> dict:
    totals = {"record_count": 0, "billable_size": 0, "cost": 0.0}
    for row in rows:
        totals["record_count"] += int(row.get("record_count", 0) or 0)
        totals["billable_size"] += int(row.get("billable_size", 0) or 0)
        totals["cost"] += float(row.get("cost", 0.0) or 0.0)
    return totals


def print_estimated_totals(totals: dict) -> None:
    print()
    print("Estimated totals")
    print(f"  records:       {totals['record_count']:,}")
    print(f"  billable size: {totals['billable_size'] / 1_000_000_000:.3f} GB")
    print(f"  cost:          ${totals['cost']:.4f}")


def download_chunk(client, chunk: DownloadChunk, *, limit: int | None, force: bool, retries: int) -> dict:
    path = Path(chunk.output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return {"status": "skipped_exists", "bytes": path.stat().st_size}

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    kwargs = {
        "dataset": DATASET,
        "symbols": [chunk.databento_symbol],
        "schema": chunk.schema,
        "stype_in": chunk.stype_in,
        "start": chunk.start,
        "end": chunk.end,
    }
    if limit:
        kwargs["limit"] = limit

    t0 = time.time()
    attempts = max(1, retries + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            store = client.timeseries.get_range(**kwargs)
            store.to_file(tmp_path, compression="zstd")
            tmp_path.replace(path)
            last_exc = None
            break
        except Exception as exc:  # DataBento/network failures can be intermittent on long sparse batches.
            last_exc = exc
            if tmp_path.exists():
                tmp_path.unlink()
            if "account_insufficient_funds" in str(exc) or str(exc).startswith("402 "):
                raise
            if attempt >= attempts:
                raise
            sleep_seconds = min(30, 2 ** attempt)
            print(
                f"  attempt {attempt}/{attempts} failed: {exc}; retrying in {sleep_seconds}s",
                flush=True,
            )
            time.sleep(sleep_seconds)
    if last_exc is not None:
        raise last_exc
    return {
        "status": "downloaded",
        "seconds": round(time.time() - t0, 3),
        "bytes": path.stat().st_size,
    }


def append_manifest(output_dir: Path, row: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "manifest.jsonl"
    with manifest.open("a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download DataBento order-book data as compressed DBN.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbols", nargs="*", help="Symbols such as NQ, ES, GC.")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD in America/New_York.")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD, exclusive, in America/New_York.")
    parser.add_argument("--schema", default="mbp-10", choices=["mbp-10", "mbp-1", "mbo", "tbbo", "trades"])
    parser.add_argument("--stype-in", default="continuous", choices=["continuous", "parent", "raw_symbol"])
    parser.add_argument("--rth-only", action="store_true", help="Download one ET RTH window per weekday.")
    parser.add_argument("--rth-start", type=parse_hhmm, default=dtime(8, 30), help="ET start for --rth-only.")
    parser.add_argument("--rth-end", type=parse_hhmm, default=dtime(16, 0), help="ET end for --rth-only.")
    parser.add_argument("--chunk-days", type=int, default=1, help="Calendar days per chunk when not using --rth-only.")
    parser.add_argument(
        "--windows-csv",
        type=Path,
        default=None,
        help="CSV with start/end and optional symbol columns. Naive times are interpreted as America/New_York.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional record limit for smoke tests.")
    parser.add_argument("--cost-only", action="store_true", help="Estimate metadata only; do not download.")
    parser.add_argument("--skip-estimate", action="store_true", help="Skip record/size/cost metadata calls.")
    parser.add_argument(
        "--skip-existing-estimate",
        action="store_true",
        help="When a target DBN file already exists and --force is not set, omit it from cost totals/downloads.",
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=None,
        help="Abort before any download if estimated new cost is above this dollar amount.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing DBN files.")
    parser.add_argument("--retries", type=int, default=2, help="Retry failed downloads this many times.")
    args = parser.parse_args()

    start_date = end_date = None
    if args.windows_csv is None:
        if args.start is None or args.end is None:
            raise SystemExit("--start and --end are required unless --windows-csv is provided")
        start_date = parse_date(args.start)
        end_date = parse_date(args.end)
        if end_date <= start_date:
            raise SystemExit("--end must be after --start")

    try:
        import databento as db
    except ImportError as exc:
        raise SystemExit("ERROR: databento is not installed. Run `uv sync` in backtesting/.") from exc

    client = db.Historical(get_api_key())
    requested_symbols = [raw.upper() for raw in args.symbols]
    if args.windows_csv is None and not requested_symbols:
        raise SystemExit("Provide at least one symbol, or use --windows-csv with a symbol column.")

    if args.windows_csv is not None:
        all_chunks = build_window_csv_chunks(
            windows_csv=args.windows_csv,
            requested_symbols=requested_symbols,
            schema=args.schema,
            stype_in=args.stype_in,
            output_root=OUTPUT_ROOT,
            limit=args.limit,
        )
    else:
        all_chunks = []
        for symbol in requested_symbols:
            if args.stype_in in {"continuous", "parent"} and symbol not in CONTINUOUS_SYMBOL_MAP:
                raise SystemExit(f"Unsupported mapped symbol {symbol!r}. Use --stype-in raw_symbol for custom symbols.")
            databento_symbol = resolve_symbol(symbol, args.stype_in)
            output_dir = OUTPUT_ROOT / symbol / args.schema
            if args.rth_only:
                chunks = build_rth_chunks(
                    symbol=symbol,
                    databento_symbol=databento_symbol,
                    schema=args.schema,
                    stype_in=args.stype_in,
                    start_date=start_date,
                    end_date=end_date,
                    rth_start=args.rth_start,
                    rth_end=args.rth_end,
                    output_dir=output_dir,
                    limit=args.limit,
                )
            else:
                chunks = build_calendar_chunks(
                    symbol=symbol,
                    databento_symbol=databento_symbol,
                    schema=args.schema,
                    stype_in=args.stype_in,
                    start_date=start_date,
                    end_date=end_date,
                    chunk_days=max(1, args.chunk_days),
                    output_dir=output_dir,
                    limit=args.limit,
                )
            all_chunks.extend(chunks)

    skipped_existing = []
    if args.skip_existing_estimate and not args.force:
        pending_chunks = []
        for chunk in all_chunks:
            if Path(chunk.output_path).exists():
                skipped_existing.append(chunk)
            else:
                pending_chunks.append(chunk)
        all_chunks = pending_chunks

    print("DataBento order-book download")
    print(f"  dataset:  {DATASET}")
    print(f"  schema:   {args.schema}")
    print(f"  stype_in: {args.stype_in}")
    print(f"  chunks:   {len(all_chunks)}")
    if skipped_existing:
        print(f"  skipped existing exact files: {len(skipped_existing)}")
    if args.max_cost is not None:
        print(f"  max cost: ${args.max_cost:.2f}")
    print(f"  output:   {OUTPUT_ROOT}")
    print()

    estimate_rows: list[dict] = []
    for idx, chunk in enumerate(all_chunks, start=1):
        row = {"chunk": idx, **asdict(chunk)}
        print(f"[{idx}/{len(all_chunks)}] {chunk.symbol} {chunk.start} -> {chunk.end}")
        if not args.skip_estimate:
            estimate = estimate_chunk(client, chunk, limit=args.limit)
            row.update(estimate)
            print(
                "  estimate: "
                f"{estimate['record_count']:,} records, "
                f"{estimate['billable_size'] / 1_000_000_000:.3f} GB billable, "
                f"${estimate['cost']:.4f}"
            )
        estimate_rows.append(row)

    totals = estimated_totals(estimate_rows)
    if not args.skip_estimate:
        print_estimated_totals(totals)

    if args.max_cost is not None and not args.skip_estimate and totals["cost"] > args.max_cost:
        print()
        print(
            f"ABORTED: estimated cost ${totals['cost']:.4f} exceeds "
            f"--max-cost ${args.max_cost:.2f}. No download was started."
        )
        return 2

    for row in estimate_rows:
        chunk = DownloadChunk(
            symbol=row["symbol"],
            databento_symbol=row["databento_symbol"],
            schema=row["schema"],
            stype_in=row["stype_in"],
            start=row["start"],
            end=row["end"],
            output_path=row["output_path"],
        )
        if args.cost_only:
            row["status"] = "estimated"
            append_manifest(Path(chunk.output_path).parent, row)
            continue

        result = download_chunk(client, chunk, limit=args.limit, force=args.force, retries=args.retries)
        row.update(result)
        append_manifest(Path(chunk.output_path).parent, row)
        print(f"  {result['status']}: {result.get('bytes', 0) / 1_000_000:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
