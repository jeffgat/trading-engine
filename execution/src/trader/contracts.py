"""Futures contract helpers for aligning signal and broker contract months."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

MONTH_CODES = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}

UNDERLYING_ROOTS = {
    "NQ": "NQ",
    "MNQ": "NQ",
    "ES": "ES",
    "MES": "ES",
    "GC": "GC",
    "MGC": "GC",
    "CL": "CL",
    "MCL": "CL",
    "YM": "YM",
    "MYM": "YM",
    "RTY": "RTY",
    "M2K": "RTY",
    "SI": "SI",
    "SIL": "SI",
    "6E": "6E",
    "M6E": "6E",
    "6B": "6B",
    "M6B": "6B",
    "6J": "6J",
    "M6J": "6J",
}

QUARTERLY_UNDERLYINGS = {"NQ", "ES", "YM", "RTY"}
QUARTERLY_MONTH_CODES = ("H", "M", "U", "Z")
ALL_MONTH_CODES = tuple(MONTH_CODES.keys())

_CONTRACT_RE = re.compile(r"^([A-Z0-9]+)([FGHJKMNQUVXZ])(\d{1,4})$")


@dataclass(frozen=True)
class FuturesContract:
    raw: str
    root: str
    month_code: str
    year: int

    @property
    def month(self) -> int:
        return MONTH_CODES[self.month_code]


def _asof_year(as_of: datetime | date | None) -> int:
    if as_of is None:
        return datetime.now().year
    return as_of.year


def expand_year_code(year_code: str, *, as_of: datetime | date | None = None) -> int:
    """Expand a DataBento-style 1/2 digit futures year code to a full year."""
    code = str(year_code)
    if len(code) == 4:
        return int(code)
    if len(code) == 2:
        return 2000 + int(code)
    if len(code) != 1:
        raise ValueError(f"unsupported futures year code: {year_code!r}")

    digit = int(code)
    anchor = _asof_year(as_of)
    candidates = [year for year in range(anchor - 10, anchor + 11) if year % 10 == digit]
    if not candidates:
        return 2000 + digit
    return min(candidates, key=lambda year: (abs(year - anchor), year < anchor))


def parse_contract(raw: str, *, as_of: datetime | date | None = None) -> FuturesContract:
    """Parse a raw futures contract such as ``NQU6`` or ``MNQU2026``."""
    normalized = str(raw or "").strip().upper()
    match = _CONTRACT_RE.match(normalized)
    if match is None:
        raise ValueError(f"cannot parse futures contract: {raw!r}")
    root, month_code, year_code = match.groups()
    return FuturesContract(
        raw=normalized,
        root=root,
        month_code=month_code,
        year=expand_year_code(year_code, as_of=as_of),
    )


def underlying_root(root: str) -> str:
    """Return the canonical full-size underlying for a futures root."""
    normalized = str(root or "").strip().upper()
    return UNDERLYING_ROOTS.get(normalized, normalized)


def explicit_traderspost_contract(
    *,
    signal_contract: str,
    exec_root: str,
    as_of: datetime | date | None = None,
) -> str:
    """Map a DataBento raw signal contract to a TradersPost explicit ticker.

    Example:
        ``NQU6`` + ``MNQ`` -> ``MNQU2026``.
    """
    signal = parse_contract(signal_contract, as_of=as_of)
    exec_root_normalized = str(exec_root or "").strip().upper()
    try:
        explicit_exec = parse_contract(exec_root_normalized, as_of=as_of)
    except ValueError:
        explicit_exec = None
    if explicit_exec is not None:
        if (
            underlying_root(explicit_exec.root) != underlying_root(signal.root)
            or explicit_exec.month_code != signal.month_code
            or explicit_exec.year != signal.year
        ):
            raise ValueError(
                "explicit execution ticker %s does not match signal contract %s"
                % (exec_root_normalized, signal.raw)
            )
        return f"{explicit_exec.root}{explicit_exec.month_code}{explicit_exec.year}"

    if not exec_root_normalized:
        raise ValueError("missing execution root ticker")
    if underlying_root(exec_root_normalized) != underlying_root(signal.root):
        raise ValueError(
            "execution root %s does not match signal contract %s"
            % (exec_root_normalized, signal.raw)
        )
    return f"{exec_root_normalized}{signal.month_code}{signal.year}"


def contract_order_key(raw: str, *, as_of: datetime | date | None = None) -> tuple[int, int, str]:
    contract = parse_contract(raw, as_of=as_of)
    return (contract.year, contract.month, contract.root)


def month_cycle_for_root(root: str) -> tuple[str, ...]:
    """Return the likely listed month cycle for a futures root."""
    underlying = underlying_root(root)
    if underlying in QUARTERLY_UNDERLYINGS:
        return QUARTERLY_MONTH_CODES
    return ALL_MONTH_CODES


def adjacent_contract_month(
    month_code: str,
    year: int,
    *,
    root: str,
    step: int,
) -> tuple[str, int]:
    """Move one listed contract month forward/backward for a root."""
    months = month_cycle_for_root(root)
    normalized_month = str(month_code or "").upper()
    if normalized_month not in months:
        months = ALL_MONTH_CODES
    idx = months.index(normalized_month)
    next_idx = idx + step
    next_year = int(year)
    while next_idx < 0:
        next_idx += len(months)
        next_year -= 1
    while next_idx >= len(months):
        next_idx -= len(months)
        next_year += 1
    return months[next_idx], next_year


def cleanup_traderspost_contracts(
    *,
    exec_root: str,
    contracts: list[str | None] | tuple[str | None, ...],
    as_of: datetime | date | None = None,
    include_adjacent: bool = True,
    include_root: bool = True,
) -> list[str]:
    """Return explicit/root tickers worth flattening during manual cleanup.

    The list is deliberately conservative: known explicit contracts first,
    adjacent rollover months next, then the generic root. This gives emergency
    cleanup a chance to catch stale old-month orders during roll week.
    """
    root = str(exec_root or "").strip().upper()
    result: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        normalized = str(value or "").strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    parsed_signals: list[FuturesContract] = []
    for raw in contracts:
        raw_text = str(raw or "").strip().upper()
        if not raw_text:
            continue
        try:
            signal = parse_contract(raw_text, as_of=as_of)
        except ValueError:
            if raw_text == root:
                add(raw_text)
            continue

        if root and underlying_root(signal.root) == underlying_root(root):
            if signal.root == root:
                add(f"{signal.root}{signal.month_code}{signal.year}")
            else:
                add(
                    explicit_traderspost_contract(
                        signal_contract=signal.raw,
                        exec_root=root,
                        as_of=as_of,
                    )
                )
            parsed_signals.append(signal)

    if include_adjacent and root:
        for signal in parsed_signals:
            for step in (-1, 1):
                month_code, year = adjacent_contract_month(
                    signal.month_code,
                    signal.year,
                    root=root,
                    step=step,
                )
                add(f"{root}{month_code}{year}")

    if include_root:
        add(root)
    return result
