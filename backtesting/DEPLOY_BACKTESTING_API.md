# Deploy Backtesting API to DigitalOcean

The droplet now has two backtesting-related services:

- `experiments-db` on port `8100`: lightweight shared SQLite API.
- `orb-backtester` on port `8200`: full FastAPI app for dashboard reads, candles, backtests, optimizations, news/regime reports, and saved configs.

The frontend keeps using `/bt-api/*`. In local dev, Vite proxies that to `localhost:8000`. In Vercel, `frontend/vercel.json` rewrites it to `http://143.110.148.234:8200/api/*`.

## First-Time Setup

From the repo root:

```bash
bash backtesting/deploy/deploy_api.sh --setup
```

This creates `/opt/orb-backtester`, installs the `orb-backtester` systemd service, and creates `/opt/orb-backtester/.env` if missing.

Make sure port `8200/tcp` is reachable from Vercel. If the droplet uses UFW, allow it:

```bash
ufw allow 8200/tcp
```

If the droplet is behind a DigitalOcean Cloud Firewall, add `8200/tcp` there instead.

If the server should sync market data from Cloudflare R2, fill these values on the droplet:

```bash
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=orb-backtests-data
```

## Deploy Code

Manual deploy:

```bash
bash backtesting/deploy/deploy_api.sh
```

Manual deploy plus raw market-data sync:

```bash
bash backtesting/deploy/deploy_api.sh --sync-data
```

Pushes to `main` that touch the backtesting API source, runner, pyproject, lockfile, or deploy files also run `.github/workflows/deploy-backtesting-api.yml`.

## Verify

On the droplet:

```bash
systemctl status orb-backtester
curl -sf http://localhost:8200/api/health
```

From outside:

```bash
curl -sf http://143.110.148.234:8200/api/health
```

## Data Note

The deploy intentionally excludes `backtesting/data/` because it is gitignored and large. The full API will boot without it, but compute/chart endpoints such as `/api/backtest`, `/api/optimize`, `/api/candles`, and `/api/news-candles` need the relevant files in `/opt/orb-backtester/data/raw`.
