#!/usr/bin/env python3
"""Build a repo-derived Scale Yourself report for trading_engine.

The report intentionally uses observable local evidence only: git history,
the backtesting experiment database, and tracked research artifacts. It avoids
including proprietary code or internals while still showing throughput.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import sqlite3
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports" / "scale-yourself"
DB_PATH = ROOT / "backtesting" / "data" / "results" / "experiments.db"
MANUAL_BACKTEST_STATS = {
    "label": "Manual dashboard backtesting",
    "trades": 667,
    "source": "User-provided backtesting dashboard screenshot from 2026-05-21.",
}


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()


def git_monthly_activity() -> dict[str, dict[str, int]]:
    raw = run(
        [
            "git",
            "log",
            "--all",
            "--date=format:%Y-%m",
            "--pretty=format:--MONTH--%ad",
            "--numstat",
        ]
    )
    monthly: dict[str, dict[str, int]] = defaultdict(
        lambda: {"commits": 0, "insertions": 0, "deletions": 0}
    )
    month = ""
    for line in raw.splitlines():
        if line.startswith("--MONTH--"):
            month = line.removeprefix("--MONTH--")
            monthly[month]["commits"] += 1
            continue
        parts = line.split()
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and month:
            monthly[month]["insertions"] += int(parts[0])
            monthly[month]["deletions"] += int(parts[1])
    return dict(monthly)


def git_summary() -> dict[str, object]:
    all_dates = run(["git", "log", "--all", "--reverse", "--date=short", "--pretty=format:%ad"]).splitlines()
    first = all_dates[0] if all_dates else "unknown"
    last = run(["git", "log", "--all", "--date=short", "--pretty=format:%ad", "-n", "1"])
    commits = int(run(["git", "rev-list", "--all", "--count"]))
    files_by_area: dict[str, int] = defaultdict(int)
    for path in run(["git", "ls-files"]).splitlines():
        top = path.split("/", 1)[0]
        files_by_area[top if top in {"backtesting", "execution", "frontend", "pinescript"} else "root/other"] += 1
    return {
        "first_commit": first,
        "last_commit": last,
        "commits": commits,
        "files_by_area": dict(sorted(files_by_area.items())),
    }


def experiment_monthly_activity() -> dict[str, dict[str, float]]:
    if not DB_PATH.exists():
        return {}
    monthly: dict[str, dict[str, float]] = defaultdict(
        lambda: {"runs": 0, "trades": 0, "total_r": 0.0, "optimizations": 0, "sweep_combinations": 0}
    )
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            select substr(timestamp, 1, 7) as month,
                   count(*) as runs,
                   coalesce(sum(total_trades), 0) as trades,
                   coalesce(sum(total_r), 0) as total_r
            from runs
            group by month
            order by month
            """
        ):
            monthly[row["month"]]["runs"] = int(row["runs"])
            monthly[row["month"]]["trades"] = int(row["trades"])
            monthly[row["month"]]["total_r"] = float(row["total_r"])
        for row in conn.execute(
            """
            select substr(timestamp, 1, 7) as month,
                   count(*) as optimizations,
                   coalesce(sum(total_combinations), 0) as sweep_combinations
            from optimizations
            group by month
            order by month
            """
        ):
            monthly[row["month"]]["optimizations"] = int(row["optimizations"])
            monthly[row["month"]]["sweep_combinations"] = int(row["sweep_combinations"])
    return dict(monthly)


