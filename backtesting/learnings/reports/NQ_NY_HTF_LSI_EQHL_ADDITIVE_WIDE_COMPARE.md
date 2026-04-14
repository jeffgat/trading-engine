# NQ NY HTF-LSI EQHL Additive Wide Compare

- Objective: test whether wider EQHL zones help as an additive layer on top of the frozen `5m lag24` lead.
- Scope: holdout stays closed. All non-source parameters are frozen to the current `5m lag24` operating lead (`08:30-13:30`, `rr3.5`, `tp1=0.4`, `gap3.0`, `htf60 n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).
- Controls: `HTF-only` and the current additive incumbent `HTF + 15m EQHL tol1`.
- Wide additive shortlist: EQHL source TF `{5m,15m,60m}` x tolerance `{3,5,10,15,20}` points with `touches=2`, `eqhl_n_left=2`, `lookback=48`.

| Label | Family | Source | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 htf_only control | htf_only | HTF-only | 1.270 | 0.118 | 1.717 | 0.292 | 6.831 | 1.467 | 0.199 | 5.432 | 299 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent | incumbent_tight | HTF+EQHL 15m tol1 | 1.257 | 0.115 | 1.786 | 0.312 | 8.037 | 1.515 | 0.216 | 6.359 | 322 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt | wide_additive | HTF+EQHL 60m 15pt | 1.269 | 0.119 | 1.760 | 0.310 | 6.860 | 1.471 | 0.201 | 6.530 | 375 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 10pt | wide_additive | HTF+EQHL 60m 10pt | 1.263 | 0.118 | 1.742 | 0.304 | 6.746 | 1.454 | 0.196 | 6.103 | 359 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 3pt | wide_additive | HTF+EQHL 60m 3pt | 1.284 | 0.123 | 1.734 | 0.291 | 7.111 | 1.453 | 0.192 | 5.828 | 332 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 20pt | wide_additive | HTF+EQHL 60m 20pt | 1.272 | 0.120 | 1.662 | 0.279 | 6.436 | 1.432 | 0.187 | 5.775 | 387 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m 3pt | wide_additive | HTF+EQHL 15m 3pt | 1.276 | 0.120 | 1.451 | 0.209 | 6.186 | 1.367 | 0.163 | 5.569 | 377 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 5pt | wide_additive | HTF+EQHL 60m 5pt | 1.265 | 0.116 | 1.694 | 0.285 | 7.302 | 1.426 | 0.183 | 5.445 | 344 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m 15pt | wide_additive | HTF+EQHL 15m 15pt | 1.188 | 0.085 | 1.503 | 0.219 | 7.122 | 1.338 | 0.151 | 5.079 | 444 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m 10pt | wide_additive | HTF+EQHL 15m 10pt | 1.207 | 0.092 | 1.359 | 0.166 | 3.986 | 1.292 | 0.133 | 4.978 | 433 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m 5pt | wide_additive | HTF+EQHL 15m 5pt | 1.230 | 0.101 | 1.308 | 0.153 | 4.790 | 1.313 | 0.141 | 4.602 | 411 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m 3pt | wide_additive | HTF+EQHL 5m 3pt | 1.130 | 0.061 | 1.327 | 0.163 | 3.431 | 1.227 | 0.113 | 3.977 | 455 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m 5pt | wide_additive | HTF+EQHL 5m 5pt | 1.114 | 0.053 | 1.480 | 0.215 | 4.879 | 1.304 | 0.141 | 3.581 | 504 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m 20pt | wide_additive | HTF+EQHL 15m 20pt | 1.153 | 0.069 | 1.416 | 0.184 | 6.095 | 1.276 | 0.123 | 3.530 | 463 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m 10pt | wide_additive | HTF+EQHL 5m 10pt | 1.076 | 0.035 | 1.408 | 0.182 | 4.323 | 1.212 | 0.100 | 2.889 | 586 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m 15pt | wide_additive | HTF+EQHL 5m 15pt | 1.065 | 0.029 | 1.224 | 0.111 | 2.552 | 1.104 | 0.052 | 1.306 | 639 |
| NQ NY HTF_LSI 5m lag24 + EQHL5m 20pt | wide_additive | HTF+EQHL 5m 20pt | 1.090 | 0.039 | 1.227 | 0.109 | 2.372 | 1.102 | 0.048 | 1.115 | 664 |
