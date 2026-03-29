#!/usr/bin/env python3
"""Brute-force grid search to find the optimal combination of strategy risk sizes
that minimizes a target month's drawdown while maximizing that month's returns.

Reads configuration from a JSON file (passed as sys.argv[1]) specifying strategies,
target month, DD constraints, risk levels, and year range.

Searches all N^S combinations of risk levels across S strategies. Filters combos
where at most K months violate the DD threshold, then ranks by total month R descending.

The DD calculation matches the frontend's computeCombinedMaxDrawdownByMonth exactly:
running cumR and peak persist across the entire trade history, never reset per month.

Usage:
    cd python && uv run python ../.claude/skills/portfolio-month-optimizer/scripts/optimize_month.py config.json
"""

import calendar
import itertools
import json
import sqlite3
import sys
import time

from pathlib import Path

import numpy as np

# Anchor to repo root regardless of cwd — script lives at .claude/skills/.../scripts/
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "python" / "src"))
from orb_backtest.experiments import DB_PATH

# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_RISK_LEVELS = [0, 50, 100, 150, 200, 250]
DEFAULT_CHUNK_SIZE = 10_000


# ── Config loading & validation ─────────────────────────────────────────────


def validate_config(config):
    """Validate the config dict. Prints a clear error and exits on failure."""
    errors = []

    # strategies
    if "strategies" not in config:
        errors.append("Missing required key: 'strategies'")
    elif not isinstance(config["strategies"], list) or len(config["strategies"]) == 0:
        errors.append("'strategies' must be a non-empty list")
    else:
        required_keys = {"name", "short", "result_file", "base_scale", "current_risk"}
        for i, strat in enumerate(config["strategies"]):
            if not isinstance(strat, dict):
                errors.append(f"strategies[{i}] must be a dict")
                continue
            missing = required_keys - set(strat.keys())
            if missing:
                errors.append(
                    f"strategies[{i}] ('{strat.get('name', '?')}') missing keys: "
                    f"{', '.join(sorted(missing))}"
                )
            else:
                label = strat.get("name", f"strategies[{i}]")
                if not isinstance(strat["base_scale"], (int, float)) or strat["base_scale"] <= 0:
                    errors.append(f"'{label}': base_scale must be a positive number")
                if not isinstance(strat["current_risk"], (int, float)) or strat["current_risk"] < 0:
                    errors.append(f"'{label}': current_risk must be a non-negative number")

    # month
    if "month" not in config:
        errors.append("Missing required key: 'month'")
    elif not isinstance(config["month"], int) or not (1 <= config["month"] <= 12):
        errors.append(f"'month' must be an integer 1-12, got: {config.get('month')}")

    # max_dd_threshold
    if "max_dd_threshold" not in config:
        errors.append("Missing required key: 'max_dd_threshold'")
    elif not isinstance(config["max_dd_threshold"], (int, float)) or config["max_dd_threshold"] <= 0:
        errors.append(
            f"'max_dd_threshold' must be a positive number, got: {config.get('max_dd_threshold')}"
        )

    # max_violations
    if "max_violations" not in config:
        errors.append("Missing required key: 'max_violations'")
    elif not isinstance(config["max_violations"], int) or config["max_violations"] < 0:
        errors.append(
            f"'max_violations' must be a non-negative integer, got: {config.get('max_violations')}"
        )

    # risk_levels (always present after defaults applied in load_config)
    rl = config.get("risk_levels", [])
    if not isinstance(rl, list) or len(rl) == 0:
        errors.append("'risk_levels' must be a non-empty list of numbers")
    elif not all(isinstance(r, (int, float)) for r in rl):
        errors.append("'risk_levels' must contain only numbers")
    elif max(rl) <= 0:
        errors.append("'risk_levels' must contain at least one positive value")
    elif isinstance(config.get("strategies"), list):
        rl_set = set(rl)
        for i, strat in enumerate(config["strategies"]):
            if isinstance(strat, dict):
                cr = strat.get("current_risk")
                if isinstance(cr, (int, float)) and cr not in rl_set:
                    errors.append(
                        f"strategies[{i}] ('{strat.get('name', '?')}'): "
                        f"current_risk={cr} is not in risk_levels {rl}"
                    )

    # year_range
    if "year_range" not in config:
        errors.append("Missing required key: 'year_range'")
    elif (
        not isinstance(config["year_range"], list)
        or len(config["year_range"]) != 2
        or not all(isinstance(y, int) for y in config["year_range"])
    ):
        errors.append(
            f"'year_range' must be a list of exactly 2 integers, got: {config.get('year_range')}"
        )
    elif config["year_range"][0] > config["year_range"][1]:
        errors.append(
            f"'year_range' start ({config['year_range'][0]}) must be <= end ({config['year_range'][1]})"
        )

    # chunk_size (optional)
    if "chunk_size" in config:
        cs = config["chunk_size"]
        if not isinstance(cs, int) or cs <= 0:
            errors.append(f"'chunk_size' must be a positive integer, got: {cs}")

    if errors:
        print("CONFIG VALIDATION ERRORS:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


def load_config(path):
    """Load and validate config from a JSON file."""
    with open(path, "r") as f:
        config = json.load(f)

    # Apply defaults BEFORE validation so cross-checks (e.g., current_risk in risk_levels) work
    if "risk_levels" not in config:
        config["risk_levels"] = list(DEFAULT_RISK_LEVELS)
    if "chunk_size" not in config:
        config["chunk_size"] = DEFAULT_CHUNK_SIZE

    validate_config(config)

    return config


# ── Core functions ──────────────────────────────────────────────────────────


def load_trades_from_db(strategies):
    """Load trades for all strategies from the DB.

    Returns list of N lists, each containing (date_str, scaled_r) tuples.
    """
    conn = sqlite3.connect(str(DB_PATH))
    all_strategy_trades = []

    for i, strat in enumerate(strategies):
        row = conn.execute(
            "SELECT trades_json FROM runs WHERE result_file = ? AND run_type = 'backtest' "
            "ORDER BY id DESC LIMIT 1",
            (strat["result_file"],),
        ).fetchone()

        if row is None:
            print(
                f"  ERROR: No backtest found for {strat['name']} "
                f"(result_file={strat['result_file']})"
            )
            conn.close()
            sys.exit(1)

        trades = json.loads(row[0])
        filled = [
            (t["date"], t["r_multiple"] * strat["base_scale"])
            for t in trades
            if t["exit_type"] != "no_fill"
        ]
        all_strategy_trades.append(filled)
        print(f"  #{i+1} {strat['name']:.<30s} {len(filled):>5} filled trades")

    conn.close()
    return all_strategy_trades


def build_merged_timeline(all_strategy_trades):
    """Merge all strategy trades into a single sorted timeline.

    Returns:
        dates: np.array of date strings, shape (n_trades,)
        strat_indices: np.array of int, shape (n_trades,) -- which strategy each trade belongs to
        base_r_values: np.array of float, shape (n_trades,) -- base_scaled r_multiple
    """
    merged = []
    for strat_idx, trades in enumerate(all_strategy_trades):
        for date_str, scaled_r in trades:
            merged.append((date_str, strat_idx, scaled_r))

    # Stable sort by date (preserves order of strategies for same-date trades)
    merged.sort(key=lambda x: x[0])

    dates = np.array([m[0] for m in merged])
    strat_indices = np.array([m[1] for m in merged], dtype=np.int32)
    base_r_values = np.array([m[2] for m in merged], dtype=np.float64)

    return dates, strat_indices, base_r_values


def compute_month_indices(dates, month, target_years):
    """Pre-compute trade indices that fall in the target month for each year.

    Returns dict: year -> np.array of indices into the merged timeline.
    """
    month_str = f"{month:02d}"
    month_indices = {}
    for year in target_years:
        prefix = f"{year}-{month_str}"
        mask = np.array([d.startswith(prefix) for d in dates])
        indices = np.where(mask)[0]
        if len(indices) > 0:
            month_indices[year] = indices
    return month_indices


def compute_month_net_r_matrix(all_strategy_trades, month, target_years, n_strategies):
    """Pre-compute month Net R for each strategy and year.

    Returns np.array of shape (n_years, n_strategies).
    """
    month_str = f"{month:02d}"
    year_to_idx = {year: yi for yi, year in enumerate(target_years)}
    matrix = np.zeros((len(target_years), n_strategies), dtype=np.float64)

    for strat_idx, trades in enumerate(all_strategy_trades):
        for date_str, scaled_r in trades:
            if date_str[5:7] == month_str:
                year = int(date_str[:4])
                yi = year_to_idx.get(year)
                if yi is not None:
                    matrix[yi, strat_idx] += scaled_r

    return matrix


def generate_all_combos(weight_values, n_strategies):
    """Generate all weight combinations.

    Returns np.array of shape (n_combos, n_strategies) with weight values.
    """
    return np.array(
        list(itertools.product(weight_values, repeat=n_strategies)), dtype=np.float64
    )


def run_grid_search(
    all_combos, strat_indices, base_r_values, month_indices, target_years, chunk_size
):
    """Run the vectorized grid search in chunks.

    For each chunk of combos, compute the full equity curve and extract month DD.

    Returns:
        month_dd_all: np.array of shape (n_combos, n_years) -- month DD per year
    """
    n_combos = len(all_combos)
    n_years = len(target_years)
    n_chunks = (n_combos + chunk_size - 1) // chunk_size

    month_dd_all = np.zeros((n_combos, n_years), dtype=np.float64)

    print(f"\nRunning grid search ({n_chunks} chunks of {chunk_size:,})...")
    t_total = time.time()

    for chunk_idx in range(n_chunks):
        t_chunk = time.time()
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_combos)
        chunk_weights = all_combos[start:end]

        # Build weighted R matrix: shape (chunk_size, n_trades)
        weighted_r = chunk_weights[:, strat_indices] * base_r_values[np.newaxis, :]

        # Cumulative R and peak
        cum_r = np.cumsum(weighted_r, axis=1)
        peak = np.maximum.accumulate(cum_r, axis=1)
        dd = peak - cum_r

        # Extract month DD for each year
        for year_idx, year in enumerate(target_years):
            if year in month_indices:
                idx = month_indices[year]
                month_dd = np.max(dd[:, idx], axis=1)
                month_dd_all[start:end, year_idx] = month_dd

        elapsed = time.time() - t_chunk
        print(f"  Chunk {chunk_idx+1:>3}/{n_chunks} ... {elapsed:.1f}s", flush=True)

    total_elapsed = time.time() - t_total
    print(f"  Total: {total_elapsed:.1f}s")

    return month_dd_all


