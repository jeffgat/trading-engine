#!/usr/bin/env python3
"""Second-round cross-asset regime-gate follow-up on the promoted shortlist.

This round answers three questions for the survivors from round one:
1. Is the damage coming from `bull_medium_vol`, `sideways_medium_vol`, or both?
2. Does a lighter partial gate beat the full NQ-style gate?
3. Which holdout variant should each candidate carry forward?
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from orb_backtest.analysis.regime_research import _filled_trades
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest

import run_cross_asset_regime_gate_research as round1

OUTPUT_DIR = round1.ROOT / "data" / "results" / "cross_asset_regime_gate_round2"
SHORTLIST_IDS = {
    "nq_asia_2",
    "gc_asia_1",
    "rty_ny_2",
    "rty_ny_4",
    "si_asia_1",
    "si_asia_3",
}


@dataclass(frozen=True)
class GateVariant:
    key: str
    label: str
    blocked_buckets: frozenset[str]


GATE_VARIANTS = (
    GateVariant("ungated", "Ungated", frozenset()),
    GateVariant(
        "block_bull_medium_vol",
        "Block bull_medium_vol",
        frozenset({"bull_medium_vol"}),
    ),
    GateVariant(
        "block_sideways_medium_vol",
        "Block sideways_medium_vol",
        frozenset({"sideways_medium_vol"}),
    ),
    GateVariant(
        "block_full_medium_vol",
        "Block bull_medium_vol + sideways_medium_vol",
        frozenset({"bull_medium_vol", "sideways_medium_vol"}),
    ),
)


def build_shortlist() -> list[round1.CandidateSpec]:
    return [c for c in round1.build_candidates() if c.candidate_id in SHORTLIST_IDS]


def make_bucket_gate(
    regime_lookup: dict[str, str],
    blocked_buckets: frozenset[str],
):
    def gate(trades: list[TradeResult]) -> list[TradeResult]:
        if not blocked_buckets:
            return list(trades)
        return [
            trade
            for trade in trades
            if trade.exit_type == EXIT_NO_FILL or regime_lookup.get(trade.date) not in blocked_buckets
        ]

    return gate


def bucket_snapshot(trades: list[TradeResult]) -> dict:
    filled = _filled_trades(trades)
    if not filled:
        return {
            "trades": 0,
            "net_r": 0.0,
            "avg_r": 0.0,
            "win_rate": None,
        }
    wins = sum(1 for trade in filled if trade.r_multiple > 0)
    net_r = sum(trade.r_multiple for trade in filled)
    return {
        "trades": len(filled),
        "net_r": round(net_r, 2),
        "avg_r": round(net_r / len(filled), 3),
        "win_rate": round(wins / len(filled), 4),
    }


def holdout_bucket_attribution(
    trades: list[TradeResult],
    regime_lookup: dict[str, str],
) -> dict:
    filled = _filled_trades(trades)
    by_bucket: dict[str, list[TradeResult]] = {
        "bull_medium_vol": [],
        "sideways_medium_vol": [],
        "other_regimes": [],
    }
    for trade in filled:
        bucket = regime_lookup.get(trade.date)
        if bucket == "bull_medium_vol":
            by_bucket["bull_medium_vol"].append(trade)
        elif bucket == "sideways_medium_vol":
            by_bucket["sideways_medium_vol"].append(trade)
        else:
            by_bucket["other_regimes"].append(trade)
    return {name: bucket_snapshot(bucket_trades) for name, bucket_trades in by_bucket.items()}


def delta(lhs: dict, rhs: dict, key: str, digits: int = 3) -> float | None:
    left = lhs.get(key)
    right = rhs.get(key)
    if left is None or right is None:
        return None
    return round(float(lhs[key]) - float(rhs[key]), digits)


def infer_damage_bucket(bucket_attribution: dict) -> str:
    bull_r = float(bucket_attribution["bull_medium_vol"]["net_r"] or 0.0)
    sideways_r = float(bucket_attribution["sideways_medium_vol"]["net_r"] or 0.0)
    if bull_r < 0.0 and sideways_r < 0.0:
        return "both_medium_vol_buckets"
    if bull_r < 0.0:
        return "bull_medium_vol"
    if sideways_r < 0.0:
        return "sideways_medium_vol"
    return "neither_medium_vol_bucket"


def choose_preferred_variant(variants: dict[str, dict]) -> str:
    baseline = variants["ungated"]["holdout"]
    baseline_trades = int(baseline.get("trades") or 0)
    baseline_r = float(baseline.get("net_r") or 0.0)

    eligible: list[tuple[float, float, str]] = []
    for key, payload in variants.items():
        holdout = payload["holdout"]
        trades = int(holdout.get("trades") or 0)
        net_r = float(holdout.get("net_r") or 0.0)
        calmar = float(holdout.get("calmar") or 0.0)
        dd = float(holdout.get("max_drawdown_r") or 0.0)
        payout = float(holdout.get("payout_rate") or 0.0)

        min_trades = max(50, int(round(baseline_trades * 0.50)))
        max_r_drop = max(3.0, baseline_r * 0.15)
        if key == "ungated":
            eligible.append((calmar, net_r, key))
            continue
        if trades < min_trades:
            continue
        if net_r <= 0.0:
            continue
        if net_r < baseline_r - max_r_drop:
            continue
        if calmar < float(baseline.get("calmar") or 0.0) + 0.25:
            continue
        if dd < float(baseline.get("max_drawdown_r") or 0.0) + 1.0:
            continue
        if payout < float(baseline.get("payout_rate") or 0.0) - 0.05:
            continue
        eligible.append((calmar, net_r, key))

    eligible.sort(reverse=True)
    return eligible[0][2] if eligible else "ungated"


def recommendation_label(preferred_variant: str) -> str:
    if preferred_variant == "ungated":
        return "keep_ungated"
    if preferred_variant == "block_full_medium_vol":
        return "promote_full_gate"
    return "promote_partial_gate"


def sort_key(result: dict) -> tuple[float, float]:
    preferred = result["variants"][result["preferred_variant"]]["holdout"]
    calmar = float(preferred.get("calmar") or 0.0)
    net_r = float(preferred.get("net_r") or 0.0)
    return (calmar, net_r)


def build_memo(results: list[dict]) -> str:
    lines = [
        "# Cross-Asset Regime-Gate Round Two Memo",
        "",
        "## Protocol",
        f"- Shared pre-holdout through {round1.PRE_HOLDOUT_END}",
        f"- Shared holdout {round1.HOLDOUT_START} to {round1.HOLDOUT_END}",
        "- Survivors only: NQ Asia-2, GC Asia-1, RTY NY-2/NY-4, SI Asia-1/Asia-3",
        "- Gate variants: ungated, bull-only, sideways-only, full medium-vol gate",
        "",
        "## Preferred Variants",
    ]

    for result in sorted(results, key=sort_key, reverse=True):
        preferred = result["variants"][result["preferred_variant"]]["holdout"]
        damage = result["holdout_bucket_attribution"]
        lines.append(
            f"- {result['asset']} {result['candidate_name']}: {result['preferred_variant']} "
            f"({result['recommendation']}) | holdout {preferred['net_r']}R, Cal {preferred['calmar']}, "
            f"DD {preferred['max_drawdown_r']}R, PR {preferred['payout_rate']}; "
            f"bull_med {damage['bull_medium_vol']['net_r']}R, sideways_med {damage['sideways_medium_vol']['net_r']}R."
        )

    lines.extend(["", "## Promotion Call"])
    promoted = [r for r in results if r["recommendation"] != "keep_ungated"]
    kept_ungated = [r for r in results if r["recommendation"] == "keep_ungated"]

    if promoted:
        for result in sorted(promoted, key=sort_key, reverse=True):
            lines.append(
                f"- Promote {result['asset']} {result['candidate_name']} with `{result['preferred_variant']}`."
            )
    else:
        lines.append("- No candidate beat the ungated baseline strongly enough to promote a gate.")

    if kept_ungated:
        lines.extend(["", "## Keep Ungated"])
        for result in sorted(kept_ungated, key=sort_key, reverse=True):
            lines.append(
                f"- Keep {result['asset']} {result['candidate_name']} ungated; blocked buckets were not damaging enough."
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    print("Cross-Asset Regime-Gate Round Two")
    print("=" * 72)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    shortlist = build_shortlist()
    by_asset: dict[str, list[round1.CandidateSpec]] = {}
    for candidate in shortlist:
        by_asset.setdefault(candidate.asset, []).append(candidate)

    bundles: dict[str, round1.InstrumentBundle] = {}
    for asset, asset_candidates in by_asset.items():
        print(f"\nLoading {asset} data and regime calendar...", flush=True)
        bundles[asset] = round1.bundle_for_asset(asset, asset_candidates)

    all_results: list[dict] = []
    for asset in sorted(by_asset):
        bundle = bundles[asset]
        print(f"\n{'=' * 72}")
        print(f"{asset} Round-Two Candidates")
        print(f"{'=' * 72}")
        for candidate in by_asset[asset]:
            print(f"\nRunning {candidate.asset} {candidate.candidate_name}...", flush=True)
            candidate_t0 = time.time()

            base_pre = run_backtest(
                bundle.df_5m,
                candidate.config,
                end_date=round1.PRE_HOLDOUT_END,
                df_1m=bundle.df_1m,
                df_1s=bundle.df_1s,
            )
            base_pre = round1.apply_post_trade_filters(base_pre, candidate)

            base_holdout = run_backtest(
                bundle.df_5m,
                candidate.config,
                start_date=round1.HOLDOUT_START,
                end_date=round1.HOLDOUT_END,
                df_1m=bundle.df_1m,
                df_1s=bundle.df_1s,
            )
            base_holdout = round1.apply_post_trade_filters(base_holdout, candidate)

            round1.validate_mapping(asset, candidate, base_pre, bundle)
            round1.validate_mapping(asset, candidate, base_holdout, bundle)

            variants: dict[str, dict] = {}
            for variant in GATE_VARIANTS:
                gate_fn = make_bucket_gate(bundle.regime_lookup, variant.blocked_buckets)
                pre_trades = gate_fn(base_pre)
                holdout_trades = gate_fn(base_holdout)
                pre_scorecard = round1.simulate_prop_scorecard(candidate, pre_trades, bundle.pre_dates)
                holdout_scorecard = round1.simulate_prop_scorecard(
                    candidate, holdout_trades, bundle.holdout_dates
                )
                variants[variant.key] = {
                    "label": variant.label,
                    "blocked_buckets": sorted(variant.blocked_buckets),
                    "pre_holdout": round1.metric_snapshot(pre_trades, pre_scorecard),
                    "holdout": round1.metric_snapshot(holdout_trades, holdout_scorecard),
                }

            preferred_variant = choose_preferred_variant(variants)
            preferred_holdout = variants[preferred_variant]["holdout"]
            ungated_holdout = variants["ungated"]["holdout"]
            bucket_attr = holdout_bucket_attribution(base_holdout, bundle.regime_lookup)

            result = {
                "asset": candidate.asset,
                "candidate_id": candidate.candidate_id,
                "candidate_name": candidate.candidate_name,
                "session": candidate.session,
                "direction": candidate.direction,
                "notes": candidate.notes,
                "variants": variants,
                "holdout_bucket_attribution": bucket_attr,
                "damage_bucket_inference": infer_damage_bucket(bucket_attr),
                "preferred_variant": preferred_variant,
                "preferred_label": variants[preferred_variant]["label"],
                "recommendation": recommendation_label(preferred_variant),
                "preferred_vs_ungated_holdout": {
                    "delta_trades": delta(preferred_holdout, ungated_holdout, "trades", digits=0),
                    "delta_net_r": delta(preferred_holdout, ungated_holdout, "net_r", digits=2),
                    "delta_calmar": delta(preferred_holdout, ungated_holdout, "calmar", digits=3),
                    "delta_sharpe": delta(preferred_holdout, ungated_holdout, "sharpe", digits=3),
                    "delta_max_drawdown_r": delta(
                        preferred_holdout, ungated_holdout, "max_drawdown_r", digits=2
                    ),
                    "delta_payout_rate": delta(
                        preferred_holdout, ungated_holdout, "payout_rate", digits=4
                    ),
                },
            }
            all_results.append(result)
            print(
                f"  Preferred: {result['preferred_variant']} | "
                f"Holdout R {preferred_holdout['net_r']:+.2f} | "
                f"Cal {preferred_holdout['calmar'] or 0:.3f} | "
                f"DD {preferred_holdout['max_drawdown_r']:+.2f} | "
                f"{result['recommendation']} [{time.time() - candidate_t0:.1f}s]"
            )

    payload = {
        "protocol": {
            "pre_holdout_end": round1.PRE_HOLDOUT_END,
            "holdout_start": round1.HOLDOUT_START,
            "holdout_end": round1.HOLDOUT_END,
            "gate_variants": [
                {"key": variant.key, "blocked_buckets": sorted(variant.blocked_buckets)}
                for variant in GATE_VARIANTS
            ],
        },
        "shortlist": sorted(SHORTLIST_IDS),
        "results": sorted(all_results, key=sort_key, reverse=True),
    }

    json_path = OUTPUT_DIR / "round2_results.json"
    memo_path = OUTPUT_DIR / "round2_memo.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))
    memo_path.write_text(build_memo(payload["results"]))

    print(f"\nSaved JSON: {json_path}")
    print(f"Saved memo: {memo_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
