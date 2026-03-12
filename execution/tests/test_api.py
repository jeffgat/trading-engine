from trader.api import parse_trade_log_line


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
