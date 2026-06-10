from __future__ import annotations

from datetime import datetime

import pandas as pd

from trader.engine import Bar
from trader.historical_backtest import (
    BACKTEST_REPORTING_RISK_USD,
    _build_config_dict,
    _timeframe_for_minutes,
    run_profile_backtest_sync,
)
from trader.main import ExecutionConfig
from trader.orderbook_features import DynamicSizingDecision


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
                "max_prior_rolling_atr_pct": 1.62,
                "max_orb_range_pct": 0.46,
                "excluded_dow": None,
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
                "lsi_confirmation_mode": "cisd",
                "lsi_stop_mode": "atr_pct",
                "stop_atr_pct": 15.0,
                "base_bar_minutes": 1,
            }
        },
    )

    config = _build_config_dict("FAST_V1.1", exec_config)

    assert config["risk_usd"] == BACKTEST_REPORTING_RISK_USD
    assert config["nq_asia_risk_usd"] == 400
    assert config["nq_asia_max_prior_rolling_atr_pct"] == 1.62
    assert config["nq_asia_max_orb_range_pct"] == 0.46
    assert config["nq_asia_excluded_dow"] is None
    assert config["nq_asia_lsi_risk_usd"] == 400
    assert config["nq_asia_regime_gates"] == ["bull_no_low_confidence", "block_full_medium_vol"]
    assert "nq_asia_regime_gate" not in config
    assert config["nq_asia_lsi_regime_gates"] == ["block_full_medium_vol"]
    assert config["nq_asia_lsi_regime_gate"] == "block_full_medium_vol"
    assert config["nq_asia_lsi_lsi_variant"] == "legacy-LSI"
    assert config["nq_asia_lsi_lsi_confirmation_mode"] == "cisd"
    assert config["nq_asia_lsi_lsi_stop_mode"] == "atr_pct"
    assert config["nq_asia_lsi_stop_atr_pct"] == 15.0
    assert config["nq_asia_lsi_base_bar_minutes"] == 1


def test_build_config_dict_resolves_aliased_session_defaults() -> None:
    exec_config = ExecutionConfig(
        name="ALPHA_V2",
        session_overrides={
            "NQ_NY-RR2": {
                "base_session": "NQ_NY",
                "risk_usd": 250,
                "rr": 2.0,
                "tp1_ratio": 1.0,
                "exit_mode": "single_target",
                "max_prior_rolling_atr_pct": 1.6228,
                "max_orb_range_pct": 0.4658,
                "excluded_dow": None,
            }
        },
    )

    config = _build_config_dict("ALPHA_V2", exec_config)

    assert config["nq_ny_rr2_base_session"] == "NQ_NY"
    assert config["nq_ny_rr2_orb_window"] == "09:30-09:45"
    assert config["nq_ny_rr2_entry_window"] == "09:45-12:00"
    assert config["nq_ny_rr2_flat_window"] == "15:30-16:00"
    assert config["nq_ny_rr2_risk_usd"] == 250
    assert config["nq_ny_rr2_rr"] == 2.0
    assert config["nq_ny_rr2_tp1_ratio"] == 1.0
    assert config["nq_ny_rr2_exit_mode"] == "single_target"
    assert config["nq_ny_rr2_max_prior_rolling_atr_pct"] == 1.6228
    assert config["nq_ny_rr2_max_orb_range_pct"] == 0.4658
    assert config["nq_ny_rr2_excluded_dow"] is None
    assert config["nq_ny_rr2_exec_ticker"] == "MNQ"


def test_timeframe_for_minutes_supports_3m_lsi_probe() -> None:
    assert _timeframe_for_minutes(1) == "1m"
    assert _timeframe_for_minutes(3) == "3m"
    assert _timeframe_for_minutes(5) == "5m"


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


def test_run_profile_backtest_attaches_shadow_dynamic_sizing_provider(monkeypatch) -> None:
    class FakeState:
        value = "flat"

    class FakeLsiEngine:
        def __init__(self) -> None:
            self.name = "NQ_NY_LSI_PURE_1M"
            self.atr_length = 14
            self.base_bar_minutes = 5
            self.state = FakeState()
            self.on_trade_exit = None
            self.dynamic_sizing_provider = None
            self.dynamic_sizing_shadow = False

        async def on_bar(self, _bar, _atr) -> None:
            return None

        async def on_tick(self, _bar, _atr) -> None:
            return None

    engine = FakeLsiEngine()

    def provider(_context):
        return DynamicSizingDecision(
            feature="confirm_last_10s_mid_velocity_ticks_per_second",
            risk_weight=1.5,
            tier="high",
            active=True,
            reason="test",
        )

    monkeypatch.setattr(
        "trader.historical_backtest.load_exec_configs",
        lambda _config: [ExecutionConfig(name="TEST", lsi_session_overrides={"NQ_NY_LSI_PURE_1M": {}})],
    )
    monkeypatch.setattr(
        "trader.historical_backtest.build_engines",
        lambda *_args, **_kwargs: ([], {"NQ.FUT": [engine]}, {"NQ.FUT": {14}}),
    )
    monkeypatch.setattr(
        "trader.historical_backtest.build_lsi_engines",
        lambda *_args, **_kwargs: [engine],
    )
    monkeypatch.setattr(
        "trader.historical_backtest._seed_daily_bars",
        lambda _symbol, _replay_start: [],
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

    result = run_profile_backtest_sync(
        config={"risk": {}, "sessions": {}},
        profile_name="TEST",
        start_date="2025-01-06",
        end_date="2025-01-06",
        latest_data_ts=datetime(2025, 1, 6, 9, 35),
        dynamic_sizing_providers={"NQ_NY_LSI_PURE_1M": provider},
        dynamic_sizing_shadow=True,
    )

    assert result["trades"] == []
    assert engine.dynamic_sizing_provider is provider
    assert engine.dynamic_sizing_shadow is True
