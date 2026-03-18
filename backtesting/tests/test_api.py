from __future__ import annotations

import pandas as pd

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import EXIT_SL, TradeResult
from orb_backtest.results.export import results_to_dict


def test_instruments_endpoint(client):
    res = client.get("/api/instruments")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert isinstance(payload["result"], list)
    assert payload["result"][0]["symbol"]


def test_sessions_endpoint(client):
    res = client.get("/api/sessions")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    names = {s["name"] for s in payload["result"]}
    assert "NY" in names


def test_configs_crud(client):
    create_payload = {
        "name": "NQ NY ORB base",
        "notes": "baseline config",
        "instrument": "NQ",
        "sessions": ["NY"],
        "strategy": "continuation",
        "config": {"rr": 2.5, "tp1_ratio": 0.5},
    }
    created = client.post("/api/configs", json=create_payload)
    assert created.status_code == 200
    config_id = created.json()["result"]["id"]

    listed = client.get("/api/configs")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["result"]]
    assert config_id in ids

    fetched = client.get(f"/api/configs/{config_id}")
    assert fetched.status_code == 200
    assert fetched.json()["result"]["name"] == "NQ NY ORB base"

    update_payload = {
        **create_payload,
        "name": "NQ NY ORB updated",
        "notes": "updated notes",
    }
    updated = client.put(f"/api/configs/{config_id}", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["result"]["name"] == "NQ NY ORB updated"

    deleted = client.delete(f"/api/configs/{config_id}")
    assert deleted.status_code == 200

    missing = client.get(f"/api/configs/{config_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CONFIG_NOT_FOUND"


def test_testing_plan_crud(client):
    create_payload = {"instrument": "NQ", "title": "test plan", "notes": "notes"}
    created = client.post("/api/testing-plan", json=create_payload)
    assert created.status_code == 200
    item_id = created.json()["result"]["id"]

    listed = client.get("/api/testing-plan")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["result"]]
    assert item_id in ids

    updated = client.put(
        f"/api/testing-plan/{item_id}",
        json={"status": "completed", "notes": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["result"]["status"] == "completed"

    deleted = client.delete(f"/api/testing-plan/{item_id}")
    assert deleted.status_code == 200


def test_run_backtest_endpoint_stubbed(client, monkeypatch):
    import orb_backtest.api as api

    def fake_load_5m_data(*_args, **_kwargs):
        return pd.DataFrame()

    def fake_run_backtest(*_args, **_kwargs):
        return []

    def fake_results_to_dict(*_args, **_kwargs):
        return {
            "config": {"instrument": "NQ", "rr": 2.5, "risk_usd": 5000},
            "summary": {
                "total_trades": 0,
                "total_pnl_usd": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_usd": 0.0,
                "profit_factor": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "total_r": 0.0,
                "max_drawdown_r": 0.0,
                "avg_r": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,
                "total_signals": 0,
                "no_fills": 0,
                "win_count": 0,
                "loss_count": 0,
                "be_count": 0,
                "avg_pnl_usd": 0.0,
                "avg_win_usd": 0.0,
                "avg_loss_usd": 0.0,
                "largest_win_usd": 0.0,
                "largest_loss_usd": 0.0,
                "exit_breakdown": {},
                "pnl_by_year": {},
                "pnl_by_month": {},
                "pnl_by_dow": {},
                "long_trades": 0,
                "short_trades": 0,
                "long_win_rate": 0.0,
                "short_win_rate": 0.0,
                "long_pnl_usd": 0.0,
                "short_pnl_usd": 0.0,
            },
            "trades": [],
            "equity_curve": [],
        }

    def fake_save_backtest_result(_result):
        return "bt-test"

    monkeypatch.setattr(api, "load_5m_data", fake_load_5m_data)
    monkeypatch.setattr(api, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(api, "results_to_dict", fake_results_to_dict)
    monkeypatch.setattr(api, "save_backtest_result", fake_save_backtest_result)

    res = client.post("/api/backtest", json={"instrument": "NQ", "sessions": ["NY"]})
    assert res.status_code == 200
    payload = res.json()["result"]
    assert payload["id"] == "bt-test"
    assert payload["config"]["instrument"] == "NQ"


def test_run_backtest_endpoint_parses_saved_config_shape(client, monkeypatch):
    import orb_backtest.api as api

    captured = {}

    def fake_load_5m_data(*_args, **_kwargs):
        return pd.DataFrame()

    def fake_load_1m_for_5m(*_args, **_kwargs):
        return pd.DataFrame()

    def fake_run_backtest(df, config, start_date=None, end_date=None, df_1m=None):
        captured["config"] = config
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["has_1m"] = df_1m is not None
        return []

    def fake_results_to_dict(*_args, **_kwargs):
        return {
            "config": {"instrument": "NQ", "rr": 3.0, "risk_usd": 5000},
            "summary": {
                "total_trades": 0,
                "total_pnl_usd": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_usd": 0.0,
                "profit_factor": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "total_r": 0.0,
                "max_drawdown_r": 0.0,
                "avg_r": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,
                "total_signals": 0,
                "no_fills": 0,
                "win_count": 0,
                "loss_count": 0,
                "be_count": 0,
                "avg_pnl_usd": 0.0,
                "avg_win_usd": 0.0,
                "avg_loss_usd": 0.0,
                "largest_win_usd": 0.0,
                "largest_loss_usd": 0.0,
                "exit_breakdown": {},
                "pnl_by_year": {},
                "pnl_by_month": {},
                "pnl_by_dow": {},
                "long_trades": 0,
                "short_trades": 0,
                "long_win_rate": 0.0,
                "short_win_rate": 0.0,
                "long_pnl_usd": 0.0,
                "short_pnl_usd": 0.0,
            },
            "trades": [],
            "equity_curve": [],
        }

    monkeypatch.setattr(api, "load_5m_data", fake_load_5m_data)
    monkeypatch.setattr(api, "load_1m_for_5m", fake_load_1m_for_5m)
    monkeypatch.setattr(api, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(api, "results_to_dict", fake_results_to_dict)
    monkeypatch.setattr(api, "save_backtest_result", lambda _result: "bt-test")

    res = client.post(
        "/api/backtest",
        json={
            "instrument": "NQ",
            "sessions": ["NY"],
            "start": "2024-03-05",
            "strategy": "lsi",
            "direction_filter": "long",
            "bar_magnifier": "ON",
            "impulse_close_filter": "OFF",
            "swing_n_bars": 12,
            "excluded_days": ["Wed", "Thu"],
            "half_days": ["20250703"],
            "excluded_dates": ["20241218"],
            "ny_rth_start": "09:30",
            "ny_entry_window": "09:35-15:30",
            "ny_flat_window": "15:50-16:00",
            "lsi_n_left": 8,
            "lsi_n_right": 60,
            "lsi_fvg_window_left": 20,
            "lsi_fvg_window_right": 5,
            "lsi_stop_mode": "absolute",
            "lsi_entry_mode": "fvg_limit",
        },
    )
    assert res.status_code == 200
    cfg = captured["config"]
    assert captured["start_date"] == "2024-03-05"
    assert captured["end_date"] is None
    assert captured["has_1m"] is True
    assert cfg.use_bar_magnifier is True
    assert cfg.impulse_close_filter is False
    assert cfg.swing_n_bars == 12
    assert cfg.excluded_days == (2, 3)
    assert cfg.half_days == ("20250703",)
    assert cfg.excluded_dates == ("20241218",)
    assert cfg.lsi_n_left == 8
    assert cfg.lsi_n_right == 60
    assert cfg.lsi_fvg_window_left == 20
    assert cfg.lsi_fvg_window_right == 5
    assert cfg.lsi_stop_mode == "absolute"
    assert cfg.lsi_entry_mode == "fvg_limit"
    assert cfg.sessions[0].rth_start == "09:30"
    assert cfg.sessions[0].entry_start == "09:35"
    assert cfg.sessions[0].entry_end == "15:30"
    assert cfg.sessions[0].flat_start == "15:50"
    assert cfg.sessions[0].flat_end == "16:00"


def test_results_to_dict_applies_excluded_days_filter():
    config = StrategyConfig(
        instrument=NQ,
        sessions=(SessionConfig(name="NY"),),
        excluded_days=(3,),
    )
    trades = [
        TradeResult(
            date="2026-03-05",
            session="NY",
            direction=1,
            signal_bar=0,
            fill_bar=0,
            entry_price=100.0,
            stop_price=99.0,
            tp1_price=100.5,
            tp2_price=101.0,
            exit_type=EXIT_SL,
            exit_bar=0,
            pnl_points=-1.0,
            pnl_usd=-100.0,
            r_multiple=-1.0,
            qty=1.0,
            half_qty=0.0,
            gap_size=1.0,
            risk_points=1.0,
            fill_time="2026-03-05T10:00:00",
            exit_time="2026-03-05T10:05:00",
        ),
        TradeResult(
            date="2026-03-06",
            session="NY",
            direction=1,
            signal_bar=1,
            fill_bar=1,
            entry_price=100.0,
            stop_price=99.0,
            tp1_price=100.5,
            tp2_price=101.0,
            exit_type=EXIT_SL,
            exit_bar=1,
            pnl_points=-1.0,
            pnl_usd=-100.0,
            r_multiple=-1.0,
            qty=1.0,
            half_qty=0.0,
            gap_size=1.0,
            risk_points=1.0,
            fill_time="2026-03-06T10:00:00",
            exit_time="2026-03-06T10:05:00",
        ),
    ]

    result = results_to_dict(trades, config, include_trades=True)

    assert result["config"]["excluded_days"] == ["Thu"]
    assert len(result["trades"]) == 1
    assert result["trades"][0]["date"] == "2026-03-06"
    assert result["summary"]["total_signals"] == 1
    assert result["summary"]["total_trades"] == 1


def test_news_straddle_endpoint_accepts_fomc_event_type(client, monkeypatch):
    import orb_backtest.api as api

    captured = {}

    def fake_run_news_straddle(config, start=None, end=None):
        captured["config"] = config
        captured["start"] = start
        captured["end"] = end
        return {
            "config": {
                "buffer_points": config.buffer_points,
                "target_points": config.target_points,
                "event_types": list(config.event_types),
                "observation_window_seconds": config.observation_window_seconds,
                "instrument": config.instrument,
                "stop_loss_points": config.stop_loss_points,
            },
            "summary": {},
            "events": [],
        }

    monkeypatch.setattr(api, "run_news_straddle", fake_run_news_straddle)
    monkeypatch.setattr(api, "log_news_straddle_run", lambda *_args, **_kwargs: 1)

    res = client.post(
        "/api/news-straddle",
        json={
            "buffer_points": 5,
            "target_points": 25,
            "event_types": ["FOMC"],
            "observation_window_seconds": 120,
            "instrument": "NQ",
            "start": "2024-01-01",
            "end": "2024-12-31",
        },
    )

    assert res.status_code == 200
    assert captured["config"].event_types == ("FOMC",)
    assert captured["start"] == "2024-01-01"
    assert captured["end"] == "2024-12-31"
    assert res.json()["result"]["config"]["event_types"] == ["FOMC"]


def test_news_candles_uses_fomc_release_time(client, monkeypatch):
    import orb_backtest.engine.news_straddle as news_straddle

    def fake_load_1s_data(*_args, **_kwargs):
        idx = pd.DatetimeIndex(
            [
                "2025-03-19 13:59:59",
                "2025-03-19 14:00:00",
            ]
        )
        return pd.DataFrame(
            {
                "open": [20000.0, 20005.0],
                "high": [20006.0, 20012.0],
                "low": [19998.0, 20003.0],
                "close": [20005.0, 20010.0],
            },
            index=idx,
        )

    monkeypatch.setattr(news_straddle, "_load_1s_data", fake_load_1s_data)

    res = client.get(
        "/api/news-candles",
        params={
            "instrument": "NQ",
            "date": "2025-03-19",
            "seconds_before": 1,
            "seconds_after": 0,
            "event_type": "FOMC",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert len(payload) == 2
    assert payload[0]["time"].startswith("2025-03-19T13:59:59")
    assert payload[1]["time"].startswith("2025-03-19T14:00:00")
