# YM (Dow Jones Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $5/point
- **Min tick**: 1.0
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m)
- **Liquidity**: NY session tested. Continuation model (front-month continuous via Databento `YM.c.0`).

## Strategies Tested

### 1. Continuation NY both directions
- **Status**: NO-GO
- **Date tested**: 2026-02-17
- **Pipeline results**:

| Phase | Result | Detail |
|-------|--------|--------|
| 1. Structural | PASS | 1906 trades, 45.8% WR, PF 1.03, Sharpe 0.25 |
| 2. Walk-Forward | FAIL | WF efficiency -1.52, stability 0.92 (vacuously high) |
| 3. Prop Filter | FAIL | DD -47.8R, worst month -10.7R, expectancy -0.020R |
| 4. Hold-Out | PASS | 218 trades, Sharpe 2.00, PF 1.32, +32.3R |
| 5. Monte Carlo | FAIL | 0% survival at 10R DD |

### 2. Continuation NY short-only
- **Status**: NO-GO
- **Date tested**: 2026-02-17
- **Rationale**: Short side showed Sharpe 0.76 vs long's 0.09 in structural check
- **Pipeline results**:

| Phase | Result | Detail |
|-------|--------|--------|
| 1. Structural | PASS | 989 trades, 47.4% WR, PF 1.11, Sharpe 0.76 |
| 2. Walk-Forward | FAIL | WF efficiency 0.26, stability 0.88 (high) |
| 3. Prop Filter | FAIL | DD -19.0R, worst month -7.0R, 2019: -11.1R |
| 4. Hold-Out | PASS | 115 trades, Sharpe 1.21, PF 1.18, +8.1R |
| 5. Monte Carlo | FAIL | 0.4% survival, 99.6% ruin |

- **Mode params**: rr=2.0, ny_stop_atr_pct=7.5, ny_min_gap_atr_pct=2.25, tp1_ratio=0.4
- **Note**: Best of the NY variants. Real stability (0.88) but WF efficiency only 0.26. Fold 1 (2019 OOS) was devastating (-2.05 OOS Sharpe). Fold 6 showed promise (1.39 OOS Sharpe with rr=2.0, stop=5.0, gap=1.0, tp1=0.4).

### 3. Continuation Asia long-only
- **Status**: NO-GO
- **Date tested**: 2026-02-17
- **Rationale**: Best Sharpe (0.84) and PF (1.12) of all structural screens
- **Pipeline results**:

| Phase | Result | Detail |
|-------|--------|--------|
| 1. Structural | FAIL | 1202 trades, 46.9% WR, PF 1.12, max consec losses=16 (>15) |
| 2. Walk-Forward | FAIL | WF efficiency 0.11, stability 0.79 (high) |
| 3. Prop Filter | FAIL | DD -13.8R, worst month -7.3R, 2023: -4.4R, 2024: -5.8R |
| 4. Hold-Out | PASS | 58 trades, Sharpe 1.18, PF 1.17, +5.3R |
| 5. Monte Carlo | FAIL | 3.2% survival, 96.8% ruin |

- **Mode params**: rr=2.5, asia_stop_atr_pct=5.25, asia_min_gap_atr_pct=2.5, tp1_ratio=0.5
- **Note**: Promising structural metrics but fails Phase 1 on consecutive losses. WF showed regime dependency — strong 2019-2022, weak 2023-2024. Combined OOS was positive (30.6R, PF 1.13, Sharpe 0.91) but DD -13.8R too deep for prop.

### 4. Reversal (all sessions, all directions)
- **Status**: NO-GO
- **Date tested**: 2026-02-17
- **Result**: Catastrophic across all 12 combinations (NY/Asia/LDN x both/long/short). PF range 0.23-0.53. Worst: NY both -1253.8R. YM does NOT mean-revert through FVGs.

### 5. Inversion (all sessions, all directions)
- **Status**: NO-GO
- **Date tested**: 2026-02-17
- **Result**: Negative across all 12 combinations. PF range 0.34-0.89. Best was LDN both (PF 0.87, Sharpe -1.02) — still a consistent loser. Unlike GC where inversion long was a GO, YM inversion does not work.

## Comprehensive Screening Results (Phase 1 structural, 2016-2026)

| Strategy | Session | Direction | Trades | WR | PF | Sharpe | Total R | Max DD |
|----------|---------|-----------|--------|-----|------|--------|---------|--------|
| continuation | NY | both | 1906 | 45.8% | 1.03 | 0.25 | +34.6R | -68.4R |
| continuation | NY | long | 1068 | 45.4% | 1.01 | 0.09 | +7.1R | -56.6R |
| **continuation** | **NY** | **short** | **989** | **47.4%** | **1.11** | **0.76** | **+54.4R** | **-31.2R** |
| continuation | Asia | both | 2057 | 45.6% | 1.03 | 0.26 | +39.0R | -55.9R |
| **continuation** | **Asia** | **long** | **1202** | **46.9%** | **1.12** | **0.84** | **+74.8R** | **-22.5R** |
| continuation | Asia | short | 1073 | 44.0% | 0.94 | -0.44 | -34.0R | -78.1R |
| continuation | LDN | both | 2407 | 46.4% | 1.01 | 0.12 | +19.4R | -46.7R |
| continuation | LDN | long | 1498 | 46.8% | 1.02 | 0.17 | +16.4R | -34.0R |
| continuation | LDN | short | 1382 | 45.6% | 1.00 | -0.01 | -1.1R | -40.8R |
| reversal | all | all | - | 16-32% | 0.23-0.53 | -4.7 to -12.3 | catastrophic | - |
| inversion | all | all | - | 21-43% | 0.34-0.89 | -0.8 to -8.6 | negative | - |

## Key Insights

1. **YM is not viable for the ORB+FVG strategy** in any form tested. Every combination of strategy (continuation/reversal/inversion), session (NY/Asia/LDN), and direction (both/long/short) produces NO-GO results.

2. **The short side of NY continuation is the "least bad"** variant (Sharpe 0.76, PF 1.11) but still fails walk-forward and MC with -19R drawdown on WF OOS trades.

3. **Asia long-only has the best raw metrics** (Sharpe 0.84, PF 1.12) but is regime-dependent — strong 2017-2022, degrading 2023-2024. Failed Phase 1 on consecutive losses.

4. **Reversal is catastrophically bad** on YM — opposite of what the continuation strategy does is terrible. This confirms YM does trend through FVGs (continuation direction is correct), but the edge is too thin.

5. **Inversion doesn't transfer from GC to YM** — the FVG invalidation pattern that works beautifully on gold does not work on the Dow.

6. **All hold-out periods (2025) look good** but this is misleading — it's a single favorable regime. WF and MC consistently show the strategy can't survive realistic path variance.

7. **The fundamental problem**: YM's ATR-scaled risk with default params leads to drawdowns 2-7x the prop firm limit. No param combination within reasonable ranges can solve this.

## Recommendation

Do not pursue the ORB+FVG strategy on YM for prop firm trading. The instrument may be better suited to:
- Different entry logic entirely (e.g., range breakout without FVG requirement)
- Much wider ORB windows (30+ min)
- Different timeframes (15m or 1h bars)
- Trend-following overlays rather than intraday mean-reversion setups
