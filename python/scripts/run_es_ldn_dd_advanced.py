#!/usr/bin/env python3
"""ES London ORB Continuation — advanced DD reduction tests.

Tests 5 untested approaches on WF mode params:
  rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0, both directions

1. Economic event date exclusion (FOMC, NFP, CPI)
2. Exit type analysis — are EOD exits the DD driver?
3. Earlier flat/exit time sweep
4. Post-ORB cooling period
5. CISD strategy on ES LDN
"""

import sys, time
from collections import defaultdict
from dataclasses import replace as dc_replace
sys.path.insert(0, "src")

import numpy as np

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_SL, EXIT_EOD, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_TP1_TP2
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

# ── Economic event dates ────────────────────────────────────────────────
FOMC_DATES = (
    "20160127","20160316","20160427","20160615","20160727","20160921","20161102","20161214",
    "20170201","20170315","20170503","20170614","20170726","20170920","20171101","20171213",
    "20180131","20180321","20180502","20180613","20180801","20180926","20181108","20181219",
    "20190130","20190320","20190501","20190619","20190731","20190918","20191030","20191211",
    "20200129","20200318","20200429","20200610","20200729","20200916","20201105","20201216",
    "20210127","20210317","20210428","20210616","20210728","20210922","20211103","20211215",
    "20220126","20220316","20220504","20220615","20220727","20220921","20221102","20221214",
    "20230201","20230322","20230503","20230614","20230726","20230920","20231101","20231213",
    "20240131","20240320","20240501","20240612","20240731","20240918","20241107","20241218",
    "20250129","20250319","20250507","20250618","20250730","20250917","20251029","20251210",
    "20260128",
)

NFP_DATES = (
    "20160108","20160205","20160304","20160401","20160506","20160603","20160708","20160805","20160902","20161007","20161104","20161202",
    "20170106","20170203","20170310","20170407","20170505","20170602","20170707","20170804","20170901","20171006","20171103","20171208",
    "20180105","20180202","20180309","20180406","20180504","20180601","20180706","20180803","20180907","20181005","20181102","20181207",
    "20190104","20190201","20190308","20190405","20190503","20190607","20190705","20190802","20190906","20191004","20191101","20191206",
    "20200110","20200207","20200306","20200403","20200508","20200605","20200702","20200807","20200904","20201002","20201106","20201204",
    "20210108","20210205","20210305","20210402","20210507","20210604","20210702","20210806","20210903","20211008","20211105","20211203",
    "20220107","20220204","20220304","20220401","20220506","20220603","20220708","20220805","20220902","20221007","20221104","20221202",
    "20230106","20230203","20230310","20230407","20230505","20230602","20230707","20230804","20230901","20231006","20231103","20231208",
    "20240105","20240202","20240308","20240405","20240503","20240607","20240705","20240802","20240906","20241004","20241101","20241206",
    "20250110","20250207","20250307","20250404","20250502","20250606","20250703","20250801","20250905","20251120","20251216",
    "20260109","20260211",
)

CPI_DATES = (
    "20160120","20160219","20160316","20160414","20160517","20160616","20160715","20160816","20160916","20161018","20161117","20161215",
    "20170118","20170215","20170315","20170414","20170512","20170614","20170714","20170811","20170914","20171013","20171115","20171213",
    "20180112","20180214","20180313","20180411","20180510","20180612","20180712","20180810","20180913","20181011","20181114","20181212",
    "20190111","20190213","20190312","20190410","20190510","20190612","20190711","20190813","20190912","20191010","20191113","20191211",
    "20200114","20200213","20200311","20200410","20200512","20200610","20200714","20200812","20200911","20201013","20201112","20201210",
    "20210113","20210210","20210310","20210413","20210512","20210610","20210713","20210811","20210914","20211013","20211110","20211210",
    "20220112","20220210","20220310","20220412","20220511","20220610","20220713","20220810","20220913","20221013","20221110","20221213",
    "20230112","20230214","20230314","20230412","20230510","20230613","20230712","20230810","20230913","20231012","20231114","20231212",
    "20240111","20240213","20240312","20240410","20240515","20240612","20240711","20240814","20240911","20241010","20241113","20241211",
    "20250115","20250212","20250312","20250410","20250513","20250611","20250715","20250812","20250910","20251024","20251218",
    "20260113","20260213",
)

ALL_EVENT_DATES = tuple(sorted(set(FOMC_DATES + NFP_DATES + CPI_DATES)))


def get_metrics(trades):
    m = compute_metrics(trades)
    return {
        "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
        "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
        "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
        "exit_breakdown": m["exit_breakdown"],
    }


def worst_month_r(trades):
    monthly = defaultdict(float)
    for t in trades:
        if t.exit_type != EXIT_NO_FILL:
            monthly[t.date[:7]] += t.r_multiple
    return min(monthly.values()) if monthly else 0.0


