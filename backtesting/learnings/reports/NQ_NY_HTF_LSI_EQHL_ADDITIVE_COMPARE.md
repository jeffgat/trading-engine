# NQ NY HTF-LSI EQHL Additive Compare

- Objective: compare the current `5m lag24` HTF-only lead against a narrow additive `HTF + EQHL` shortlist.
- Scope: holdout stays closed. All non-source parameters are frozen to the current `5m lag24` operating lead (`08:30-13:30`, `rr3.5`, `tp1=0.4`, `gap3.0`, `htf60 n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).
- Additive shortlist: EQHL source TF `{5m,15m}` x tolerance `{1,2}` with `touches=2`, `eqhl_n_left=2`, `lookback=48`.

| Label | Source | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 + EQHL5m tol1 | HTF+EQHL 5m tol1 | 1.288 | 0.126 | 1.582 | 0.255 | 6.480 | 1.385 | 0.174 | 7.387 | 364 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 | HTF+EQHL 15m tol1 | 1.257 | 0.115 | 1.786 | 0.312 | 8.037 | 1.515 | 0.216 | 6.359 | 322 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol2 | HTF+EQHL 15m tol2 | 1.262 | 0.115 | 1.743 | 0.298 | 7.756 | 1.495 | 0.207 | 6.296 | 333 |
| NQ NY HTF_LSI 5m lag24 lead | HTF-only | 1.270 | 0.118 | 1.717 | 0.292 | 6.831 | 1.467 | 0.199 | 5.432 | 299 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m tol2 | HTF+EQHL 5m tol2 | 1.165 | 0.077 | 1.582 | 0.255 | 7.947 | 1.272 | 0.132 | 4.337 | 386 |
