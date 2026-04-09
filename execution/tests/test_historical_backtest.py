from __future__ import annotations

from datetime import datetime

import pandas as pd

from trader.engine import Bar
from trader.historical_backtest import (
    BACKTEST_REPORTING_RISK_USD,
    _build_config_dict,
    run_profile_backtest_sync,
)
from trader.main import ExecutionConfig


def test_build_config_dict_uses_backtest_reporting_risk() -> None:
    exec_config = ExecutionConfig(
        name="FAST_V1.1",
        session_overrides={
            "NQ_Asia": {
                "risk_usd": 400,
                "entry_start": "19:30",
                "entry_end": "23:00",
                "flat_start": "23:55",
                "flat_end": "04:00",
                "regime_gate": "bull_no_low_confidence",
                "regime_gates": ["block_full_medium_vol"],
            }
        },
        lsi_session_overrides={
            "NQ_Asia_LSI": {
                "risk_usd": 400,
                "entry_start": "19:30",
                "entry_end": "23:00",
                "flat_start": "23:55",
                "flat_end": "04:00",
                "regime_gates": ["block_full_medium_vol"],
                "lsi_variant": "legacy-LSI",
            }
        },
    )

    config = _build_config_dict("FAST_V1.1", exec_config)

    assert config["risk_usd"] == BACKTEST_REPORTING_RISK_USD
    assert config["nq_asia_risk_usd"] == 400
    assert config["nq_asia_lsi_risk_usd"] == 400
    assert config["nq_asia_regime_gates"] == ["bull_no_low_confidence", "block_full_medium_vol"]
    assert "nq_asia_regime_gate" not in config
    assert config["nq_asia_lsi_regime_gates"] == ["block_full_medium_vol"]
    assert config["nq_asia_lsi_regime_gate"] == "block_full_medium_vol"
    assert config["nq_asia_lsi_lsi_variant"] == "legacy-LSI"


def test_run_profile_backtest_wires_daily_history_provider(monkeypatch) -> None:
    class FakeState:
        value = "flat"

    class FakeEngine:
        def __init__(self) -> None:
            self.name = "NQ_NY"
            self.atr_length = 14
            self.state = FakeState()
            self.on_trade_exit = None
            self.bar_count = 0

        async def on_bar(self, bar, _atr) -> None:
            self.bar_count += 1

        async def on_tick(self, _bar, _atr) -> None:
            return None

    engine = FakeEngine()
    provider_calls: list = []

    monkeypatch.setattr(
        "trader.historical_backtest.load_exec_configs",
        lambda _config: [ExecutionConfig(name="TEST", session_overrides={"NQ_NY": {}})],
    )
    monkeypatch.setattr(
        "trader.historical_backtest.build_engines",
        lambda *_args, **_kwargs: ([engine], {"NQ.FUT": [engine]}, {"NQ.FUT": {14}}),
    )
    monkeypatch.setattr(
        "trader.historical_backtest.build_lsi_engines",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "trader.historical_backtest._seed_daily_bars",
        lambda _symbol, _replay_start: [
            (pd.Timestamp("2025-01-02").date(), 100.0, 101.0, 99.0, 100.5),
            (pd.Timestamp("2025-01-03").date(), 100.5, 101.5, 100.0, 101.0),
        ],
    )
    monkeypatch.setattr(
        "trader.historical_backtest._read_parquet_frame",
        lambda *_args, **_kwargs: pd.DataFrame(
            {
                "open": [101.0],
                "high": [102.0],
                "low": [100.5],
                "close": [101.5],
                "volume": [1000],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2025-01-06 09:30", tz="America/New_York")]),
        ),
    )
    monkeypatch.setattr(
        "trader.historical_backtest.set_daily_history_provider",
        lambda provider: provider_calls.append(provider),
    )

    result = run_profile_backtest_sync(
        config={"risk": {}, "sessions": {}},
        profile_name="TEST",
        start_date="2025-01-06",
        end_date="2025-01-06",
        latest_data_ts=datetime(2025, 1, 6, 9, 35),
    )

    assert engine.bar_count == 1
    assert result["trades"] == []
    assert callable(provider_calls[0])
    assert provider_calls[-1] is None
    assert provider_calls[0]("NQ.FUT") == [
        (pd.Timestamp("2025-01-02").date(), 100.0, 101.0, 99.0, 100.5),
        (pd.Timestamp("2025-01-03").date(), 100.5, 101.5, 100.0, 101.0),
        (pd.Timestamp("2025-01-06").date(), 101.0, 102.0, 100.5, 101.5),
    ]