def show(label, m, wm, extra=""):
    print(f"  {label:<40} {m['trades']:>5}t  {m['wr']:>5.1%} WR  PF {m['pf']:.2f}  "
          f"Sharpe {m['sharpe']:.2f}  Net R {m['total_r']:>+7.1f}  DD {m['max_dd']:.1f}R  "
          f"worst mo {wm:.1f}R{extra}")


def main():
    print("ES LDN — Advanced DD Reduction Tests")
    print("=" * 70)

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s")

    base_config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        rr=3.0,
        tp1_ratio=0.5,
    )
    base_config = with_overrides(base_config, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)

    print("Running base backtest...", flush=True)
    t0 = time.time()
    base_trades = run_backtest(df_5m, base_config, start_date=START_DATE, df_1m=df_1m)
    base_m = get_metrics(base_trades)
    base_wm = worst_month_r(base_trades)
    print(f"Done in {time.time() - t0:.1f}s\n")

    # ════════════════════════════════════════════════════════════════════
    # TEST 1: ECONOMIC EVENT DATE EXCLUSION
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 100)
    print("  TEST 1: ECONOMIC EVENT DATE EXCLUSION")
    print("=" * 100)

    # First, analyze event-day vs non-event-day performance
    filled = [t for t in base_trades if t.exit_type != EXIT_NO_FILL]
    event_set = set()
    for d in ALL_EVENT_DATES:
        event_set.add(f"{d[:4]}-{d[4:6]}-{d[6:]}")

    event_trades = [t for t in filled if t.date in event_set]
    non_event_trades = [t for t in filled if t.date not in event_set]

    event_r = [t.r_multiple for t in event_trades]
    non_event_r = [t.r_multiple for t in non_event_trades]

    print(f"\n  Event day stats ({len(event_trades)} trades):")
    if event_r:
        print(f"    WR: {np.mean(np.array(event_r)>0):.1%}  Avg R: {np.mean(event_r):.3f}  "
              f"Net R: {sum(event_r):.1f}  Sum neg: {sum(r for r in event_r if r<0):.1f}")
    print(f"  Non-event day stats ({len(non_event_trades)} trades):")
    if non_event_r:
        print(f"    WR: {np.mean(np.array(non_event_r)>0):.1%}  Avg R: {np.mean(non_event_r):.3f}  "
              f"Net R: {sum(non_event_r):.1f}  Sum neg: {sum(r for r in non_event_r if r<0):.1f}")

    # Test exclusion configs
    event_configs = [
        ("Baseline", ()),
        ("Excl FOMC only", FOMC_DATES),
        ("Excl NFP only", NFP_DATES),
        ("Excl CPI only", CPI_DATES),
        ("Excl FOMC+NFP", tuple(sorted(set(FOMC_DATES + NFP_DATES)))),
        ("Excl FOMC+NFP+CPI", ALL_EVENT_DATES),
    ]

    print(f"\n  {'Label':<40} {'Trades':>5}  {'WR':>5}     {'PF':>5}  {'Sharpe':>6}  "
          f"{'Net R':>7}  {'MaxDD':>6}  {'Worst Mo':>8}")
    print("  " + "-" * 95)

    for label, excl_dates in event_configs:
        cfg = dc_replace(base_config, excluded_dates=excl_dates)
        t_list = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m)
        m = get_metrics(t_list)
        wm = worst_month_r(t_list)
        show(label, m, wm)

    # ════════════════════════════════════════════════════════════════════
    # TEST 2: EXIT TYPE ANALYSIS
    # ════════════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 100)
    print("  TEST 2: EXIT TYPE ANALYSIS — which exits drive DD?")
    print("=" * 100)

    exit_groups = defaultdict(list)
    for t in filled:
        exit_groups[t.exit_type].append(t.r_multiple)

    EXIT_NAMES_MAP = {1: "SL", 2: "TP1_TP2", 3: "TP1_BE", 4: "TP1_EOD", 5: "EOD"}

    print(f"\n  {'Exit Type':<12} {'Count':>6} {'WR':>6} {'Avg R':>7} {'Net R':>8} {'Sum Neg':>8} {'Pct of Loss':>11}")
    print("  " + "-" * 65)
    total_neg = sum(r for rs in exit_groups.values() for r in rs if r < 0)
    for etype in sorted(exit_groups.keys()):
        rs = np.array(exit_groups[etype])
        neg_sum = sum(r for r in rs if r < 0)
        pct_loss = neg_sum / total_neg * 100 if total_neg != 0 else 0
        wr = float(np.mean(rs > 0))
        print(f"  {EXIT_NAMES_MAP.get(etype, str(etype)):<12} {len(rs):>6} {wr:>5.1%} {float(rs.mean()):>7.3f} "
              f"{float(rs.sum()):>+7.1f}R {neg_sum:>+7.1f}R {pct_loss:>10.1f}%")

    # Post-hoc: what if we removed EOD exits?
    no_eod = [t for t in base_trades if t.exit_type != EXIT_EOD or t.exit_type == EXIT_NO_FILL]
    m_no_eod = get_metrics(no_eod)
    wm_no_eod = worst_month_r(no_eod)
    print(f"\n  Remove EXIT_EOD trades:")
    show("  Without EOD exits", m_no_eod, wm_no_eod)
    show("  Baseline", base_m, base_wm)

    # ════════════════════════════════════════════════════════════════════
    # TEST 3: EARLIER FLAT/EXIT TIME
    # ════════════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 100)
    print("  TEST 3: EARLIER FLAT/EXIT TIME SWEEP")
    print("  Current: flat_start=08:20, flat_end=08:25")
    print("=" * 100)

    flat_times = [
        ("08:20 (baseline)", "08:20", "08:25"),
        ("07:30", "07:30", "07:35"),
        ("07:00", "07:00", "07:05"),
        ("06:30", "06:30", "06:35"),
        ("06:00", "06:00", "06:05"),
        ("05:30", "05:30", "05:35"),
    ]

    print(f"\n  {'Flat Time':<20} {'Trades':>5}  {'WR':>5}     {'PF':>5}  {'Sharpe':>6}  "
          f"{'Net R':>7}  {'MaxDD':>6}  {'Worst Mo':>8}")
    print("  " + "-" * 85)

    ldn_overridden = base_config.sessions[0]  # has stop=1.5%, gap=1.25%
    for label, flat_s, flat_e in flat_times:
        ldn = dc_replace(ldn_overridden, flat_start=flat_s, flat_end=flat_e)
        # Also cap entry_end to flat_start if it's earlier
        if flat_s < ldn_overridden.entry_end:
            ldn = dc_replace(ldn, entry_end=flat_s)
        cfg = dc_replace(base_config, sessions=(ldn,))
        t_list = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m)
        m = get_metrics(t_list)
        wm = worst_month_r(t_list)
        show(label, m, wm)

    # ════════════════════════════════════════════════════════════════════
    # TEST 4: POST-ORB COOLING PERIOD
    # ════════════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 100)
    print("  TEST 4: POST-ORB COOLING PERIOD")
    print("  Keep 15m ORB (03:00-03:15), delay entry_start")
    print("=" * 100)

    cool_times = [
        ("03:15 (baseline)", "03:15"),
        ("03:30 (+15m cool)", "03:30"),
        ("03:45 (+30m cool)", "03:45"),
        ("04:00 (+45m cool)", "04:00"),
        ("04:30 (+75m cool)", "04:30"),
    ]

    print(f"\n  {'Entry Start':<25} {'Trades':>5}  {'WR':>5}     {'PF':>5}  {'Sharpe':>6}  "
          f"{'Net R':>7}  {'MaxDD':>6}  {'Worst Mo':>8}")
    print("  " + "-" * 85)

    for label, entry_s in cool_times:
        ldn = dc_replace(ldn_overridden, entry_start=entry_s)
        cfg = dc_replace(base_config, sessions=(ldn,))
        t_list = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m)
        m = get_metrics(t_list)
        wm = worst_month_r(t_list)
        show(label, m, wm)

    # ════════════════════════════════════════════════════════════════════
    # TEST 5: CISD STRATEGY ON ES LDN
    # ════════════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 100)
    print("  TEST 5: CISD STRATEGY ON ES LDN")
    print("  ORB sweep + displacement candle, market entry")
    print("=" * 100)

    cisd_rrs = [1.5, 2.0, 2.5, 3.0]
    cisd_tp1s = [0.3, 0.5]

    print(f"\n  {'Config':<25} {'Trades':>5}  {'WR':>5}     {'PF':>5}  {'Sharpe':>6}  "
          f"{'Net R':>7}  {'MaxDD':>6}  {'Worst Mo':>8}")
    print("  " + "-" * 85)

    # First show continuation baseline for comparison
    show("Continuation baseline", base_m, base_wm)

    for rr in cisd_rrs:
        for tp1 in cisd_tp1s:
            cisd_cfg = StrategyConfig(
                sessions=(LDN_SESSION,),
                instrument=ES,
                strategy="cisd",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                rr=rr,
                tp1_ratio=tp1,
            )
            cisd_cfg = with_overrides(cisd_cfg, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)
            t_list = run_backtest(df_5m, cisd_cfg, start_date=START_DATE, df_1m=df_1m)
            m = get_metrics(t_list)
            if m["trades"] < 20:
                print(f"  rr={rr} tp1={tp1:<23} {m['trades']:>5}t  (too few)")
                continue
            wm = worst_month_r(t_list)
            show(f"CISD rr={rr} tp1={tp1}", m, wm)

    print(f"\n{'='*70}")
    print(f"  ALL TESTS COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
