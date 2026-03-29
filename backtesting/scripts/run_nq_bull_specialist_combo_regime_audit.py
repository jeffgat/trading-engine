#!/usr/bin/env python3
"""Audit the optimized NQ 4-leg combo by year, regime, and leg."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import build_nq_ny_regime_calendar  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_papertrade_optimized_last5y"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_regime_audit_last5y"


def summarize(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    out = (
        frame.groupby(by, dropna=False)
        .agg(
            trades=("r_multiple", "size"),
            net_r=("r_multiple", "sum"),
            pnl_usd=("pnl_usd", "sum"),
            avg_r=("r_multiple", "mean"),
        )
        .reset_index()
    )
    out["net_r"] = out["net_r"].round(6)
    out["pnl_usd"] = out["pnl_usd"].round(2)
    out["avg_r"] = out["avg_r"].round(6)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--start", default="2021-03-29")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(input_dir / "combo_trades.csv")
    trades["date"] = pd.to_datetime(trades["date"])
    trades["year"] = trades["date"].dt.year.astype(str)
    trades["r_multiple"] = trades["r_multiple"].astype(float)
    trades["pnl_usd"] = trades["pnl_usd"].astype(float)

    df_5m = load_5m_data(NQ.data_file, start=args.start)
    calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start)
    calendar["year"] = pd.to_datetime(calendar["date"]).dt.year.astype(str)

    merged = trades.merge(
        calendar[["date", "year", "regime", "low_confidence"]],
        on=["date", "year"],
        how="left",
    )

    year_summary = summarize(merged, ["year"])
    regime_summary = summarize(merged, ["regime"]).sort_values("net_r", ascending=False)
    year_regime_summary = summarize(merged, ["year", "regime"])
    leg_year_summary = summarize(merged, ["leg_name", "year"])
    leg_regime_summary = summarize(merged, ["leg_name", "regime"])
    leg_year_regime_summary = summarize(merged, ["year", "leg_name", "regime"])
    low_conf_summary = summarize(merged, ["low_confidence"])
    calendar_regime_days = (
        calendar[
            (calendar["date"] >= merged["date"].min()) & (calendar["date"] <= merged["date"].max())
        ]
        .groupby(["year", "regime"], dropna=False)
        .size()
        .reset_index(name="days")
    )

    year_summary.to_csv(output_dir / "year_summary.csv", index=False)
    regime_summary.to_csv(output_dir / "regime_summary.csv", index=False)
    year_regime_summary.to_csv(output_dir / "year_regime_summary.csv", index=False)
    leg_year_summary.to_csv(output_dir / "leg_year_summary.csv", index=False)
    leg_regime_summary.to_csv(output_dir / "leg_regime_summary.csv", index=False)
    leg_year_regime_summary.to_csv(output_dir / "leg_year_regime_summary.csv", index=False)
    low_conf_summary.to_csv(output_dir / "low_confidence_summary.csv", index=False)
    calendar_regime_days.to_csv(output_dir / "calendar_regime_days.csv", index=False)

    by_year = {row["year"]: row for _, row in year_summary.iterrows()}
    by_regime = {row["regime"]: row for _, row in regime_summary.iterrows()}
    y22 = by_year.get("2022")
    y23 = by_year.get("2023")
    bear = by_regime.get("bear")
    bull = by_regime.get("bull")
    sideways = by_regime.get("sideways")

    summary_lines = [
        "# NQ 4-Leg Combo Regime Audit",
        "",
        "## Scope",
        "",
        f"- Input package: `{input_dir}`.",
        f"- Filled-trade coverage: `{merged['date'].min().date()}` to `{merged['date'].max().date()}`.",
        f"- Total filled trades audited: `{len(merged)}`.",
        "",
        "## Headline Read",
        "",
        "- This combo is not behaving like a pure bull-regime portfolio.",
        "- Only `bull_specialist` is truly regime-specialized; the other three legs are long-biased but not regime-routed.",
        f"- Bear-regime trades contributed `{bear['net_r']:.2f}R` across `{int(bear['trades'])}` trades, versus `{bull['net_r']:.2f}R` in bull and `{sideways['net_r']:.2f}R` in sideways.",
        "",
        "## 2022-2023 Snapshot",
        "",
        f"- 2022: `{y22['net_r']:.2f}R` on `{int(y22['trades'])}` trades.",
        f"- 2023: `{y23['net_r']:.2f}R` on `{int(y23['trades'])}` trades.",
        "- The strongest 2022 contribution came from `nq_asia`, not from the bull specialist.",
        "- The strongest 2023 contributions came from `nq_asia` and `nq_ny_lsi`, with the bull specialist helping only in actual bull-regime windows.",
        "",
        "## Interpretation",
        "",
        "- The combo currently acts like a long-biased multi-session payout engine with a bull-specialist core, not a regime-specialist portfolio.",
        "- If the design goal is strict regime specialization, this audit is a warning sign rather than a success confirmation.",
        "- If the design goal is funded-account payout speed with acceptable breach risk, the combo can still be useful, but it should be labeled honestly as a mixed-regime long combo.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
