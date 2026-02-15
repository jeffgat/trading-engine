"""Instrument definitions and registry."""

from __future__ import annotations

from ..config import Instrument

NQ = Instrument(
    symbol="NQ",
    point_value=20.0,
    min_tick=0.25,
    commission=0.05,
    data_file="NQ_5m.csv",
    exchange_tz="America/New_York",
)

MNQ = Instrument(
    symbol="MNQ",
    point_value=2.0,
    min_tick=0.25,
    commission=0.05,
    data_file="MNQ_5m.csv",
    exchange_tz="America/New_York",
)

ES = Instrument(
    symbol="ES",
    point_value=50.0,
    min_tick=0.25,
    commission=0.05,
    data_file="ES_5m.csv",
    exchange_tz="America/New_York",
)

_INSTRUMENTS: dict[str, Instrument] = {
    "NQ": NQ,
    "MNQ": MNQ,
    "ES": ES,
}


def get_instrument(symbol: str) -> Instrument:
    """Look up an instrument by symbol. Raises KeyError if not found."""
    key = symbol.upper()
    if key not in _INSTRUMENTS:
        raise KeyError(f"Unknown instrument: {symbol}. Available: {list(_INSTRUMENTS.keys())}")
    return _INSTRUMENTS[key]


def list_instruments() -> dict[str, Instrument]:
    """Return all registered instruments."""
    return dict(_INSTRUMENTS)
