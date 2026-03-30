from __future__ import annotations

from unittest.mock import MagicMock

from trader.api import DashboardState, _build_exec_config_meta
from trader.engine import State
from trader.gates import build_regime_gate
from trader.lsi_engine import LSIState
from trader.main import (
    _checkpoint_shutdown_flat,
    apply_atr_values,
    build_engines,
    build_lsi_engines,
    load_exec_configs,
)


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
            self.max_open_contracts = 20
            self.webhooks = [FakeWebhook("https://example.test/hook", "Account 1")]
            self.session_overrides = {"NQ_NY": {}}
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
    assert meta["FAST_V2"]["max_open_contracts"] == 20
    assert meta["FAST_V2"]["sessions"] == ["NQ_NY"]
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
    assert _engines[0].atr_length == 12
    assert _atr_lens["NQ.FUT"] == {12}
    assert _atr_lens["ES.FUT"] == {7}


def test_build_engines_respects_long_only_override():
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

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["NQ_NY"],
        exec_overrides={"NQ_NY": {"long_only": False}},
    )

    assert engines[0].long_only is False


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
    apply_atr_values(sym_map, {"NQ.FUT": {12: 123.0}})
    assert engines[0]._daily_atr == 123.0


def test_apply_atr_values_uses_engine_specific_length():
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
    cont_engines, sym_map, atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY"],
        exec_overrides={},
    )
    lsi_engines = build_lsi_engines(
        config,
        broker,
        sym_map,
        atr_lens,
        config_name="FAST_V2",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={"NQ_Asia_LSI": {"atr_length": 40}},
    )
    apply_atr_values(sym_map, {"NQ.FUT": {12: 123.0, 40: 456.0}})
    assert cont_engines[0]._daily_atr == 123.0
    assert lsi_engines[0]._daily_atr == 456.0


def test_general_v1_exec_config_loads_as_dry_run_fixed_risk_profile():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    assert "GENERAL_V1" in configs
    general = configs["GENERAL_V1"]
    assert general.enabled is True
    assert general.webhook_url == ""
    assert set(general.session_overrides) == {"NQ_Asia", "NQ_NY_BULL_SPECIALIST"}
    assert set(general.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert general.session_overrides["NQ_Asia"]["risk_usd"] == 400
    assert general.session_overrides["NQ_NY_BULL_SPECIALIST"]["risk_usd"] == 400
    assert general.lsi_session_overrides["NQ_Asia_LSI"]["risk_usd"] == 400
    assert general.lsi_session_overrides["NQ_NY_LSI"]["risk_usd"] == 400
    assert general.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.34
    assert general.lsi_session_overrides["NQ_NY_LSI"]["qty_multiplier"] == 1.0


def test_general_v1_builds_exactly_four_engines_with_fixed_lsi_multiplier():
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
    general = {cfg.name: cfg for cfg in load_exec_configs()}["GENERAL_V1"]

    cont, sym_map, atr_lens = build_engines(
        config,
        broker,
        config_name="GENERAL_V1",
        session_list=list(general.session_overrides),
        exec_overrides=general.session_overrides,
    )
    lsi = build_lsi_engines(
        config,
        broker,
        sym_map,
        atr_lens,
        config_name="GENERAL_V1",
        lsi_list=list(general.lsi_session_overrides),
        lsi_overrides=general.lsi_session_overrides,
    )

    assert len(cont) + len(lsi) == 4
    assert {engine.name for engine in cont} == {"NQ_Asia", "NQ_NY_BULL_SPECIALIST"}
    assert {engine.name for engine in lsi} == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(engine.risk_usd == 400 for engine in cont)
    assert all(engine.risk_usd == 400 for engine in lsi)
    ny_lsi = next(engine for engine in lsi if engine.name == "NQ_NY_LSI")
    assert ny_lsi.qty_multiplier == 1.0


def test_fast_and_fast_v2_exec_configs_only_load_viable_sessions():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    fast = configs["FAST"]
    fast_v2 = configs["FAST_V2"]

    assert set(fast.session_overrides) == {
        "NQ_NY",
        "NQ_NY_BULL_SPECIALIST",
        "NQ_Asia",
        "ES_NY",
        "ES_Asia",
    }
    assert set(fast.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast.lsi_session_overrides.values())
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.34
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["qty_multiplier"] == 1.0

    assert set(fast_v2.session_overrides) == {"NQ_Asia"}
    assert set(fast_v2.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert fast_v2.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.4


def test_recommended_exec_configs_match_phase_one_subset_portfolios():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    fast = configs["FAST_V1.1"]
    fast_v2 = configs["FAST_V2.1"]
    general = configs["GENERAL_V1"]

    assert set(fast.session_overrides) == {
        "NQ_NY_BULL_SPECIALIST",
        "NQ_Asia",
        "ES_NY",
        "ES_Asia",
    }
    assert set(fast.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast.lsi_session_overrides.values())
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.34

    assert set(fast_v2.session_overrides) == {"NQ_Asia"}
    assert set(fast_v2.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast_v2.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast_v2.lsi_session_overrides.values())
    assert fast_v2.webhook_url == ""

    assert set(general.session_overrides) == {"NQ_Asia", "NQ_NY_BULL_SPECIALIST"}
    assert set(general.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in general.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in general.lsi_session_overrides.values())
    assert general.webhook_url == ""


def test_checkpoint_shutdown_flat_marks_orb_engine_flat():
    cleanup_task = MagicMock()
    cleanup_task.done.return_value = False
    engine = MagicMock()
    engine._state = State.MANAGING
    engine._cleanup_task = cleanup_task

    _checkpoint_shutdown_flat(engine)

    assert engine._state == State.FLAT
    cleanup_task.cancel.assert_called_once()
    assert engine._cleanup_task is None
    engine._release_position_cap.assert_called_once()
    engine._notify_state_change.assert_called_once()


def test_checkpoint_shutdown_flat_marks_lsi_engine_flat():
    cleanup_task = MagicMock()
    cleanup_task.done.return_value = True
    engine = MagicMock()
    engine._state = LSIState.ARMED_LIMIT
    engine._cleanup_task = cleanup_task

    _checkpoint_shutdown_flat(engine)

    assert engine._state == LSIState.FLAT
    cleanup_task.cancel.assert_not_called()
    engine._release_position_cap.assert_called_once()
    engine._notify_state_change.assert_called_once()


def test_bull_regime_gate_blocks_non_bull_and_low_confidence(monkeypatch):
    monkeypatch.setattr(
        "trader.gates._get_nq_regime_lookup",
        lambda: {
            "20250115": {"regime": "bear", "low_confidence": False},
            "20250116": {"regime": "bull", "low_confidence": True},
            "20250117": {"regime": "bull", "low_confidence": False},
        },
    )
    gate = build_regime_gate("bull_no_low_confidence")

    assert gate("20250115") is False
    assert gate("20250116") is False
    assert gate("20250117") is True
