# NQ NY Reference LSI Discovery (3m)

- Base signal timeframe: `3m`
- Reference level group: `previous_day_asia`
- Holdout frozen at `2025-01-01` and not used.
- Discovery `2016-01-01` to `2022-12-31`.
- Validation `2023-01-01` to `2024-12-31`.

## Baseline

- pre-holdout trades: `188`
- pre-holdout PF / avgR: `1.4965` / `0.1447`
- validation trades: `41`
- validation PF / avgR: `2.0714` / `0.2836`
- structurally alive: `YES`

## Stage A Top 10

- `NQ NY reference_lsi 3m previous_day_asia short 14:00 far gap3 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `12`
- `NQ NY reference_lsi 3m previous_day_asia short 12:00 far gap3 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `11`
- `NQ NY reference_lsi 3m previous_day_asia short 13:00 far gap3 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `11`
- `NQ NY reference_lsi 3m previous_day_asia short 12:00 far gap6 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `13`
- `NQ NY reference_lsi 3m previous_day_asia short 12:00 far gap9 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `14`
- `NQ NY reference_lsi 3m previous_day_asia short 12:00 far gap12 inv6 rr2 tp0.5`: val avgR `1.5278`, val PF `0.0`, pre trades `15`
- `NQ NY reference_lsi 3m previous_day_asia short 11:00 far gap3 inv6 rr2 tp0.5`: val avgR `1.5`, val PF `0.0`, pre trades `10`
- `NQ NY reference_lsi 3m previous_day_asia short 11:00 far gap6 inv6 rr2 tp0.5`: val avgR `1.5`, val PF `0.0`, pre trades `12`
- `NQ NY reference_lsi 3m previous_day_asia short 11:00 far gap9 inv6 rr2 tp0.5`: val avgR `1.5`, val PF `0.0`, pre trades `13`
- `NQ NY reference_lsi 3m previous_day_asia short 11:00 far gap12 inv6 rr2 tp0.5`: val avgR `1.5`, val PF `0.0`, pre trades `14`

## Stage B Top 10

- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr3.0 tp0.8`: val avgR `0.5531`, val PF `3.2446`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr2.5 tp0.8`: val avgR `0.5492`, val PF `3.1872`, rr `2.5`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr3.0 tp0.7`: val avgR `0.5284`, val PF `3.1454`, rr `3.0`, tp1 `0.7`
- `NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr3.0 tp0.8`: val avgR `0.5284`, val PF `3.1391`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr2.5 tp0.8`: val avgR `0.5248`, val PF `3.0873`, rr `2.5`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 12:00 near gap9 inv12 rr3.0 tp0.8`: val avgR `0.5096`, val PF `2.9766`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr3.0 tp0.7`: val avgR `0.5058`, val PF `3.0496`, rr `3.0`, tp1 `0.7`
- `NQ NY reference_lsi 3m previous_day_asia both 12:00 near gap9 inv12 rr2.5 tp0.8`: val avgR `0.5058`, val PF `2.9248`, rr `2.5`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap9 inv12 rr3.0 tp0.8`: val avgR `0.4945`, val PF `2.9939`, rr `3.0`, tp1 `0.8`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap9 inv12 rr2.5 tp0.8`: val avgR `0.491`, val PF `2.9445`, rr `2.5`, tp1 `0.8`

## Promoted

- `NQ NY reference_lsi 3m previous_day_asia both 12:00 near gap9 inv12 rr3.0 tp0.8`: WF avgR `0.3248`, WF PF `1.9874`, plateau `0.4978`, PSR `0.9961`, DSR `0.8198`
- `NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr2.5 tp0.8`: WF avgR `0.3189`, WF PF `2.0386`, plateau `0.4587`, PSR `0.9961`, DSR `0.828`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr2.5 tp0.8`: WF avgR `0.3007`, WF PF `1.9382`, plateau `0.477`, PSR `0.9935`, DSR `0.7771`
