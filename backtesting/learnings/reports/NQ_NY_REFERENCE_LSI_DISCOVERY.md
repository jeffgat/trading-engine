# NQ NY Reference LSI Discovery

- Holdout frozen at `2025-01-01` and not used.
- Discovery `2016-01-01` to `2022-12-31`.
- Validation `2023-01-01` to `2024-12-31`.

## Baseline

- pre-holdout trades: `251`
- pre-holdout PF / avgR: `1.0561` / `0.0136`
- validation trades: `57`
- validation PF / avgR: `1.2182` / `0.0735`
- structurally alive: `YES`

## Stage A Top 10

- `NQ NY reference_lsi short 11:00 near gap3 inv12 rr2 tp0.5`: val avgR `0.5775`, val PF `4.8038`, pre trades `29`
- `NQ NY reference_lsi short 11:00 near gap3 inv18 rr2 tp0.5`: val avgR `0.5775`, val PF `4.8038`, pre trades `30`
- `NQ NY reference_lsi short 11:00 near gap6 inv12 rr2 tp0.5`: val avgR `0.5082`, val PF `5.4167`, pre trades `43`
- `NQ NY reference_lsi short 11:00 near gap6 inv18 rr2 tp0.5`: val avgR `0.5082`, val PF `5.4167`, pre trades `44`
- `NQ NY reference_lsi short 11:00 far gap3 inv6 rr2 tp0.5`: val avgR `0.5`, val PF `0.0`, pre trades `14`
- `NQ NY reference_lsi short 11:00 near gap6 inv6 rr2 tp0.5`: val avgR `0.4493`, val PF `3.3413`, pre trades `27`
- `NQ NY reference_lsi short 11:00 near gap3 inv6 rr2 tp0.5`: val avgR `0.4367`, val PF `2.7586`, pre trades `19`
- `NQ NY reference_lsi short 12:00 near gap6 inv6 rr2 tp0.5`: val avgR `0.3322`, val PF `2.1822`, pre trades `36`
- `NQ NY reference_lsi short 13:00 near gap6 inv6 rr2 tp0.5`: val avgR `0.3322`, val PF `2.1822`, pre trades `38`
- `NQ NY reference_lsi short 14:00 near gap6 inv6 rr2 tp0.5`: val avgR `0.3322`, val PF `2.1822`, pre trades `38`

## Stage B Top 10

- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.0 tp0.8`: val avgR `0.3786`, val PF `1.9596`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.8`: val avgR `0.3713`, val PF `1.9652`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi both 11:00 near gap12 inv18 rr3.0 tp0.8`: val avgR `0.3562`, val PF `1.9136`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.0 tp0.7`: val avgR `0.3499`, val PF `1.8873`, rr `3.0`, tp1 `0.7`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.7`: val avgR `0.3451`, val PF `1.8959`, rr `3.0`, tp1 `0.7`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.5`: val avgR `0.345`, val PF `1.9283`, rr `3.0`, tp1 `0.5`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr2.5 tp0.8`: val avgR `0.3333`, val PF `1.8419`, rr `2.5`, tp1 `0.8`
- `NQ NY reference_lsi both 11:00 near gap12 inv18 rr3.0 tp0.7`: val avgR `0.3283`, val PF `1.8431`, rr `3.0`, tp1 `0.7`
- `NQ NY reference_lsi both 13:00 near gap6 inv12 rr3.0 tp0.8`: val avgR `0.326`, val PF `1.8328`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.6`: val avgR `0.3218`, val PF `1.8344`, rr `3.0`, tp1 `0.6`

## Promoted

- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.8`: WF avgR `0.1272`, WF PF `1.3495`, plateau `0.3582`, PSR `0.788`, DSR `0.1687`
- `NQ NY reference_lsi both 11:00 near gap12 inv12 rr3.0 tp0.8`: WF avgR `0.1044`, WF PF `1.2838`, plateau `0.3642`, PSR `0.7686`, DSR `0.155`
- `NQ NY reference_lsi both 11:00 near gap6 inv18 rr3.0 tp0.7`: WF avgR `0.1016`, WF PF `1.2825`, plateau `0.3461`, PSR `0.7306`, DSR `0.1295`
