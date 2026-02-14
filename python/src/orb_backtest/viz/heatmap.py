"""Heatmap visualization for parameter sweep results."""

from __future__ import annotations

from typing import Any

import numpy as np


def plot_sweep_heatmap(
    results: list[tuple[Any, dict]],
    x_param: str,
    y_param: str,
    metric: str = "sharpe_ratio",
    param_ranges: dict[str, list] | None = None,
    title: str | None = None,
    save_path: str | None = None,
    figsize: tuple[int, int] = (12, 8),
    cmap: str = "RdYlGn",
    annotate: bool = True,
    fmt: str = ".2f",
) -> None:
    """Plot a 2D heatmap from grid sweep results.

    Args:
        results: List of (config, metrics_dict) tuples.
        x_param: Parameter name for x-axis.
        y_param: Parameter name for y-axis.
        metric: Metric key in metrics_dict to plot (e.g., 'sharpe_ratio', 'total_pnl_usd').
        param_ranges: Optional dict of param ranges for axis labels.
        title: Plot title (auto-generated if None).
        save_path: Path to save figure (shows interactively if None).
        figsize: Figure size.
        cmap: Colormap name.
        annotate: Whether to annotate cells with values.
        fmt: Number format for annotations.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    # Extract param values and metric values
    x_values = set()
    y_values = set()
    data_map: dict[tuple, float] = {}

    for config, metrics in results:
        x_val = _get_param(config, x_param)
        y_val = _get_param(config, y_param)
        m_val = metrics.get(metric, 0.0)

        if x_val is not None and y_val is not None:
            x_values.add(x_val)
            y_values.add(y_val)
            data_map[(x_val, y_val)] = m_val

    x_sorted = sorted(x_values)
    y_sorted = sorted(y_values)

    # Build 2D array
    data = np.full((len(y_sorted), len(x_sorted)), np.nan)
    for (xi, x_val) in enumerate(x_sorted):
        for (yi, y_val) in enumerate(y_sorted):
            if (x_val, y_val) in data_map:
                data[yi, xi] = data_map[(x_val, y_val)]

    # Plot
    fig, ax = plt.subplots(figsize=figsize)

    sns.heatmap(
        data,
        ax=ax,
        xticklabels=[str(v) for v in x_sorted],
        yticklabels=[str(v) for v in y_sorted],
        cmap=cmap,
        annot=annotate,
        fmt=fmt,
        linewidths=0.5,
        linecolor="gray",
        cbar_kws={"label": _metric_label(metric)},
    )

    ax.set_xlabel(x_param)
    ax.set_ylabel(y_param)
    ax.set_title(title or f"{_metric_label(metric)} by {x_param} vs {y_param}")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        plt.show()


def plot_multi_metric_heatmaps(
    results: list[tuple[Any, dict]],
    x_param: str,
    y_param: str,
    metrics: list[str] = None,
    save_path: str | None = None,
) -> None:
    """Plot multiple metric heatmaps in a grid layout.

    Args:
        results: List of (config, metrics_dict) tuples.
        x_param: Parameter for x-axis.
        y_param: Parameter for y-axis.
        metrics: List of metric keys to plot (default: common ones).
        save_path: Path to save combined figure.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    if metrics is None:
        metrics = ["sharpe_ratio", "total_pnl_usd", "win_rate", "profit_factor", "max_drawdown_usd", "avg_r"]

    n = len(metrics)
    cols = min(3, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))
    if rows == 1 and cols == 1:
        axes = np.array([[axes]])
    elif rows == 1:
        axes = axes.reshape(1, -1)
    elif cols == 1:
        axes = axes.reshape(-1, 1)

    for idx, metric in enumerate(metrics):
        r, c = divmod(idx, cols)
        ax = axes[r, c]

        x_values = sorted(set(_get_param(cfg, x_param) for cfg, _ in results if _get_param(cfg, x_param) is not None))
        y_values = sorted(set(_get_param(cfg, y_param) for cfg, _ in results if _get_param(cfg, y_param) is not None))

        data = np.full((len(y_values), len(x_values)), np.nan)
        for config, m in results:
            xv = _get_param(config, x_param)
            yv = _get_param(config, y_param)
            if xv in x_values and yv in y_values:
                xi = x_values.index(xv)
                yi = y_values.index(yv)
                data[yi, xi] = m.get(metric, 0.0)

        cmap = "RdYlGn_r" if "drawdown" in metric else "RdYlGn"
        sns.heatmap(
            data, ax=ax,
            xticklabels=[str(v) for v in x_values],
            yticklabels=[str(v) for v in y_values],
            cmap=cmap, annot=True, fmt=".2f",
            linewidths=0.5, linecolor="gray",
        )
        ax.set_xlabel(x_param)
        ax.set_ylabel(y_param)
        ax.set_title(_metric_label(metric))

    # Hide unused subplots
    for idx in range(n, rows * cols):
        r, c = divmod(idx, cols)
        axes[r, c].set_visible(False)

    plt.suptitle(f"Parameter Sweep: {x_param} vs {y_param}", fontsize=14, y=1.02)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
    else:
        plt.show()


def _get_param(config, param: str):
    """Extract param value from config, supporting session-prefixed names."""
    for sess_prefix in ("ny_", "asia_", "ldn_"):
        if param.startswith(sess_prefix):
            attr = param[len(sess_prefix):]
            sess_name = sess_prefix.rstrip("_").upper()
            for s in config.sessions:
                if s.name.upper() == sess_name:
                    return getattr(s, attr, None)
            return None
    return getattr(config, param, None)


def _metric_label(metric: str) -> str:
    """Human-readable label for a metric key."""
    labels = {
        "sharpe_ratio": "Sharpe Ratio",
        "sortino_ratio": "Sortino Ratio",
        "total_pnl_usd": "Total PnL ($)",
        "win_rate": "Win Rate",
        "profit_factor": "Profit Factor",
        "max_drawdown_usd": "Max Drawdown ($)",
        "max_drawdown_pct": "Max Drawdown (%)",
        "avg_r": "Avg R-Multiple",
        "avg_pnl_usd": "Avg PnL/Trade ($)",
        "total_trades": "Total Trades",
    }
    return labels.get(metric, metric.replace("_", " ").title())