# ── Formatting helpers ──────────────────────────────────────────────────────


def format_combo(strategies, weights, max_risk, risk_levels_for_display=None):
    """Format a weight combo as short-name:$risk pairs."""
    parts = []
    for i, strat in enumerate(strategies):
        if risk_levels_for_display is not None:
            risk = risk_levels_for_display[i]
        else:
            risk = int(round(weights[i] * max_risk))
        parts.append(f"{strat['short']}:${risk}")
    return "  ".join(parts)


def format_dd_row(dd_values, threshold):
    """Format a row of DD values with * for violations."""
    parts = []
    for dd in dd_values:
        s = f"{dd:.1f}"
        if dd > threshold:
            s += "*"
        parts.append(f"{s:>6}")
    return " ".join(parts)


def format_r_row(r_values):
    """Format a row of R values."""
    return " ".join(f"{r:>+5.1f}" for r in r_values)


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print("Usage: optimize_month.py <config.json>")
        print("\nConfig JSON format:")
        print(
            json.dumps(
                {
                    "strategies": [
                        {
                            "name": "Strategy Name",
                            "short": "SN",
                            "result_file": "bt-result-file-hash",
                            "base_scale": 1.0,
                            "current_risk": 250,
                        }
                    ],
                    "month": 3,
                    "max_dd_threshold": 8.0,
                    "max_violations": 2,
                    "risk_levels": [0, 50, 100, 150, 200, 250],
                    "year_range": [2016, 2025],
                    "chunk_size": 10000,
                },
                indent=2,
            )
        )
        sys.exit(1)

    config = load_config(sys.argv[1])

    # Extract config values
    strategies = config["strategies"]
    month = config["month"]
    month_name = calendar.month_name[month]
    max_dd_threshold = config["max_dd_threshold"]
    max_violations = config["max_violations"]
    risk_levels = config["risk_levels"]
    max_risk = max(risk_levels)
    weight_values = [r / max_risk for r in risk_levels]
    year_start, year_end = config["year_range"]
    target_years = list(range(year_start, year_end + 1))
    chunk_size = config["chunk_size"]
    n_strategies = len(strategies)
    current_risk = [s["current_risk"] for s in strategies]

    n_combos = len(weight_values) ** n_strategies

    print(f"{month_name.upper()} PORTFOLIO OPTIMIZATION")
    print("=" * 70)
    print(
        f"Strategies: {n_strategies}  |  Risk levels: {len(risk_levels)}  |  "
        f"Combinations: {n_combos:,}"
    )
    print(
        f"Constraint: {month_name} DD <= {max_dd_threshold}R in at least "
        f"{len(target_years) - max_violations} of {len(target_years)} years "
        f"({target_years[0]}-{target_years[-1]})"
    )

    # ── Step 1: Load trades ──────────────────────────────────────────────────
    print("\nLoading trades from DB...")
    all_strategy_trades = load_trades_from_db(strategies)

    total_filled = sum(len(t) for t in all_strategy_trades)
    all_dates = set()
    for trades in all_strategy_trades:
        for date_str, _ in trades:
            all_dates.add(date_str)
    print(f"  Total: {total_filled:,} filled trades across {len(all_dates):,} unique dates")

    # ── Step 2: Merge and sort timeline ──────────────────────────────────────
    dates, strat_indices, base_r_values = build_merged_timeline(all_strategy_trades)
    n_trades = len(dates)
    chunk_mem_gb = chunk_size * n_trades * 8 * 4 / 1e9
    print(f"\nMerged timeline: {n_trades:,} trades")
    print(
        f"  Peak chunk memory: ~{chunk_mem_gb:.1f} GB "
        f"({chunk_size:,} combos x {n_trades:,} trades x 4 arrays)"
    )

    # ── Step 3: Pre-compute month Net R matrix ───────────────────────────────
    print(f"\nPre-computing {month_name} Net R matrix...")
    month_r_matrix = compute_month_net_r_matrix(
        all_strategy_trades, month, target_years, n_strategies
    )

    # Print month R by strategy
    header = "  Strategy              " + " ".join(f"{y:>6}" for y in target_years)
    print(f"  {month_name} R by strategy:")
    print(header)
    for i, strat in enumerate(strategies):
        vals = " ".join(
            f"{month_r_matrix[yi, i]:>+5.1f}" for yi in range(len(target_years))
        )
        print(f"  {strat['name']:<22s} {vals}")

    # ── Step 4: Pre-compute month trade indices ──────────────────────────────
    month_indices = compute_month_indices(dates, month, target_years)

    # ── Step 5: Generate all combos ──────────────────────────────────────────
    print(f"\nGenerating {n_combos:,} weight combinations...")
    all_combos = generate_all_combos(weight_values, n_strategies)

    # ── Step 6: Grid search ──────────────────────────────────────────────────
    month_dd_all = run_grid_search(
        all_combos, strat_indices, base_r_values, month_indices, target_years, chunk_size
    )

    # ── Step 7: Compute month Net R for all combos ───────────────────────────
    month_r_for_combo = all_combos @ month_r_matrix.T  # (n_combos, n_years)
    total_month_r = month_r_for_combo.sum(axis=1)  # (n_combos,)

    # ── Step 8: Filter and rank ──────────────────────────────────────────────
    violations = (month_dd_all > max_dd_threshold).sum(axis=1)
    passing = violations <= max_violations
    n_passing = int(passing.sum())
    pct_passing = n_passing / n_combos * 100

    print("\n" + "=" * 70)
    print(f"RESULTS: {n_passing:,} combos pass constraint ({pct_passing:.1f}%)")
    print("=" * 70)

    # ── Current setup baseline ───────────────────────────────────────────────
    current_weights = np.array([r / max_risk for r in current_risk], dtype=np.float64)
    current_weighted_r = current_weights[strat_indices] * base_r_values
    current_cum_r = np.cumsum(current_weighted_r)
    current_peak = np.maximum.accumulate(current_cum_r)
    current_dd = current_peak - current_cum_r

    current_month_dd = np.zeros(len(target_years))
    current_month_r = np.zeros(len(target_years))
    for yi, year in enumerate(target_years):
        if year in month_indices:
            idx = month_indices[year]
            current_month_dd[yi] = float(np.max(current_dd[idx]))
        current_month_r[yi] = float(current_weights @ month_r_matrix[yi])

    current_total_r = current_month_r.sum()
    current_violations = int((current_month_dd > max_dd_threshold).sum())

    print(f"\nCURRENT SETUP (for reference):")
    print(f"  {format_combo(strategies, current_weights, max_risk, current_risk)}")
    print(f"  {month_name} DD: {format_dd_row(current_month_dd, max_dd_threshold)}")
    print(
        f"  {month_name} R:  {format_r_row(current_month_r)}  "
        f"Total: {current_total_r:>+.1f}R  Violations: {current_violations}"
    )

    # ── Top 20 by total month R ──────────────────────────────────────────────
    passing_indices = np.where(passing)[0]
    passing_total_r = total_month_r[passing_indices]
    top_order = np.argsort(-passing_total_r)[:20]
    top_indices = passing_indices[top_order]

    print(f"\nTOP 20 COMBINATIONS (sorted by Total {month_name} R):")
    year_header = " ".join(f"{y:>6}" for y in target_years)
    print(f"     Years: {year_header}")
    for rank, combo_idx in enumerate(top_indices, 1):
        weights = all_combos[combo_idx]
        risk_display = [int(round(w * max_risk)) for w in weights]
        combo_str = format_combo(strategies, weights, max_risk, risk_display)
        combo_total_r = total_month_r[combo_idx]
        combo_violations = int(violations[combo_idx])

        dd_vals = month_dd_all[combo_idx]
        r_vals = month_r_for_combo[combo_idx]

        print(
            f"\n#{rank:>2}  {combo_str}  Total: {combo_total_r:>+.1f}R  "
            f"Violations: {combo_violations}"
        )
        print(f"     DD:  {format_dd_row(dd_vals, max_dd_threshold)}")
        print(f"     R:   {format_r_row(r_vals)}")

    # ── Summary stats ────────────────────────────────────────────────────────
    if n_passing > 0:
        print(f"\n{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Passing combos: {n_passing:,} / {n_combos:,} ({pct_passing:.1f}%)")
        print(
            f"  Best total {month_name} R (passing): "
            f"{passing_total_r[top_order[0]]:>+.1f}R"
        )
        n_shown = min(len(top_order), 20)
        if n_shown > 0:
            worst_shown = passing_total_r[top_order[n_shown - 1]]
            print(f"  #{n_shown} total {month_name} R:              {worst_shown:>+.1f}R")
        print(f"  Current setup total {month_name} R:  {current_total_r:>+.1f}R")

        # Check if current setup passes
        if current_violations <= max_violations:
            better_count = int((passing_total_r > current_total_r + 1e-9).sum())
            current_rank = better_count + 1
            print(f"  Current setup rank (among passing): #{current_rank}")
        else:
            print(
                f"  Current setup does NOT pass constraint "
                f"({current_violations} violations)"
            )


if __name__ == "__main__":
    main()
