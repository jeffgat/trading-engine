"""Performance metrics computed from trade results."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..engine.simulator import TradeResult, EXIT_NO_FILL, EXIT_NAMES


def compute_metrics(trades: list[TradeResult]) -> dict:
    """Compute comprehensive performance metrics from trade results.

    Args:
        trades: List of TradeResult from the simulator.

    Returns:
        Dict with summary stats, exit breakdown, and time-based analysis.
    """
    # Filter out no-fill trades for PnL metrics
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    all_trades = trades  # keep no-fills for signal stats

    if not filled:
        return _empty_metrics(len(all_trades))

    pnl_usd = np.array([t.pnl_usd for t in filled])
    pnl_pts = np.array([t.pnl_points for t in filled])
    r_multiples = np.array([t.r_multiple for t in filled])

    wins = pnl_usd > 0
    losses = pnl_usd < 0
    breakevens = pnl_usd == 0

    total_wins = float(np.sum(pnl_usd[wins]))
    total_losses = float(np.sum(pnl_usd[losses]))

    # Equity curve for drawdown
    equity = np.cumsum(pnl_usd)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    # Max drawdown as % of peak equity
    max_dd_pct = 0.0
    if len(peak) > 0 and np.max(peak) > 0:
        dd_pct = drawdown / np.where(peak > 0, peak, 1.0) * 100
        max_dd_pct = float(np.min(dd_pct))

    # Consecutive wins/losses
    max_consec_wins = _max_consecutive(pnl_usd > 0)
    max_consec_losses = _max_consecutive(pnl_usd < 0)

    # Annualized Sharpe & Sortino
    # ~1 trade/day, so annualize with sqrt(252)
    avg_r = float(np.mean(r_multiples))
    std_r = float(np.std(r_multiples, ddof=1)) if len(r_multiples) > 1 else 1.0
    sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    downside_returns = np.minimum(r_multiples, 0.0)
    downside_std = float(np.sqrt(np.mean(downside_returns ** 2)))
    sortino = (avg_r / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

    # Exit type breakdown
    exit_counts = defaultdict(int)
    for t in all_trades:
        exit_counts[EXIT_NAMES.get(t.exit_type, "unknown")] += 1

    # PnL by year, month, day-of-week
    pnl_by_year = _group_pnl(filled, lambda t: t.date[:4])
    pnl_by_month = _group_pnl(filled, lambda t: t.date[:7])
    pnl_by_dow = _group_pnl_dow(filled)

    # Direction breakdown
    long_trades = [t for t in filled if t.direction == 1]
    short_trades = [t for t in filled if t.direction == -1]

    return {
        "total_signals": len(all_trades),
        "total_trades": len(filled),
        "no_fills": exit_counts.get("no_fill", 0),
        "win_count": int(np.sum(wins)),
        "loss_count": int(np.sum(losses)),
        "be_count": int(np.sum(breakevens)),
        "win_rate": float(np.mean(wins)) if len(filled) > 0 else 0.0,
        "total_pnl_usd": float(np.sum(pnl_usd)),
        "avg_pnl_usd": float(np.mean(pnl_usd)),
        "avg_win_usd": float(np.mean(pnl_usd[wins])) if wins.any() else 0.0,
        "avg_loss_usd": float(np.mean(pnl_usd[losses])) if losses.any() else 0.0,
        "largest_win_usd": float(np.max(pnl_usd)) if len(pnl_usd) > 0 else 0.0,
        "largest_loss_usd": float(np.min(pnl_usd)) if len(pnl_usd) > 0 else 0.0,
        "profit_factor": abs(total_wins / total_losses) if total_losses != 0 else float("inf"),
        "avg_r": avg_r,
        "avg_win_r": float(np.mean(r_multiples[wins])) if wins.any() else 0.0,
        "avg_loss_r": float(np.mean(r_multiples[losses])) if losses.any() else 0.0,
        "max_drawdown_usd": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "exit_breakdown": dict(exit_counts),
        "pnl_by_year": pnl_by_year,
        "pnl_by_month": pnl_by_month,
        "pnl_by_dow": pnl_by_dow,
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "long_win_rate": _win_rate(long_trades),
        "short_win_rate": _win_rate(short_trades),
        "long_pnl_usd": sum(t.pnl_usd for t in long_trades),
        "short_pnl_usd": sum(t.pnl_usd for t in short_trades),
    }


def _empty_metrics(total_signals: int) -> dict:
    """Return zeroed-out metrics when no trades filled."""
    return {
        "total_signals": total_signals,
        "total_trades": 0,
        "no_fills": total_signals,
        "win_count": 0,
        "loss_count": 0,
        "be_count": 0,
        "win_rate": 0.0,
        "total_pnl_usd": 0.0,
        "avg_pnl_usd": 0.0,
        "avg_win_usd": 0.0,
        "avg_loss_usd": 0.0,
        "largest_win_usd": 0.0,
        "largest_loss_usd": 0.0,
        "profit_factor": 0.0,
        "avg_r": 0.0,
        "avg_win_r": 0.0,
        "avg_loss_r": 0.0,
        "max_drawdown_usd": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "exit_breakdown": {"no_fill": total_signals},
        "pnl_by_year": {},
        "pnl_by_month": {},
        "pnl_by_dow": {},
        "long_trades": 0,
        "short_trades": 0,
        "long_win_rate": 0.0,
        "short_win_rate": 0.0,
        "long_pnl_usd": 0.0,
        "short_pnl_usd": 0.0,
    }


def _max_consecutive(mask: np.ndarray) -> int:
    """Max consecutive True values in a boolean array."""
    if len(mask) == 0:
        return 0
    max_run = 0
    current = 0
    for v in mask:
        if v:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _win_rate(trades: list[TradeResult]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t.pnl_usd > 0) / len(trades)


def _group_pnl(trades: list[TradeResult], key_fn) -> dict[str, float]:
    groups: dict[str, float] = {}
    for t in trades:
        k = key_fn(t)
        groups[k] = groups.get(k, 0.0) + t.pnl_usd
    return dict(sorted(groups.items()))


def _group_pnl_dow(trades: list[TradeResult]) -> dict[str, float]:
    """PnL by day of week (Mon=0 .. Fri=4)."""
    import datetime

    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    groups: dict[str, float] = {}
    for t in trades:
        d = datetime.date.fromisoformat(t.date)
        name = dow_names[d.weekday()]
        groups[name] = groups.get(name, 0.0) + t.pnl_usd
    return groups
