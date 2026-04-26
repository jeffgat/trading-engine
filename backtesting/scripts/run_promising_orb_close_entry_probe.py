"""Run close-entry probe on promising non-ALPHA_V1 ORB candidates.

This reuses the experimental market-at-close harness from
``run_alpha_v1_orb_close_entry_probe.py`` and applies it to ORB candidates that
were not selected for ALPHA_V1 but remain worth remembering:
- NQ Asia-2 phase-one winner / backup
- GC NY R3 continuation longs
- GC Asia-1 continuation both-directions
"""

from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC, NQ
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

import run_alpha_v1_orb_close_entry_probe as close_probe


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "promising_orb_close_entry_probe"
REPORT_PATH = ROOT / "learnings" / "reports" / "PROMISING_ORB_CLOSE_ENTRY_PROBE.md"


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    label: str
    config: StrategyConfig
    notes: str


def build_candidates() -> list[CandidateSpec]:
    nq_asia_2_session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="23:15",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=100.0,
        min_gap_atr_pct=1.0,
    )
    nq_asia_2 = StrategyConfig(
        sessions=(nq_asia_2_session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.6,
        atr_length=14,
        name="NQ Asia-2 15m ORB100 RR3.5 TP0.6 ungated",
        notes="Promising NQ Asia phase-one backup; run ungated for this close-entry probe.",
    )

    gc_ny_r3_session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:38",
        entry_start="09:38",
        entry_end="12:00",
        flat_start="13:30",
        flat_end="16:00",
        stop_atr_pct=4.5,
        min_gap_atr_pct=3.0,
    )
    gc_ny_r3 = StrategyConfig(
        sessions=(gc_ny_r3_session,),
        instrument=GC,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=9.0,
        tp1_ratio=0.35,
        atr_length=7,
        impulse_close_filter=True,
        excluded_days=(4,),
        excluded_dates=FOMC_DATES,
        name="GC NY R3 Cont Longs High-RR Fri/FOMC Excl",
        notes="Paused ALPHA candidate; strongest WF validated GC continuation leg but prop/instrument constraints blocked inclusion.",
    )

    gc_asia_1_session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:30",
        entry_start="20:30",
        entry_end="23:15",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=25.0,
        min_gap_atr_pct=1.0,
    )
    gc_asia_1 = StrategyConfig(
        sessions=(gc_asia_1_session,),
        instrument=GC,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.5,
        tp1_ratio=0.6,
        atr_length=14,
        name="GC Asia-1 30m ORB25 RR2.5 TP0.6 both ungated",
        notes="Promising GC commodity diversifier; ALPHA excluded due Apex GC restriction.",
    )

    return [
        CandidateSpec(
            key="nq_asia_2_backup",
            label="NQ Asia-2 backup",
            config=nq_asia_2,
            notes="High-flow NQ Asia backup. Latest regime round preferred ungated; earlier notes still flag regime-gate follow-up.",
        ),
        CandidateSpec(
            key="gc_ny_r3_paused",
            label="GC NY R3 paused",
            config=gc_ny_r3,
            notes="Paused only because GC is banned on Apex and RR9 is operationally awkward at standard prop sizing.",
        ),
        CandidateSpec(
            key="gc_asia_1_diversifier",
            label="GC Asia-1 diversifier",
            config=gc_asia_1,
            notes="Both-direction GC Asia continuation. Gated version was preferred elsewhere, but this probe keeps the raw signal definition.",
        ),
    ]


def _metrics_row(
    candidate: CandidateSpec,
    variant: str,
    trades,
    baseline_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = close_probe._metrics_row(candidate.label, variant, trades, baseline_metrics)
    row["key"] = candidate.key
    row["notes"] = candidate.notes
    return row


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for candidate in build_candidates():
        config = candidate.config
        print(f"[probe] Loading {candidate.label} ({config.instrument.symbol})", flush=True)
        market = close_probe._load_or_resample_market_data(config)

        print(f"[probe] Baseline retest {candidate.label}", flush=True)
        baseline = run_backtest(
            market.df_5m,
            config,
            start_date=close_probe.FULL_START,
            end_date=close_probe.AVAILABLE_END,
            df_1m=market.df_1m,
            df_1s=market.df_1s,
            _maps=market.maps,
        )
        if config.excluded_days:
            baseline = apply_dow_filter(baseline, set(config.excluded_days))
        baseline_metrics = compute_metrics(baseline)
        rows.append(_metrics_row(candidate, "baseline_retest", baseline))

        for mode in ("fvg_close", "breakout_close"):
            print(f"[probe] {mode} {candidate.label}", flush=True)
            trades = close_probe._run_close_variant(config, market, mode)
            rows.append(_metrics_row(candidate, mode, trades, baseline_metrics))

        del market
        gc.collect()

    payload = {
        "scope": {
            "start": close_probe.FULL_START,
            "end": close_probe.AVAILABLE_END,
            "holdout_start": close_probe.HOLDOUT_START,
            "candidate_count": len(build_candidates()),
            "data_notes": [
                "NQ 5m/1m are resampled from NQ_1s.parquet if native files are absent.",
                "Regime gates are not applied in this broad close-entry probe.",
            ],
        },
        "rows": rows,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    columns = [
        "leg",
        "variant",
        "trades",
        "wr_pct",
        "pf",
        "net_r",
        "max_dd_r",
        "sharpe",
        "neg_years",
        "holdout_trades",
        "holdout_net_r",
        "holdout_dd_r",
        "delta_r",
        "delta_dd",
    ]

    report_lines = [
        "# Promising ORB Close-Entry Probe",
        "",
        f"Window: `{close_probe.FULL_START}` to `{close_probe.AVAILABLE_END}`. Holdout shown as `{close_probe.HOLDOUT_START}+`.",
        "",
        "## Takeaway",
        "",
        "- `fvg_close` is a NO-GO across this broader candidate set; it either loses edge outright or worsens drawdown enough to be uninteresting.",
        "- `breakout_close` is still a NO-GO for both GC candidates. It turns `GC NY R3` and `GC Asia-1` structurally negative on full history.",
        "- `NQ Asia-2 breakout_close` is the only candidate worth follow-up: full-history R improved from `+177.8R` to `+285.5R`, and holdout R improved from `+38.3R` to `+71.4R`, but max DD widened from `-17.5R` to `-24.0R` and Sharpe fell from `1.95` to `1.70`.",
        "- Practical read: close-entry remains rejected as a general replacement; the one live thread is a separate NQ Asia-2 high-flow breakout-close branch that needs risk/regime/prop validation before it can matter.",
        "",
        "## Scope",
        "",
        "- Candidates: `NQ Asia-2 backup`, `GC NY R3 paused`, `GC Asia-1 diversifier`.",
        "- Variants match the ALPHA_V1 probe: baseline retest, FVG confirmation close, and first breakout close with no FVG requirement.",
        "- Regime gates are not applied here; this is a broad entry-mechanics screen.",
        "",
        "## Results",
        "",
        close_probe._markdown_table(rows, columns),
        "",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("")
    print(close_probe._markdown_table(rows, ["leg", "variant", "trades", "wr_pct", "pf", "net_r", "max_dd_r", "sharpe", "holdout_net_r"]))
    print(f"\nReport written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
