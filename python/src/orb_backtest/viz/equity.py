"""Equity curve and drawdown visualization."""

from __future__ import annotations

import numpy as np

from ..engine.simulator import TradeResult, EXIT_NO_FILL


def plot_equity_curve(
    trades: list[TradeResult],
    title: str = "Equity Curve",
    save_path: str | None = None,
    figsize: tuple[int, int] = (14, 8),
    initial_capital: float = 0.0,
) -> None:
    """Plot cumulative PnL with drawdown shading.

    Args:
        trades: List of TradeResult from the simulator.
        title: Plot title.
        save_path: Path to save figure (shows interactively if None).
        figsize: Figure size.
        initial_capital: Starting capital (0 = show pure PnL).
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import date

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        print("No filled trades to plot.")
        return

    dates = [date.fromisoformat(t.date) for t in filled]
    pnl = np.array([t.pnl_usd for t in filled])
    equity = np.cumsum(pnl) + initial_capital
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=figsize, height_ratios=[3, 1], sharex=True
    )

    # Equity curve
    ax1.plot(dates, equity, color="#2196F3", linewidth=1.5, label="Equity")
    ax1.plot(dates, peak, color="#B0BEC5", linewidth=0.8, linestyle="--", label="Peak")
    ax1.fill_between(dates, equity, peak, alpha=0.15, color="red")

    ax1.set_ylabel("PnL ($)" if initial_capital == 0 else "Equity ($)")
    ax1.set_title(title)
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=initial_capital, color="gray", linewidth=0.5, linestyle="--")

    # Drawdown
    ax2.fill_between(dates, drawdown, 0, alpha=0.4, color="red")
    ax2.plot(dates, drawdown, color="red", linewidth=0.8)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)

    # Format x-axis
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        plt.show()


def plot_monthly_returns(
    trades: list[TradeResult],
    title: str = "Monthly Returns",
    save_path: str | None = None,
    figsize: tuple[int, int] = (14, 6),
) -> None:
    """Plot monthly returns as a bar chart with color coding."""
    import matplotlib.pyplot as plt
    from collections import defaultdict

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return

    # Group by month
    monthly: dict[str, float] = defaultdict(float)
    for t in filled:
        month_key = t.date[:7]  # YYYY-MM
        monthly[month_key] += t.pnl_usd

    months = sorted(monthly.keys())
    values = [monthly[m] for m in months]
    colors = ["#26a69a" if v >= 0 else "#ef5350" for v in values]

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(range(len(months)), values, color=colors, width=0.8)
    ax.set_xticks(range(0, len(months), max(1, len(months) // 20)))
    ax.set_xticklabels(
        [months[i] for i in range(0, len(months), max(1, len(months) // 20))],
        rotation=45, ha="right",
    )
    ax.set_ylabel("PnL ($)")
    ax.set_title(title)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        plt.show()
