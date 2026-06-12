from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trader.contracts import (
    cleanup_traderspost_contracts,
    explicit_traderspost_contract,
    expand_year_code,
    parse_contract,
)


ET = ZoneInfo("America/New_York")


def test_maps_databento_nq_contract_to_matching_micro_traderspost_contract():
    assert explicit_traderspost_contract(
        signal_contract="NQU6",
        exec_root="MNQ",
        as_of=datetime(2026, 6, 12, tzinfo=ET),
    ) == "MNQU2026"


def test_maps_databento_es_contract_to_matching_micro_traderspost_contract():
    assert explicit_traderspost_contract(
        signal_contract="ESM6",
        exec_root="MES",
        as_of=datetime(2026, 6, 12, tzinfo=ET),
    ) == "MESM2026"


def test_rejects_cross_underlying_contract_mapping():
    with pytest.raises(ValueError, match="does not match"):
        explicit_traderspost_contract(
            signal_contract="NQU6",
            exec_root="MES",
            as_of=datetime(2026, 6, 12, tzinfo=ET),
        )


def test_one_digit_year_uses_nearest_decade_to_asof():
    assert expand_year_code("6", as_of=datetime(2026, 6, 12, tzinfo=ET)) == 2026
    assert parse_contract("NQH5", as_of=datetime(2026, 1, 1, tzinfo=ET)).year == 2025


def test_cleanup_candidates_include_adjacent_rollover_contracts():
    assert cleanup_traderspost_contracts(
        exec_root="MES",
        contracts=["ESU6"],
        as_of=datetime(2026, 6, 12, tzinfo=ET),
    ) == ["MESU2026", "MESM2026", "MESZ2026", "MES"]


def test_numeric_roots_parse_for_future_resolver_coverage():
    assert explicit_traderspost_contract(
        signal_contract="6EU6",
        exec_root="M6E",
        as_of=datetime(2026, 6, 12, tzinfo=ET),
    ) == "M6EU2026"