def experiment_summary() -> dict[str, object]:
    if not DB_PATH.exists():
        return {
            "runs": 0,
            "optimizations": 0,
            "trades": 0,
            "total_r": 0.0,
            "by_instrument": [],
            "first_saved_run": "",
            "last_saved_run": "",
            "saved_run_calendar_days": 0.0,
            "history_start": "",
            "history_end": "",
            "cumulative_historical_years": 0.0,
            "dated_runs": 0,
        }
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        runs, trades, total_r = conn.execute(
            "select count(*), coalesce(sum(total_trades), 0), coalesce(sum(total_r), 0) from runs"
        ).fetchone()
        optimizations = conn.execute("select count(*) from optimizations").fetchone()[0]
        first_saved_run, last_saved_run = conn.execute("select min(timestamp), max(timestamp) from runs").fetchone()
        history_start, history_end = conn.execute(
            """
            select min(date_start), max(date_end)
            from runs
            where date_start is not null and date_start != ''
              and date_end is not null and date_end != ''
            """
        ).fetchone()
        dated_rows = conn.execute(
            """
            select date_start, date_end
            from runs
            where date_start is not null and date_start != ''
              and date_end is not null and date_end != ''
            """
        ).fetchall()
        by_instrument = [
            dict(row)
            for row in conn.execute(
                """
                select instrument,
                       count(*) as runs,
                       coalesce(sum(total_trades), 0) as trades,
                       round(coalesce(sum(total_r), 0), 1) as total_r
                from runs
                group by instrument
                order by runs desc
                limit 7
                """
            )
        ]
    saved_run_calendar_days = 0.0
    if first_saved_run and last_saved_run:
        start_dt = dt.datetime.fromisoformat(first_saved_run.replace("Z", "+00:00"))
        end_dt = dt.datetime.fromisoformat(last_saved_run.replace("Z", "+00:00"))
        saved_run_calendar_days = (end_dt - start_dt).total_seconds() / 86400
    cumulative_days = 0
    for row in dated_rows:
        start_date = dt.date.fromisoformat(row["date_start"])
        end_date = dt.date.fromisoformat(row["date_end"])
        cumulative_days += (end_date - start_date).days + 1
    return {
        "runs": int(runs),
        "optimizations": int(optimizations),
        "trades": int(trades),
        "total_r": float(total_r),
        "by_instrument": by_instrument,
        "first_saved_run": first_saved_run,
        "last_saved_run": last_saved_run,
        "saved_run_calendar_days": saved_run_calendar_days,
        "history_start": history_start,
        "history_end": history_end,
        "cumulative_historical_years": cumulative_days / 365.25,
        "dated_runs": len(dated_rows),
    }


def artifact_summary() -> dict[str, int]:
    tracked = run(["git", "ls-files"]).splitlines()
    return {
        "tracked_files": len(tracked),
        "learning_docs": sum(1 for p in tracked if p.startswith("backtesting/learnings/") and p.endswith(".md")),
        "research_reports": sum(1 for p in tracked if p.startswith("backtesting/learnings/reports/") and p.endswith(".md")),
        "pinescript_files": sum(1 for p in tracked if p.startswith("pinescript/")),
        "frontend_files": sum(1 for p in tracked if p.startswith("frontend/src/")),
        "execution_files": sum(1 for p in tracked if p.startswith("execution/src/") or p.startswith("execution/scripts/")),
    }


