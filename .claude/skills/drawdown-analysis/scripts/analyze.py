#!/usr/bin/env python3
"""Drawdown analysis: DD-by-year verdicts + consecutive loss streaks.

Usage:
    # Import and call directly with a list of filled TradeResult objects:
    from analyze import run_prop_risk_analysis
    run_prop_risk_analysis(filled_trades, prop_dd_limit=10.0, label="ES LDN R12")
"""

from collections import Counter, defaultdict


def compute_year_dd(trades_r_by_year: dict[str, list[float]]) -> list[tuple[str, float, float]]:
    """Compute max DD and net R per year.

    Returns: [(year, max_dd, net_r), ...]
    """
    results = []
    for y in sorted(trades_r_by_year.keys()):
        rs = trades_r_by_year[y]
        net_r = sum(rs)
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in rs:
            equity += r
            if equity > peak:
                peak = equity
            dd = equity - peak
            if dd < max_dd:
                max_dd = dd
        results.append((y, max_dd, net_r))
    return results


def compute_losing_streaks(filled_trades) -> list[tuple[int, float, str, str]]:
    """Find all consecutive losing streaks.

    Returns: [(streak_length, r_lost, start_date, end_date), ...]
    """
    streaks = []
    current_streak = 0
    current_r_lost = 0.0
    streak_start = None

    for t in filled_trades:
        r = t.r_multiple
        if r < 0:
            if current_streak == 0:
                streak_start = str(t.date)[:10]
            current_streak += 1
            current_r_lost += r
        else:
            if current_streak > 0:
                streaks.append(
                    (current_streak, current_r_lost, streak_start, str(t.date)[:10])
                )
            current_streak = 0
            current_r_lost = 0.0
            streak_start = None

    if current_streak > 0:
        streaks.append(
            (current_streak, current_r_lost, streak_start, str(filled_trades[-1].date)[:10])
        )

    return streaks


def compute_dd_episodes(filled_trades, threshold: float = -10.0):
    """Find all drawdown episodes that exceed the threshold.

    Returns: [(start_date, trough_date, max_dd, recovery_date_or_'ongoing'), ...]
    """
    episodes = []
    equity = 0.0
    peak = 0.0
    in_dd = False
    episode_start = None
    episode_trough = None
    episode_max_dd = 0.0

    for t in filled_trades:
        equity += t.r_multiple
        if equity > peak:
            peak = equity
            if in_dd and episode_max_dd <= threshold:
                episodes.append((episode_start, episode_trough, episode_max_dd, str(t.date)[:10]))
            in_dd = False
        dd = equity - peak
        if dd < 0:
            if not in_dd:
                in_dd = True
                episode_start = str(t.date)[:10]
                episode_max_dd = dd
                episode_trough = str(t.date)[:10]
            if dd < episode_max_dd:
                episode_max_dd = dd
                episode_trough = str(t.date)[:10]

    if in_dd and episode_max_dd <= threshold:
        episodes.append((episode_start, episode_trough, episode_max_dd, "ongoing"))

    return episodes


def _bordered_table(headers, rows, col_aligns=None):
    """Print a bordered table matching the screenshot format.

    col_aligns: list of '<' (left) or '>' (right) per column. Defaults to left.
    """
    n_cols = len(headers)
    if col_aligns is None:
        col_aligns = ['<'] * n_cols

    # Compute column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Add padding
    widths = [w + 2 for w in widths]

    def sep_line():
        return "  +" + "+".join("-" * w for w in widths) + "+"

    def data_line(cells):
        parts = []
        for i, cell in enumerate(cells):
            s = str(cell)
            if col_aligns[i] == '>':
                parts.append(" " + s.rjust(widths[i] - 2) + " ")
            else:
                parts.append(" " + s.ljust(widths[i] - 2) + " ")
        return "  |" + "|".join(parts) + "|"

    print(sep_line())
    print(data_line(headers))
    print(sep_line())
    for row in rows:
        print(data_line(row))
    print(sep_line())


