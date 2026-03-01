"""FVG detection for IFVG strategy — re-exports from orb_backtest.

The IFVG strategy uses the same 3-candle FVG pattern as the ORB strategy
but WITHOUT the ORB directional filter. Any valid FVG qualifies regardless
of its position relative to an opening range.
"""

from orb_backtest.signals.fvg import detect_fvg_no_orb  # noqa: F401
