#!/usr/bin/env python3
"""Run wave-1 ALPHA_V1 downside-variant discovery."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    DEFAULT_HOLDOUT_START,
    OUTPUT_ROOT,
    CandidateSpec,
    DataCache,
    PromotionThresholds,
    baseline_trade_streams,
    build_alpha_v1_legs,
    clone_with_name,
    filled_trades,
    filter_trades_by_combined_regime,
    make_label,
    packet_summary_row,
    research_packet,
    run_candidate_family,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402


FAMILY_ORDER = [
    "es_ny_orb_dual_book",
    "nq_ny_cont_short",
    "nq_ny_lsi_downside",
    "nq_asia_downside_quick",
    "es_asia_downside_quick",
]


def _name(prefix: str, **kwargs: object) -> str:
    parts = [prefix]
    for key, value in kwargs.items():
        safe = str(value).replace(".", "p").replace(":", "")
        parts.append(f"{key}{safe}")
    return "_".join(parts)


def build_es_ny_orb_dual_book_specs() -> list[CandidateSpec]:
    baseline = build_alpha_v1_legs()["es_ny_orb_long"].config
    specs: list[CandidateSpec] = []
    mirror_rr_tp1_pairs = ((4.0, 0.25), (4.0, 0.3), (5.0, 0.2), (5.0, 0.25))

    for rr, tp1 in mirror_rr_tp1_pairs:
        for stop_atr in (5.0, 8.0):
            for gap in (0.25, 0.5):
                for atr_len in (7, 14):
                        session = replace(
                            baseline.sessions[0],
                            stop_atr_pct=stop_atr,
                            min_gap_atr_pct=gap,
                        )
                        config = replace(
                            baseline,
                            sessions=(session,),
                            direction_filter="both",
                            rr=rr,
                            tp1_ratio=tp1,
                            atr_length=atr_len,
                        )
                        name = _name(
                            "es_ny_mirror_both",
                            rr=rr,
                            tp1=tp1,
                            stop=stop_atr,
                            gap=gap,
                            atr=atr_len,
                        )
                        specs.append(
                            CandidateSpec(
                                label=make_label(
                                    family="es_ny_orb_dual_book",
                                    session="NY",
                                    direction_mode="dual_book",
                                    candidate_name=name,
                                ),
                                config=clone_with_name(
                                    config,
                                    name=name,
                                    notes="Mirror sanity check near the live ES NY long anchor.",
                                ),
                                notes="Shared-param both-direction sanity check near the live long anchor.",
                            )
                        )

    short_rr_tp1_pairs = ((2.5, 0.4), (2.5, 0.5), (3.5, 0.3), (3.5, 0.4))
    for orb_end in ("10:00", "10:15"):
        for entry_end in ("11:30", "12:00"):
            for stop_atr in (8.0, 10.0):
                for gap in (0.5, 1.0):
                    for rr, tp1 in short_rr_tp1_pairs:
                        for atr_len in (12, 14):
                                session = SessionConfig(
                                    name="NY",
                                    orb_start="09:30",
                                    orb_end=orb_end,
                                    entry_start=orb_end,
                                    entry_end=entry_end,
                                    flat_start="15:50",
                                    flat_end="16:00",
                                    stop_atr_pct=stop_atr,
                                    min_gap_atr_pct=gap,
                                    min_stop_points=3.0,
                                    min_tp1_points=3.0,
                                )
                                config = StrategyConfig(
                                    sessions=(session,),
                                    instrument=ES,
                                    strategy="continuation",
                                    use_bar_magnifier=True,
                                    risk_usd=5000.0,
                                    direction_filter="short",
                                    rr=rr,
                                    tp1_ratio=tp1,
                                    atr_length=atr_len,
                                    name="",
                                )
                                name = _name(
                                    "es_ny_short",
                                    orb=orb_end,
                                    end=entry_end,
                                    stop=stop_atr,
                                    gap=gap,
                                    rr=rr,
                                    tp1=tp1,
                                    atr=atr_len,
                                )
                                specs.append(
                                    CandidateSpec(
                                        label=make_label(
                                            family="es_ny_orb_dual_book",
                                            session="NY",
                                            direction_mode="short",
                                            candidate_name=name,
                                        ),
                                        config=clone_with_name(
                                            config,
                                            name=name,
                                            notes="Asymmetric ES NY short sibling for dual-book testing.",
                                        ),
                                        companion_leg="es_ny_orb_long",
                                        notes="Independent ES NY short sibling paired with the frozen long leg.",
                                    )
                                )
    return specs


def build_nq_ny_cont_short_specs() -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    rr_tp1_pairs = ((2.0, 0.5), (2.5, 0.4), (2.5, 0.5), (3.0, 0.4))
    for orb_end in ("09:50", "09:55", "10:00"):
        for entry_end in ("10:30", "11:00", "11:30"):
            for stop_orb in (15.0, 17.0, 20.0):
                for gap_orb in (2.5, 5.0):
                    for rr, tp1 in rr_tp1_pairs:
                        for atr_len in (10, 12):
                                session = SessionConfig(
                                    name="NY",
                                    orb_start="09:30",
                                    orb_end=orb_end,
                                    entry_start=orb_end,
                                    entry_end=entry_end,
                                    flat_start=entry_end,
                                    flat_end="16:00",
                                    stop_orb_pct=stop_orb,
                                    min_gap_orb_pct=gap_orb,
                                    min_stop_points=10.0,
                                    min_tp1_points=10.0,
                                )
                                config = StrategyConfig(
                                    sessions=(session,),
                                    instrument=NQ,
                                    strategy="continuation",
                                    use_bar_magnifier=True,
                                    risk_usd=5000.0,
                                    direction_filter="short",
                                    rr=rr,
                                    tp1_ratio=tp1,
                                    atr_length=atr_len,
                                    name="",
                                )
                                name = _name(
                                    "nq_ny_short",
                                    orb=orb_end,
                                    end=entry_end,
                                    stop=stop_orb,
                                    gap=gap_orb,
                                    rr=rr,
                                    tp1=tp1,
                                    atr=atr_len,
                                )
                                specs.append(
                                    CandidateSpec(
                                        label=make_label(
                                            family="nq_ny_cont_short",
                                            session="NY",
                                            direction_mode="short",
                                            candidate_name=name,
                                        ),
                                        config=clone_with_name(
                                            config,
                                            name=name,
                                            notes="NQ NY continuation short challenger around the validated short-v2 anchor.",
                                        ),
                                        notes="Generalist NQ NY continuation short challenger.",
                                    )
                                )
    return specs


def build_nq_ny_lsi_downside_specs() -> list[CandidateSpec]:
    baseline = build_alpha_v1_legs()["nq_ny_lsi_long"].config
    specs: list[CandidateSpec] = []

    gate_variants = [
        ("skip_bear_mh", (), ("bear_medium_vol", "bear_high_vol")),
        ("skip_bear_h", (), ("bear_high_vol",)),
        ("only_bear_mh", ("bear_medium_vol", "bear_high_vol"), ()),
    ]

    for gate_name, include, exclude in gate_variants[:2]:
        name = _name("nq_ny_lsi_long_gate", gate=gate_name, rr=baseline.rr, tp1=baseline.tp1_ratio)
        specs.append(
            CandidateSpec(
                label=make_label(
                    family="nq_ny_lsi_downside",
                    session="NY",
                    direction_mode="long",
                    candidate_name=name,
                ),
                config=clone_with_name(
                    baseline,
                    name=name,
                    notes="Baseline NQ NY LSI long with downside-context turn-off gate.",
                ),
                include_regimes=tuple(include),
                exclude_regimes=tuple(exclude),
                notes="Turn-long-off comparator under downside context.",
            )
        )

    research_long = replace(
        baseline,
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=14,
        excluded_days=(3,),
    )
    name = _name("nq_ny_lsi_rr2_gate", gate="skip_bear_mh", rr=2.0, tp1=0.5)
    specs.append(
        CandidateSpec(
            label=make_label(
                family="nq_ny_lsi_downside",
                session="NY",
                direction_mode="long",
                candidate_name=name,
            ),
            config=clone_with_name(
                research_long,
                name=name,
                notes="RR2/TP0.5 long variant with downside-context gate.",
            ),
            exclude_regimes=("bear_medium_vol", "bear_high_vol"),
            notes="Research long variant gated off in downside contexts.",
        )
    )

    rr_tp1_pairs = ((2.0, 0.5), (2.5, 0.5), (3.0, 0.4))
    for entry_mode in ("close", "fvg_limit"):
        for rr, tp1_ratio in rr_tp1_pairs:
            for atr_len in (10, 14):
                for gap in (3.75, 5.0):
                    for gate_name, include, exclude in gate_variants:
                        config = replace(
                            baseline,
                            direction_filter="short",
                            rr=rr,
                            tp1_ratio=tp1_ratio,
                            atr_length=atr_len,
                            lsi_entry_mode=entry_mode,
                            sessions=(
                                replace(
                                    baseline.sessions[0],
                                    min_gap_atr_pct=gap,
                                ),
                            ),
                            excluded_days=(),
                        )
                        name = _name(
                            "nq_ny_lsi_short",
                            mode=entry_mode,
                            rr=rr,
                            tp1=tp1_ratio,
                            atr=atr_len,
                            gap=gap,
                            gate=gate_name,
                        )
                        specs.append(
                            CandidateSpec(
                                label=make_label(
                                    family="nq_ny_lsi_downside",
                                    session="NY",
                                    direction_mode="short",
                                    candidate_name=name,
                                ),
                                config=clone_with_name(
                                    config,
                                    name=name,
                                    notes="NQ NY LSI downside companion candidate.",
                                ),
                                include_regimes=tuple(include),
                                exclude_regimes=tuple(exclude),
                                notes="Downside-context LSI candidate; not a plain mirror of the live long.",
                            )
                        )
    return specs


def build_nq_asia_downside_quick_specs() -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    rr_tp1_pairs = ((2.0, 0.5), (3.0, 0.4), (3.0, 0.6))
    for direction in ("short", "both"):
        for orb_end in ("20:10", "20:15"):
            for stop_orb in (75.0, 100.0):
                for gap_orb in (5.0, 10.0):
                    for rr, tp1 in rr_tp1_pairs:
                        for atr_len in (5, 14):
                                session = SessionConfig(
                                    name="Asia",
                                    orb_start="20:00",
                                    orb_end=orb_end,
                                    entry_start=orb_end,
                                    entry_end="22:30",
                                    flat_start="04:00",
                                    flat_end="07:00",
                                    stop_orb_pct=stop_orb,
                                    min_gap_orb_pct=gap_orb,
                                )
                                config = StrategyConfig(
                                    sessions=(session,),
                                    instrument=NQ,
                                    strategy="continuation",
                                    use_bar_magnifier=True,
                                    risk_usd=5000.0,
                                    direction_filter=direction,
                                    rr=rr,
                                    tp1_ratio=tp1,
                                    atr_length=atr_len,
                                    name="",
                                )
                                name = _name(
                                    "nq_asia_quick",
                                    dir=direction,
                                    orb=orb_end,
                                    stop=stop_orb,
                                    gap=gap_orb,
                                    rr=rr,
                                    tp1=tp1,
                                    atr=atr_len,
                                )
                                specs.append(
                                    CandidateSpec(
                                        label=make_label(
                                            family="nq_asia_downside_quick",
                                            session="Asia",
                                            direction_mode=direction,
                                            candidate_name=name,
                                        ),
                                        config=clone_with_name(
                                            config,
                                            name=name,
                                            notes="Quick-screen NQ Asia downside candidate.",
                                        ),
                                        quick_screen=True,
                                        notes="Fast structural reject-or-escalate screen.",
                                    )
                                )
    return specs


def build_es_asia_downside_quick_specs() -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    rr_tp1_pairs = ((2.0, 0.5), (3.0, 0.4), (3.0, 0.6))
    for direction in ("short", "both"):
        for orb_end in ("20:15", "20:30"):
            for stop_atr in (10.0, 12.0):
                for gap in (0.5, 1.0):
                    for rr, tp1 in rr_tp1_pairs:
                        session = SessionConfig(
                            name="Asia",
                            orb_start="20:00",
                            orb_end=orb_end,
                            entry_start=orb_end,
                            entry_end="23:15",
                            flat_start="04:00",
                            flat_end="07:00",
                            stop_atr_pct=stop_atr,
                            min_gap_atr_pct=gap,
                            min_stop_points=3.0,
                            min_tp1_points=3.0,
                        )
                        config = StrategyConfig(
                            sessions=(session,),
                            instrument=ES,
                            strategy="continuation",
                            use_bar_magnifier=True,
                            risk_usd=5000.0,
                            direction_filter=direction,
                            rr=rr,
                            tp1_ratio=tp1,
                            atr_length=14,
                            name="",
                        )
                        name = _name(
                            "es_asia_quick",
                            dir=direction,
                            orb=orb_end,
                            stop=stop_atr,
                            gap=gap,
                            rr=rr,
                            tp1=tp1,
                        )
                        specs.append(
                            CandidateSpec(
                                label=make_label(
                                    family="es_asia_downside_quick",
                                    session="Asia",
                                    direction_mode=direction,
                                    candidate_name=name,
                                ),
                                config=clone_with_name(
                                    config,
                                    name=name,
                                    notes="Quick-screen ES Asia downside candidate.",
                                ),
                                quick_screen=True,
                                notes="Fast structural reject-or-escalate screen.",
                            )
                        )
    return specs


FAMILY_BUILDERS = {
    "es_ny_orb_dual_book": build_es_ny_orb_dual_book_specs,
    "nq_ny_cont_short": build_nq_ny_cont_short_specs,
    "nq_ny_lsi_downside": build_nq_ny_lsi_downside_specs,
    "nq_asia_downside_quick": build_nq_asia_downside_quick_specs,
    "es_asia_downside_quick": build_es_asia_downside_quick_specs,
}


def apply_spec_filters(
    specs: list[CandidateSpec],
    raw_results: dict[str, list],
    equity_regime_calendar: pd.DataFrame,
) -> dict[str, list]:
    filtered: dict[str, list] = {}
    for spec in specs:
        trades = raw_results[spec.config.name]
        trades = filter_trades_by_combined_regime(
            trades,
            equity_regime_calendar,
            include=set(spec.include_regimes),
            exclude=set(spec.exclude_regimes),
            include_low_confidence=spec.include_low_confidence,
        )
        filtered[spec.config.name] = trades
    return filtered


def ranking_key(row: dict) -> tuple:
    verdict_rank = {"promote": 2, "challenger": 1, "reject": 0}.get(row["verdict"], 0)
    downside = row["rule_a_downside_improvement_pct"]
    rolling = row["rule_b_rolling_3m_improvement_pct"]
    dsr = row["dsr"]
    return (
        verdict_rank,
        float(downside) if downside is not None else float("-inf"),
        float(rolling) if rolling is not None else float("-inf"),
        float(dsr) if dsr is not None else float("-inf"),
    )


def write_summary(
    output_dir: Path,
    rows: list[dict],
    selected_families: list[str],
) -> None:
    top_rows = sorted(rows, key=ranking_key, reverse=True)[:10]
    lines = [
        "# ALPHA_V1 Downside Wave 1",
        "",
        f"- Families run: `{', '.join(selected_families)}`.",
        f"- Candidates evaluated: `{len(rows)}`.",
        "- Priority: `Generalist First`.",
        "- Portfolio baseline: frozen `ALPHA_V1` separate-account long-only book.",
        "",
        "## Top Candidates",
        "",
    ]
    for row in top_rows:
        lines.append(
            f"- `{row['candidate_name']}` | family `{row['family']}` | verdict `{row['verdict']}` | "
            f"PSR `{row['psr']}` | DSR `{row['dsr']}` | downside lift `{row['rule_a_downside_improvement_pct']}`."
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", default=",".join(FAMILY_ORDER))
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT / "wave1"))
    args = parser.parse_args()

    selected_families = [name.strip() for name in args.families.split(",") if name.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("ALPHA_V1 Downside Wave 1")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    cache = DataCache(start_date=args.start, end_date=args.end)
    baseline_streams = baseline_trade_streams(cache)
    equity_regime_calendar = cache.get(NQ).regime_calendar
    thresholds = PromotionThresholds()
    baseline_legs = build_alpha_v1_legs()

    all_rows: list[dict] = []
    for family in FAMILY_ORDER:
        if family not in selected_families:
            continue

        specs = FAMILY_BUILDERS[family]()
        if args.max_candidates > 0:
            specs = specs[: args.max_candidates]

        family_dir = output_dir / family
        family_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{family}] {len(specs)} candidates")

        raw_results = run_candidate_family(
            cache,
            specs,
            n_workers=max(1, args.workers),
            start_date=args.start,
            end_date=args.end,
        )
        filtered_results = apply_spec_filters(specs, raw_results, equity_regime_calendar)
        trade_date_sets = [
            {trade.date for trade in filled_trades(filtered_results[spec.config.name])}
            for spec in specs
        ]

        family_rows: list[dict] = []
        for spec in specs:
            companion_trades = None
            if spec.companion_leg is not None:
                companion_trades = baseline_streams[spec.companion_leg]

            packet = research_packet(
                spec=spec,
                trades=filtered_results[spec.config.name],
                family_trade_sets=trade_date_sets,
                n_trials_raw=len(specs),
                baseline_streams=baseline_streams,
                holdout_start=args.holdout_start,
                thresholds=thresholds,
                companion_trades=companion_trades,
                regime_calendar=equity_regime_calendar,
            )
            row = packet_summary_row(packet)
            row["quick_screen"] = spec.quick_screen
            row["companion_leg"] = spec.companion_leg
            family_rows.append(row)
            all_rows.append(row)

            packet_path = family_dir / f"{spec.config.name}.json"
            packet_path.write_text(json.dumps(packet, indent=2))

        family_df = pd.DataFrame(sorted(family_rows, key=ranking_key, reverse=True))
        family_df.to_csv(family_dir / "ranking.csv", index=False)
        print(family_df.head(5).to_string(index=False))

    ranking_df = pd.DataFrame(sorted(all_rows, key=ranking_key, reverse=True))
    ranking_df.to_csv(output_dir / "wave1_ranking.csv", index=False)
    write_summary(output_dir, all_rows, selected_families)

    baseline_manifest = {
        key: {
            "family": leg.family,
            "session": leg.session,
            "candidate_name": leg.config.name,
        }
        for key, leg in baseline_legs.items()
    }
    (output_dir / "baseline_manifest.json").write_text(json.dumps(baseline_manifest, indent=2))

    print("\nSaved:")
    print(f"  {output_dir / 'wave1_ranking.csv'}")
    print(f"  {output_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