def run_prop_risk_analysis(filled_trades, prop_dd_limit: float = 10.0, label: str = ""):
    """Run full drawdown analysis and print results.

    Args:
        filled_trades: List of TradeResult with exit_type != EXIT_NO_FILL.
        prop_dd_limit: Prop firm max DD in R (e.g., 10.0 for a 10R account).
        label: Optional label for the header.
    """
    if not filled_trades:
        print("  No trades to analyze.")
        return

    safe_thresh = prop_dd_limit * 0.8

    # ── 1. Max DD by Year ─────────────────────────────────────────────
    years = defaultdict(list)
    for t in filled_trades:
        y = str(t.date)[:4]
        years[y].append(t.r_multiple)

    year_data = compute_year_dd(years)

    print()
    print("  Max DD by Year (clean view)")
    print()

    rows = []
    for y, max_dd, net_r in year_data:
        abs_dd = abs(max_dd)
        if abs_dd < safe_thresh:
            verdict = "Safe"
        elif abs_dd < prop_dd_limit:
            verdict = "Close"
        else:
            verdict = "Danger"
        rows.append((y, f"{max_dd:+.1f}R", f"{net_r:+.0f}R", verdict))

    _bordered_table(["Year", "Max DD", "Net R", "Verdict"], rows,
                    col_aligns=['>', '>', '>', '<'])

    safe_count = sum(1 for _, dd, _ in year_data if abs(dd) < safe_thresh)
    close_count = sum(1 for _, dd, _ in year_data if safe_thresh <= abs(dd) < prop_dd_limit)
    danger_count = sum(1 for _, dd, _ in year_data if abs(dd) >= prop_dd_limit)
    total_years = len(year_data)

    print()
    danger_yrs = [y for y, dd, _ in year_data if abs(dd) >= prop_dd_limit]
    close_yrs = [y for y, dd, _ in year_data if safe_thresh <= abs(dd) < prop_dd_limit]

    summary = f"  On a {prop_dd_limit:.0f}R prop account: {safe_count} of {total_years} years stay safe (<-{safe_thresh:.0f}R)"
    if close_count > 0:
        summary += f", {close_count} years get close (-{safe_thresh:.0f} to -{prop_dd_limit:.0f}R)"
    if danger_count > 0:
        summary += f",\n  and {danger_count} year(s) breach the limit ({', '.join(danger_yrs)})."
    else:
        summary += ", and no years breach the limit."

    # Add context line
    net_rs = [net_r for _, _, net_r in year_data]
    min_r, max_r = min(net_rs), max(net_rs)
    if danger_count <= 1:
        if danger_count == 1:
            summary += f"\n  Only {danger_yrs[0]} would be a problem stretch."
        summary += f" Most years the strategy makes {min_r:+.0f} to {max_r:+.0f}R"
        overall_max_dd = min(dd for _, dd, _ in year_data)
        if abs(overall_max_dd) < prop_dd_limit:
            summary += f" while never touching\n  -{prop_dd_limit:.0f}R."
        else:
            summary += "."
    print(summary)

    # ── 2. DD Episodes ────────────────────────────────────────────────
    episodes = compute_dd_episodes(filled_trades, threshold=-prop_dd_limit)

    print()
    print()
    print("=" * 60)
    print(f"  DD EPISODES EXCEEDING -{prop_dd_limit:.0f}R")
    print("=" * 60)
    print()
    if episodes:
        print(f"  {len(episodes)} episode(s):")
        print()
        rows = []
        for start, trough, dd, recov in episodes:
            rows.append((start, trough, f"{dd:+.1f}R", recov))
        _bordered_table(["Start", "Trough", "Max DD", "Recovery"], rows,
                        col_aligns=['<', '<', '>', '<'])
    else:
        print(f"  None — max DD never exceeded -{prop_dd_limit:.0f}R.")

    # ── 3. Consecutive Loss Analysis ──────────────────────────────────
    streaks = compute_losing_streaks(filled_trades)

    print()
    print()
    print("=" * 60)
    print("  CONSECUTIVE LOSS ANALYSIS")
    print("=" * 60)

    if streaks:
        streaks_by_r = sorted(streaks, key=lambda x: x[1])
        n_show = min(10, len(streaks_by_r))
        print()
        print(f"  WORST {n_show} LOSING STREAKS (by R lost):")
        print(f"  {'Losses':>6s} {'R Lost':>8s}  {'Start':<12s}  {'End':<12s}")
        print()
        for losses, r_lost, start, end in streaks_by_r[:n_show]:
            print(f"  {losses:>6d} {r_lost:>+7.1f}R  {start:<12s}  {end:<12s}")

        streak_counts = Counter(s[0] for s in streaks)
        print()
        print(f"  Streak distribution:")
        for length in sorted(streak_counts.keys()):
            print(f"    {length} consecutive losses: {streak_counts[length]} times")
    else:
        print("  No losing streaks found.")

    # ── 4. Monthly R ──────────────────────────────────────────────────
    monthly = defaultdict(float)
    for t in filled_trades:
        key = str(t.date)[:7]
        monthly[key] += t.r_multiple

    print()
    print()
    print("=" * 60)
    print("  MONTHLY R")
    print("=" * 60)
    print()

    worst_months = sorted(monthly.items(), key=lambda x: x[1])[:5]
    best_months = sorted(monthly.items(), key=lambda x: x[1], reverse=True)[:5]

    for m, r in sorted(monthly.items()):
        print(f"  {m}: {r:>+7.1f}R")

    print()
    print(f"  Best 5 months:  {', '.join(f'{m}({r:+.0f}R)' for m, r in best_months)}")
    print(f"  Worst 5 months: {', '.join(f'{m}({r:+.0f}R)' for m, r in worst_months)}")

    neg_months = sum(1 for r in monthly.values() if r < 0)
    total_months = len(monthly)
    print(f"  Negative months: {neg_months}/{total_months} ({neg_months/total_months:.0%})")

    print()
