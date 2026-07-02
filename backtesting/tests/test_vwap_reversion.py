import pandas as pd

from orb_backtest.data.instruments import NQ
from orb_backtest.engine import vwap_simulator
from orb_backtest.engine.vwap_simulator import _VWAPSetupCandidate, run_vwap_backtest
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides


def test_vwap_backtest_hierarchical_path_uses_neutral_shared_sim_defaults(monkeypatch):
    idx_5m = pd.date_range("2025-01-02 09:30", periods=8, freq="5min")
    df_5m = pd.DataFrame(
        {
            "open": [100.0] * len(idx_5m),
            "high": [100.5, 100.25, 101.75, 101.75, 101.75, 101.75, 101.75, 101.75],
            "low": [99.5, 99.5, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            "close": [100.0, 100.0, 101.5, 101.5, 101.5, 101.5, 101.5, 101.5],
            "volume": [1000] * len(idx_5m),
        },
        index=idx_5m,
    )
    idx_1m = pd.date_range("2025-01-02 09:30", periods=40, freq="1min")
    df_1m = pd.DataFrame(
        {
            "open": [100.0] * len(idx_1m),
            "high": [100.25] * 10 + [101.75] * 30,
            "low": [99.5] * 10 + [100.0] * 30,
            "close": [100.0] * 10 + [101.5] * 30,
            "volume": [1000] * len(idx_1m),
        },
        index=idx_1m,
    )

    def fake_extract(_df, session, _config, _signal_cache=None):
        return [
            _VWAPSetupCandidate(
                date_str="2025-01-02",
                session=session.name,
                direction=1,
                signal_bar=1,
                entry_bar=2,
                entry_price=100.0,
                stop_price=99.0,
                vwap_at_signal=100.5,
                daily_atr=10.0,
            )
        ]

    monkeypatch.setattr(vwap_simulator, "_extract_vwap_candidates", fake_extract)

    config = with_vwap_overrides(
        default_vwap_config(NQ),
        rr=1.5,
        risk_usd=500.0,
        tp1_ratio=1.0,
    )

    trades = run_vwap_backtest(
        df_5m,
        config,
        start_date="2025-01-02",
        end_date="2025-01-03",
        df_1m=df_1m,
    )

    assert len(trades) == 1
    assert trades[0].exit_type == vwap_simulator.EXIT_TP2_SINGLE


def test_vwap_short_does_not_trigger_default_internal_swing_breakeven(monkeypatch):
    idx_5m = pd.date_range("2025-01-02 09:30", periods=8, freq="5min")
    df_5m = pd.DataFrame(
        {
            "open": [100.0] * len(idx_5m),
            "high": [100.5, 100.25, 100.25, 100.25, 100.25, 100.25, 100.25, 100.25],
            "low": [99.5, 99.5, 99.0, 98.25, 98.25, 98.25, 98.25, 98.25],
            "close": [100.0, 100.0, 99.5, 98.5, 98.5, 98.5, 98.5, 98.5],
            "volume": [1000] * len(idx_5m),
        },
        index=idx_5m,
    )
    idx_1m = pd.date_range("2025-01-02 09:30", periods=40, freq="1min")
    df_1m = pd.DataFrame(
        {
            "open": [100.0] * len(idx_1m),
            "high": [100.25] * len(idx_1m),
            "low": [99.0] * 15 + [98.25] * 25,
            "close": [99.5] * 15 + [98.5] * 25,
            "volume": [1000] * len(idx_1m),
        },
        index=idx_1m,
    )

    def fake_extract(_df, session, _config, _signal_cache=None):
        return [
            _VWAPSetupCandidate(
                date_str="2025-01-02",
                session=session.name,
                direction=-1,
                signal_bar=1,
                entry_bar=2,
                entry_price=100.0,
                stop_price=101.0,
                vwap_at_signal=99.5,
                daily_atr=10.0,
            )
        ]

    monkeypatch.setattr(vwap_simulator, "_extract_vwap_candidates", fake_extract)

    config = with_vwap_overrides(
        default_vwap_config(NQ),
        rr=1.5,
        risk_usd=500.0,
        tp1_ratio=1.0,
    )

    trades = run_vwap_backtest(
        df_5m,
        config,
        start_date="2025-01-02",
        end_date="2025-01-03",
        df_1m=df_1m,
    )

    assert len(trades) == 1
    assert trades[0].exit_type == vwap_simulator.EXIT_TP2_SINGLE