def write_chart(rows: list[dict[str, object]], path: Path) -> None:
    width = 920
    height = 440
    pad_l = 80
    pad_r = 36
    pad_t = 36
    pad_b = 76
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    engine_trades = sum(int(row["research_trades"]) for row in rows)
    manual_trades = MANUAL_BACKTEST_STATS["trades"]
    multiple = engine_trades / manual_trades if manual_trades else 0
    bars = [
        ("Manual dashboard", manual_trades, "#f59e0b"),
        ("AI-built engine", engine_trades, "#2563eb"),
    ]
    max_value = max(value for _label, value, _color in bars)

    def bar_width(value: float) -> float:
        return (value / max_value) * chart_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Manual versus engine backtesting scale chart">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="Inter, Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">Backtesting Scale: Manual vs Engine</text>',
        '<text x="24" y="52" font-family="Inter, Arial, sans-serif" font-size="12" fill="#4b5563">Trades reviewed manually vs simulated trades saved by the research engine</text>',
    ]
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + chart_h + 18}" x2="{width-pad_r}" y2="{pad_t + chart_h + 18}" stroke="#d1d5db"/>')
    for idx, (label, value, color) in enumerate(bars):
        y = 132 + idx * 112
        w = bar_width(value)
        parts.append(f'<text x="{pad_l}" y="{y-18}" font-family="Inter, Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">{html.escape(label)}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y}" width="{chart_w}" height="34" rx="8" fill="#eef2f7"/>')
        parts.append(
            f'<rect x="{pad_l}" y="{y}" width="{max(w, 4):.1f}" height="34" rx="8" fill="{color}">'
            f'<title>{html.escape(label)}: {value:,} trades</title></rect>'
        )
        value_x = min(pad_l + max(w, 4) + 12, width - pad_r - 154)
        if w > 180:
            value_x = pad_l + w - 152
        parts.append(f'<text x="{value_x:.1f}" y="{y+23}" font-family="Inter, Arial, sans-serif" font-size="14" font-weight="700" fill="#111827">{value:,} trades</text>')
    parts.append(f'<text x="{pad_l}" y="336" font-family="Inter, Arial, sans-serif" font-size="42" font-weight="800" fill="#111827">{multiple:,.0f}x</text>')
    parts.append('<text x="194" y="326" font-family="Inter, Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">more trade observations</text>')
    parts.append(f'<text x="194" y="348" font-family="Inter, Arial, sans-serif" font-size="13" fill="#4b5563">{engine_trades:,} saved simulated trades compared with {manual_trades:,} manually reviewed trades.</text>')
    parts.append('<text x="80" y="408" font-family="Inter, Arial, sans-serif" font-size="12" fill="#6b7280">Manual stats from user-provided dashboard screenshot; engine stats from backtesting/data/results/experiments.db.</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def short_summary(summary: dict[str, object]) -> str:
    return (
        "Prior to this engine, I used a paid platform called FXReplay to conduct all my backtests for "
        "optimizing and collecting \"data\" on my strategies. On this platform I would manually rewind "
        "the price action on a chart, replay it bar by bar and record trades manually. Totalling over "
        "~30 hours, I managed to collected about 667 trades worth of data. I used Claude Code and Codex "
        "to help turn that workflow into a repeatable futures research system: strategy configs, saved "
        "backtests, experiment tracking, research notes, TradingView parity work, execution plumbing, "
        "and dashboard review all living in one loop."
    )


def write_pdf(path: Path, summary: dict[str, object], experiments: dict[str, object], artifacts: dict[str, int], rows: list[dict[str, object]]) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph

    width, height = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    margin = 0.55 * inch
    content_w = width - 2 * margin
    y = height - margin

    title_style = ParagraphStyle(
        "Title",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#111827"),
    )
    heading_style = ParagraphStyle(
        "Heading",
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceAfter=5,
    )

    def draw_paragraph(text: str, style: ParagraphStyle, x: float, top_y: float, w: float) -> float:
        p = Paragraph(html.escape(text), style)
        _pw, ph = p.wrap(w, top_y)
        p.drawOn(c, x, top_y - ph)
        return top_y - ph

    y = draw_paragraph("Scale Yourself Report: Trading Engine", title_style, margin, y, content_w)
    y -= 6

    y = draw_paragraph("Short Summary", heading_style, margin, y, content_w)
    y -= 2
    y = draw_paragraph(short_summary(summary), body_style, margin, y, content_w)
    y -= 18

    chart_x = margin
    chart_y = y - 216
    chart_w = content_w
    chart_h = 204
    manual_trades = MANUAL_BACKTEST_STATS["trades"]
    engine_trades = int(experiments["trades"])
    multiple = engine_trades / manual_trades if manual_trades else 0
    max_value = max(manual_trades, engine_trades)

    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setFillColor(colors.white)
    c.roundRect(chart_x, chart_y, chart_w, chart_h, 8, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(chart_x + 18, chart_y + chart_h - 24, "Backtesting Scale: Manual vs Engine")
    c.setFillColor(colors.HexColor("#4b5563"))
    c.setFont("Helvetica", 7.2)
    c.drawString(chart_x + 18, chart_y + chart_h - 36, "Trades reviewed manually vs simulated trades saved by the research engine")

    bar_x = chart_x + 48
    bar_w = chart_w - 86
    bar_h = 15
    bar_rows = [
        ("Manual dashboard", manual_trades, colors.HexColor("#f59e0b"), chart_y + chart_h - 84),
        ("AI-built engine", engine_trades, colors.HexColor("#2563eb"), chart_y + chart_h - 132),
    ]
    for label, value, color, by in bar_rows:
        c.setFillColor(colors.HexColor("#111827"))
        c.setFont("Helvetica-Bold", 7.8)
        c.drawString(bar_x, by + 22, label)
        c.setFillColor(colors.HexColor("#eef2f7"))
        c.roundRect(bar_x, by, bar_w, bar_h, 4, fill=1, stroke=0)
        fill_w = max((value / max_value) * bar_w, 3)
        c.setFillColor(color)
        c.roundRect(bar_x, by, fill_w, bar_h, 4, fill=1, stroke=0)
        text = f"{value:,} trades"
        c.setFillColor(colors.HexColor("#111827"))
        c.setFont("Helvetica-Bold", 7.2)
        if fill_w > 130:
            c.drawRightString(bar_x + fill_w - 18, by + 4.5, text)
        else:
            c.drawString(bar_x + fill_w + 8, by + 4.5, text)

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(bar_x, chart_y + 44, f"{multiple:,.0f}x")
    c.setFont("Helvetica-Bold", 7.8)
    c.drawString(bar_x + 54, chart_y + 54, "more trade observations")
    c.setFont("Helvetica", 7.0)
    c.setFillColor(colors.HexColor("#4b5563"))
    c.drawString(bar_x + 54, chart_y + 42, f"{engine_trades:,} saved simulated trades compared with {manual_trades:,} manually reviewed trades.")
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(bar_x, chart_y + 28, chart_x + chart_w - 48, chart_y + 28)
    c.setFont("Helvetica", 6.4)
    c.drawString(bar_x, chart_y + 12, "Manual stats from user-provided dashboard screenshot; engine stats from backtesting/data/results/experiments.db.")

    y = chart_y - 24
    y = draw_paragraph("Key Metrics", heading_style, margin, y, content_w)
    y -= 2
    metrics = [
        f"{summary['commits']:,} commits across the measured window.",
        f"{sum(row['loc_changed'] for row in rows):,} total changed lines recorded by git numstat.",
        f"{experiments['runs']:,} saved backtest runs in backtesting/data/results/experiments.db.",
        f"{experiments['trades']:,} simulated trades represented by those saved runs.",
        f"{multiple:,.0f}x more saved simulated trade observations than the {manual_trades:,} manually reviewed trades shown in the dashboard screenshot.",
        f"{experiments['optimizations']:,} saved optimization records, covering {sum(row['sweep_combinations'] for row in rows):,} parameter combinations.",
        f"{artifacts['research_reports']:,} tracked long-form research reports under backtesting/learnings/reports/.",
        f"{artifacts['learning_docs']:,} tracked learning-memory Markdown files under backtesting/learnings/.",
    ]
    c.setFont("Helvetica", 8.8)
    c.setFillColor(colors.HexColor("#111827"))
    for metric in metrics:
        bullet = Paragraph(f"&bull; {html.escape(metric)}", body_style)
        _bw, bh = bullet.wrap(content_w, y)
        bullet.drawOn(c, margin, y - bh)
        y -= bh + 2

    c.setFont("Helvetica", 6.6)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(margin, 0.35 * inch, "Generated from local git history, the experiment database, and the user-provided manual backtesting dashboard screenshot.")
    c.save()


def write_commit_chart(rows: list[dict[str, object]], path: Path) -> None:
    width = 920
    height = 440
    pad_l = 72
    pad_r = 36
    pad_t = 36
    pad_b = 76
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    running_total = 0
    cumulative_rows = []
    for row in rows:
        running_total += int(row["commits"])
        cumulative_rows.append({**row, "cumulative_commits": running_total})
    max_value = max([int(row["cumulative_commits"]) for row in cumulative_rows] + [1])

    def y_for(value: float) -> float:
        return pad_t + chart_h - (value / max_value) * chart_h

    def x_for(idx: int) -> float:
        if len(rows) == 1:
            return pad_l + chart_w / 2
        return pad_l + (idx / (len(rows) - 1)) * chart_w

    points = [
        (x_for(idx), y_for(int(row["cumulative_commits"])), int(row["cumulative_commits"]), str(row["month"]))
        for idx, row in enumerate(cumulative_rows)
    ]
    point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y, _value, _month in points)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Cumulative git commits chart">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="Inter, Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">Cumulative Git Commits</text>',
        '<text x="24" y="52" font-family="Inter, Arial, sans-serif" font-size="12" fill="#4b5563">Running total from git log --all</text>',
    ]
    for i in range(5):
        value = max_value * i / 4
        y = y_for(value)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" font-family="Inter, Arial, sans-serif" font-size="11" fill="#6b7280">{value:,.0f}</text>')
    for idx, row in enumerate(rows):
        x = x_for(idx)
        parts.append(f'<text x="{x:.1f}" y="{height-44}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="12" fill="#374151">{html.escape(str(row["month"]))}</text>')
    parts.append(f'<polyline points="{point_string}" fill="none" stroke="#2563eb" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y, value, month in points:
        label = f"{month}: {value:,} cumulative commits"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#ffffff" stroke="#2563eb" stroke-width="3">'
            f'<title>{html.escape(label)}</title></circle>'
        )
        label_y = y - 14 if y > pad_t + 24 else y + 26
        parts.append(f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="12" font-weight="700" fill="#1d4ed8">{value:,}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "month",
                "commits",
                "insertions",
                "deletions",
                "loc_changed",
                "research_runs",
                "research_trades",
                "research_total_r",
                "optimizations",
                "sweep_combinations",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_report(rows: list[dict[str, object]], summary: dict[str, object], experiments: dict[str, object], artifacts: dict[str, int]) -> str:
    by_instrument = experiments["by_instrument"]
    top_instrument_lines = "\n".join(
        f"- {row['instrument']}: {row['runs']:,} saved runs, {row['trades']:,} simulated trades, {row['total_r']:,} total R"
        for row in by_instrument
    )
    monthly_lines = "\n".join(
        "| {month} | {commits:,} | {loc_changed:,} | {research_runs:,} | {research_trades:,} | {optimizations:,} |".format(**row)
        for row in rows
    )
    files_by_area = summary["files_by_area"]
    area_lines = "\n".join(f"- {area}: {count:,} tracked files" for area, count in files_by_area.items())
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    manual_trades = MANUAL_BACKTEST_STATS["trades"]
    trade_multiple = experiments["trades"] / manual_trades if manual_trades else 0
    return f"""# Scale Yourself Report: Trading Engine

Generated: {generated_at}

## Short summary

{short_summary(summary)}

This report does not claim access to raw Codex token history. It uses local evidence that can be audited from the repo: git history, the experiment database, tracked research artifacts, and the user-provided manual backtesting dashboard screenshot.

## Key metrics

- {summary['commits']:,} commits across the measured window.
- {sum(row['loc_changed'] for row in rows):,} total changed lines recorded by git numstat.
- {experiments['runs']:,} saved backtest runs in `backtesting/data/results/experiments.db`.
- {experiments['trades']:,} simulated trades represented by those saved runs.
- {trade_multiple:,.0f}x more saved simulated trade observations than the {manual_trades:,} manually reviewed trades shown in the dashboard screenshot.
- {experiments['optimizations']:,} saved optimization records, covering {sum(row['sweep_combinations'] for row in rows):,} parameter combinations.
- {artifacts['research_reports']:,} tracked long-form research reports under `backtesting/learnings/reports/`.
- {artifacts['learning_docs']:,} tracked learning-memory Markdown files under `backtesting/learnings/`.

![Manual baseline versus cumulative engine backtesting scale](monthly_throughput.svg)

## Manual backtesting vs engine scale

The clearest leverage signal is not a commit curve. This repository started while I was already using AI, so git history does not show a clean before/after inflection. The stronger comparison is the manual backtesting ceiling versus the AI-built research engine.

Manual dashboard baseline:

- Trades reviewed: {manual_trades:,}.

Engine output:

- Saved backtest runs: {experiments['runs']:,}.
- Simulated trades: {experiments['trades']:,}.
- Trade-observation multiple: {trade_multiple:,.0f}x the manually reviewed trade count.
- Optimization records: {experiments['optimizations']:,}, covering {sum(row['sweep_combinations'] for row in rows):,} parameter combinations.

## Monthly throughput

| Month | Commits | LOC changed | Saved research runs | Simulated trades | Optimizations |
| --- | ---: | ---: | ---: | ---: | ---: |
{monthly_lines}

## What scaled

The biggest improvement was not only writing more code. It was compressing the loop from idea to evidence:

1. Strategy hypothesis becomes configurable engine behavior.
2. Backtest or sweep becomes a saved database record.
3. Results become a research report or learning-memory update.
4. Promising ideas are promoted toward dashboard review, TradingView parity, or execution replay.

That loop created measurable leverage: March alone produced {next((row['research_runs'] for row in rows if row['month'] == '2026-03'), 0):,} saved research runs and {next((row['research_trades'] for row in rows if row['month'] == '2026-03'), 0):,} simulated trades, while the repo also had {next((row['commits'] for row in rows if row['month'] == '2026-03'), 0):,} commits.

## Examples

- Backtesting/research engine: ORB, FVG, LSI, HTF-LSI, CISD, IB, VWAP, gap-fill, news, regime, and portfolio workflows are represented in `backtesting/`.
- Experiment tracking: saved runs and optimizations are queryable from the SQLite experiment DB, making research output durable instead of living only in chat.
- Research memory: `backtesting/learnings/` contains reusable strategy findings and promotion reports, including {artifacts['research_reports']:,} tracked report files.
- Execution bridge: `execution/` connects DataBento, execution engines, TradersPost service behavior, historical replay, and deploy configs.
- Frontend review loop: `frontend/` contains the React dashboard used to inspect research and execution outputs.
- TradingView parity: `pinescript/` contains alert-parity and reference scripts so research can be compared against chart behavior.

## Research output by instrument

{top_instrument_lines}

## Repo surface area

{area_lines}

## Measurement notes

- Git activity comes from `git log --all --numstat`, grouped by commit month.
- Research activity comes from `backtesting/data/results/experiments.db`.
- Manual baseline stats come from the user-provided backtesting dashboard screenshot dated 2026-05-21.
- The root `backtesting/experiments.db` currently has no tables; the active experiment store is `backtesting/data/results/experiments.db`.
- LOC changed is a throughput proxy, not a quality metric. The stronger signal is the linked loop of implementation, saved experiments, research reports, and deployability review.
- Raw Codex tokens were not available, so this report uses output-side proxies instead of token-side telemetry.
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    git_activity = git_monthly_activity()
    exp_activity = experiment_monthly_activity()
    months = sorted(set(git_activity) | set(exp_activity))
    rows: list[dict[str, object]] = []
    for month in months:
        git_row = git_activity.get(month, {})
        exp_row = exp_activity.get(month, {})
        insertions = int(git_row.get("insertions", 0))
        deletions = int(git_row.get("deletions", 0))
        rows.append(
            {
                "month": month,
                "commits": int(git_row.get("commits", 0)),
                "insertions": insertions,
                "deletions": deletions,
                "loc_changed": insertions + deletions,
                "research_runs": int(exp_row.get("runs", 0)),
                "research_trades": int(exp_row.get("trades", 0)),
                "research_total_r": round(float(exp_row.get("total_r", 0)), 1),
                "optimizations": int(exp_row.get("optimizations", 0)),
                "sweep_combinations": int(exp_row.get("sweep_combinations", 0)),
            }
        )
    write_csv(rows, OUT_DIR / "scale_yourself_metrics.csv")
    write_chart(rows, OUT_DIR / "monthly_throughput.svg")
    write_commit_chart(rows, OUT_DIR / "cumulative_commits.svg")
    summary = git_summary()
    experiments = experiment_summary()
    artifacts = artifact_summary()
    write_pdf(OUT_DIR / "scale_yourself_report.pdf", summary, experiments, artifacts, rows)
    report = build_report(rows, summary, experiments, artifacts)
    (OUT_DIR / "scale_yourself_report.md").write_text(report)
    print(OUT_DIR / "scale_yourself_report.md")
    print(OUT_DIR / "scale_yourself_report.pdf")


if __name__ == "__main__":
    main()
