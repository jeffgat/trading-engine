"""Performance metrics — re-exports from orb_backtest.

The IFVG engine produces the same TradeResult schema, so all metrics
computation works identically.
"""

from orb_backtest.results.metrics import compute_metrics  # noqa: F401
