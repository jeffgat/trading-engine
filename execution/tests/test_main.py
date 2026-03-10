from __future__ import annotations

from unittest.mock import MagicMock

from trader.api import DashboardState, _build_exec_config_meta
from trader.main import apply_atr_values, build_engines, build_lsi_engines


def test_build_engines_applies_session_date_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": ["20241218"],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["NQ_NY"],
        exec_overrides={
            "NQ_NY": {
                "excluded_dates": ["20260101"],
                "half_days": ["20260119"],
                "half_day_flat_start": "12:40",
                "half_day_flat_end": "12:45",
            }
        },
    )

    engine = engines[0]
    assert engine.excluded_dates == ("20260101",)
    assert engine.half_days == ("20260119",)
    assert engine.half_day_flat_start == "12:40"
    assert engine.half_day_flat_end == "12:45"


def test_build_lsi_engines_applies_session_date_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": ["20241218"],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="FAST_V2",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={
            "NQ_Asia_LSI": {
                "excluded_dates": ["20260102"],
                "half_days": ["20260119"],
                "half_day_flat_start": "12:35",
                "half_day_flat_end": "12:40",
            }
        },
    )

    engine = engines[0]
    assert engine.excluded_dates == ("20260102",)
    assert engine.half_days == ("20260119",)
    assert engine._half_day_flat_start_t.hour == 12
    assert engine._half_day_flat_start_t.minute == 35
    assert engine._half_day_flat_end_t.hour == 12
    assert engine._half_day_flat_end_t.minute == 40


def test_build_exec_config_meta_reads_disk_configs(monkeypatch):
    class FakeWebhook:
        def __init__(self, url: str, label: str):
            self.url = url
            self.label = label
            self.paused = False
            self.multiplier = 1.0

    class FakeConfig:
        def __init__(self):
            self.name = "FAST_V2"
            self.enabled = True
            self.webhooks = [FakeWebhook("https://example.test/hook", "Account 1")]
            self.session_overrides = {"NQ_NY": {}, "ES_NY": {}}
            self.lsi_session_overrides = {"NQ_NY_LSI": {}}

    monkeypatch.setattr("trader.main.load_exec_configs", lambda config=None: [FakeConfig()])

    state = DashboardState(
        config={},
        exec_configs={
            "FAST_V2": {
                "webhooks": [
                    {
                        "url": "https://live.example/hook",
                        "label": "Account 1",
                        "paused": True,
                        "multiplier": 2.0,
                    }
                ]
            }
        },
    )

    meta = _build_exec_config_meta(state)
    assert list(meta) == ["FAST_V2"]
    assert meta["FAST_V2"]["sessions"] == ["NQ_NY", "ES_NY"]
    assert meta["FAST_V2"]["lsi_sessions"] == ["NQ_NY_LSI"]
    assert meta["FAST_V2"]["webhooks"][0]["paused"] is True
    assert meta["FAST_V2"]["webhooks"][0]["multiplier"] == 2.0


def test_build_engines_symbol_map():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }
    _engines, sym_map, _atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY", "ES_NY"],
        exec_overrides={},
    )
    assert "NQ.FUT" in sym_map
    assert "ES.FUT" in sym_map


def test_apply_atr_values_updates_engines():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }
    engines, sym_map, _atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY"],
        exec_overrides={},
    )
    apply_atr_values(sym_map, {"NQ.FUT": 123.0})
    assert engines[0]._daily_atr == 123.0
