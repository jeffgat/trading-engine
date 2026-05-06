# ALPHA_V1 Fee Comparison

- Generated: `2026-05-06T11:24:13`
- Window: `2016-04-17` to `2026-03-24`.
- Old fee: `$0.05` per contract per side.
- New fee midpoint: MNQ/MES `$0.575` per contract per side.
- Fees are accounting-only in both engines, so fills and exits do not change between old-fee and new-fee valuation.
- Research rows use the ALPHA_V1 research configs but revalue them on the live micro contracts for fee realism.
- Exact rows use isolated live-engine profiles for each ALPHA leg. NQ R11 uses the documented `09:30-09:50` ORB override because `ALPHA_V1-A` is not yet a freshly exported five-leg profile.
- This report was regenerated from cached completed rows after the full replay finished.

## Research Engine

| Leg | Contract | Trades | Old fee net R | New fee net R | Delta R | Old comm | New comm |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HTF_LSI/NQ_NY-L24 | MNQ | 484 | 90.47 | 81.03 | -9.43 | $4469.60 | $51400.40 |
| ORB/NQ_ASIA-RR6 | MNQ | 723 | 207.58 | 155.28 | -52.30 | $24873.00 | $286039.50 |
| ORB/ES_ASIA-RR1.5 | MES | 1422 | 139.06 | 68.89 | -70.17 | $33362.90 | $383673.35 |
| ORB/ES_NY-RR5 | MES | 846 | 122.60 | 67.45 | -55.15 | $26229.00 | $301633.50 |
| NQ NY ORB R11 | MNQ | 552 | 126.62 | 92.64 | -33.97 | $16150.00 | $185725.00 |
| Combined ALPHA_V1 legs | MNQ+MES | 4027 | 686.32 | 465.30 | -221.03 | $105084.50 | $1208471.75 |

## Exact Live Engine

| Leg | Contract | Trades | Old fee net R | New fee net R | Delta R | Old comm | New comm |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HTF_LSI/NQ_NY-L24 | MNQ | 485 | 90.12 | 80.59 | -9.53 | $380.80 | $4379.20 |
| ORB/NQ_ASIA-RR6 | MNQ | 726 | 198.16 | 137.91 | -60.25 | $1090.40 | $12539.60 |
| ORB/ES_ASIA-RR1.5 | MES | 1426 | 172.43 | 101.50 | -70.93 | $995.80 | $11451.70 |
| ORB/ES_NY-RR5 | MES | 849 | 140.53 | 85.17 | -55.36 | $1576.50 | $18129.75 |
| ORB/NQ_NY-R11 | MNQ | 554 | 145.06 | 110.80 | -34.26 | $624.60 | $7182.90 |
| Combined ALPHA_V1 legs | MNQ+MES | 4040 | 746.30 | 515.97 | -230.33 | $4668.10 | $53683.15 |

## Read

- The new fee model is a small but nonzero R haircut in research because those configs use a large nominal research risk.
- The live-engine exact rows show the more relevant haircut because contract sizing and single-contract caps use the current ALPHA sprint risks.
- Runtime: cached rows reused for report generation.
