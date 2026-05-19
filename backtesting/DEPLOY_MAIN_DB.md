# Deploy Main DB to DigitalOcean

The main DB is the only SQLite database for backtesting history, saved configs,
execution logs, live trades, and execution config webhooks.

- Service: `main-db`
- API port: `8100`
- Remote directory: `/opt/main-db`
- SQLite file: `/opt/main-db/main.db`
- Preferred env vars: `MAIN_DB_URL`, `MAIN_DB_PATH`
- Legacy aliases still accepted: `EXPERIMENTS_DB_URL`, `EXPERIMENTS_DB_PATH`

## Setup

```bash
bash backtesting/deploy/deploy_db.sh --setup
```

The setup command uploads the local `backtesting/data/results/experiments.db`
as `/opt/main-db/main.db` when the local file exists.

## Deploy

```bash
bash backtesting/deploy/deploy_db.sh
```

The deploy script also migrates the old remote file from
`/opt/experiments-db/experiments.db` to `/opt/main-db/main.db` if the new DB file
does not already exist.

## Runtime Env

For client processes:

```bash
MAIN_DB_URL=http://143.110.148.234:8100
```

For the main DB service itself:

```bash
MAIN_DB_PATH=/opt/main-db/main.db
MAIN_DB_URL=
```

The service intentionally leaves `MAIN_DB_URL` blank so it writes its local
SQLite file directly instead of routing through its own HTTP API.
