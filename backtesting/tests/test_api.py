from __future__ import annotations

import pandas as pd


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
