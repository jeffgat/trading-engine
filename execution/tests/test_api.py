from trader.api import DashboardState, parse_trade_log_line
from trader.engine import TradeRecord


def test_parse_trade_log_line_keeps_full_tick_time_and_resolution():
    line = (
        "2026-03-11 21:46:00 | FAST_V2 | es | ES_Asia | TP1_PARTIAL | "
        "dir=long tp1=6737.75 half_qty=12.0 be=6734.75 tp2=6740.16 "
        "tick_time=2026-03-11 21:45:59-04:00 resolution=1s"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["details"]["tick_time"] == "2026-03-11 21:45:59-04:00"
    assert parsed["details"]["resolution"] == "1s"


def test_parse_trade_log_line_keeps_full_bar_time():
    line = (
        "2026-03-11 21:50:00 | FAST_V2 | es | ES_Asia | TP1_PARTIAL | "
        "dir=long tp1=6737.75 be=6734.75 bar_time=2026-03-11 21:45:00-04:00 resolution=5m"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["details"]["bar_time"] == "2026-03-11 21:45:00-04:00"
    assert parsed["details"]["resolution"] == "5m"


def test_parse_trade_log_line_normalizes_legacy_alpha_v1_config_name():
    line = (
        "2026-04-14 04:05:00 | ALPHA_V1 | nq | NQ_Asia | TP1_PARTIAL | "
        "dir=long tp1=25641.60 half_qty=2.0 be=25590.75 tp2=25760.25"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["config"] == "ALPHA_V1-A"


def test_dashboard_state_asia_tp1_hit_for_date_accepts_alpha_v1_alias():
    state = DashboardState()
    state.trade_history = [
        TradeRecord(
            session="NQ_Asia",
            date="20260414",
            direction=1,
            entry_price=1.0,
            stop_price=0.0,
            tp1_price=2.0,
            tp2_price=3.0,
            exit_type="tp1_partial",
            tp1_hit=True,
            timestamp="2026-04-14T04:05:00-04:00",
            config_name="ALPHA_V1",
            r_result=0.9,
            entry_timestamp="2026-04-14T03:40:00-04:00",
        )
    ]

    assert state.asia_tp1_hit_for_date("20260414", config_name="ALPHA_V1-A") is True
