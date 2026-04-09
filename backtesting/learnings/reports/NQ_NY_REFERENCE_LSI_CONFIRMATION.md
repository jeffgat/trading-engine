# NQ NY Reference LSI Confirmation

- Holdout frozen at `2025-01-01` and not used.
- Discovery `2016-01-01` to `2022-12-31`.
- Validation `2023-01-01` to `2024-12-31`.
- Raw trials `16`, effective trials `1`.

## Top Rows

- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.25 tp0.7`: val avgR `0.381`, val PF `1.9663`, pre trades `123`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.0 tp0.8`: val avgR `0.3786`, val PF `1.9596`, pre trades `123`
- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.25 tp0.7`: val avgR `0.3732`, val PF `1.9705`, pre trades `101`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.25 tp0.7`: val avgR `0.3732`, val PF `1.9705`, pre trades `103`
- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.8`: val avgR `0.3713`, val PF `1.9652`, pre trades `101`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.8`: val avgR `0.3713`, val PF `1.9652`, pre trades `103`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.0 tp0.7`: val avgR `0.3499`, val PF `1.8873`, pre trades `123`
- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.7`: val avgR `0.3451`, val PF `1.8959`, pre trades `101`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.7`: val avgR `0.3451`, val PF `1.8959`, pre trades `103`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.25 tp0.8`: val avgR `0.3352`, val PF `1.7755`, pre trades `123`
- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.25 tp0.8`: val avgR `0.3082`, val PF `1.7029`, pre trades `101`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.25 tp0.8`: val avgR `0.3082`, val PF `1.7029`, pre trades `103`
- `NQ NY reference_lsi both 11:00 near gap8 inv18 rr3.25 tp0.7`: val avgR `0.2127`, val PF `1.4774`, pre trades `113`
- `NQ NY reference_lsi both 11:00 near gap8 inv18 rr3.0 tp0.8`: val avgR `0.2111`, val PF `1.4734`, pre trades `113`
- `NQ NY reference_lsi both 11:00 near gap8 inv18 rr3.0 tp0.7`: val avgR `0.1881`, val PF `1.4214`, pre trades `113`
- `NQ NY reference_lsi both 11:00 near gap8 inv18 rr3.25 tp0.8`: val avgR `0.1558`, val PF `1.308`, pre trades `113`

## Promoted

- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.8`: WF avgR `0.1315`, WF PF `1.3534`, plateau `0.2969`, PSR `0.7891`, DSR `0.7891`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.8`: WF avgR `0.1272`, WF PF `1.3495`, plateau `0.2969`, PSR `0.788`, DSR `0.788`
- `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.25 tp0.7`: WF avgR `0.1217`, WF PF `1.3272`, plateau `0.2969`, PSR `0.7542`, DSR `0.7542`

## Decision

- Best config `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.8` is still below the repo's moderate PSR bar (`PSR 0.7891`, `DSR 0.7891`).
- Keep the 2025+ holdout closed and treat this branch as discovery-only for now.