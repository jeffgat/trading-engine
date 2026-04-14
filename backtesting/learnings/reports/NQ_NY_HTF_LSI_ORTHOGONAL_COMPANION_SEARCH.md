# NQ NY HTF-LSI Orthogonal Companion Search

- Objective: search for a genuinely different companion against the current `NQ NY HTF_LSI 5m lag24` lead.
- Ranking lens: low overlap, low daily-R correlation, acceptable standalone quality, and positive 50/50 blend behavior.

## Ranked Candidates

| Candidate | Family | In Book | Holdout Corr | Holdout Jaccard | Holdout 50/50 Calmar | Holdout 50/50 Total R | Pre 50/50 Calmar |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| ALPHA_V1 NQ Asia ORB | nq_asia_orb | True | -0.060 | 0.048 | 8.24 | 21.96 | 1.64 |
| ALPHA_V1 NQ NY legacy LSI | legacy_nq_ny_lsi | False | 0.102 | 0.116 | 6.60 | 9.46 | 1.01 |
| NQ NY EQHL_LSI 3m eqhl15m 15pt | eqhl_3m_to_15m_15pt | False | 0.394 | 0.268 | 6.07 | 14.11 | 0.83 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 | htf_plus_eqhl_15m_tol1 | False | 1.000 | 1.000 | 5.27 | 15.11 | 0.76 |
| ALPHA_V1 ES Asia ORB | es_asia_orb | True | -0.003 | 0.099 | 5.02 | 15.40 | 1.51 |
| NQ NY EQHL_LSI 5m eqhl5m 5pt | eqhl_5m_to_5m_5pt | False | 0.614 | 0.468 | 3.38 | 11.72 | 0.54 |
| ALPHA_V1 ES NY ORB | es_ny_orb | True | 0.065 | 0.113 | 3.14 | 15.94 | 1.70 |
| NQ NY HTF_LSI 2m secondary anchor | htf_lsi_2m_anchor | False | 0.419 | 0.337 | 1.58 | 7.72 | 0.77 |
