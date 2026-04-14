# NQ NY HTF-LSI Additive Diversification Check

- Objective: test whether the wide additive `60m EQHL 15pt` challenger deserves a backup/diversification slot next to the incumbent `15m EQHL tol1` additive lead.
- Method: rerun both frozen `5m lag24` additive branches, measure trade-date overlap and daily-R correlation, then test constant-gross-risk blends where incumbent weight + challenger weight = 1.0.
- Holdout split: `2025-04-01` onward.

## Overlap

- Full sample: shared trade dates `500`, Jaccard `0.796`, daily-R correlation `0.8603`.
- Pre-holdout: shared trade dates `462`, Jaccard `0.797`, daily-R correlation `0.8542`.
- Holdout: shared trade dates `38`, Jaccard `0.792`, daily-R correlation `0.9325`.

## Constant-Risk Blend Sweep

| Inc Weight | Chal Weight | Pre Total R | Pre DD | Pre Calmar | Holdout Total R | Holdout DD | Holdout Calmar |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.00 | 0.00 | 82.68 | -11.30 | 0.77 | 15.11 | -3.00 | 5.27 |
| 0.75 | 0.25 | 86.20 | -10.73 | 0.85 | 14.28 | -3.00 | 4.98 |
| 0.50 | 0.50 | 89.71 | -10.74 | 0.88 | 13.46 | -3.00 | 4.69 |
| 0.25 | 0.75 | 93.22 | -11.14 | 0.88 | 12.63 | -3.00 | 4.40 |
| 0.00 | 1.00 | 96.74 | -11.54 | 0.88 | 11.81 | -3.00 | 4.12 |
