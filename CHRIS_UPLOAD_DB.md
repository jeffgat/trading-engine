# Upload your local experiments.db to the shared droplet

Your local experiments.db has all 45 backtests and 15 starred strategies, but the droplet only has 1. Run this command to upload your full DB:

```bash
curl -X POST http://143.110.148.234:8100/api/upload-db \
     --data-binary @python/data/results/experiments.db \
     -H "Content-Type: application/octet-stream"
```

Run this from the repo root (where `python/` is). It will:
1. Backup the current DB on the droplet
2. Replace it with your local copy
3. Return a count of runs, optimizations, and starred items

After that, set your env var so all future reads/writes go to the shared DB:

```bash
echo 'export EXPERIMENTS_DB_URL="http://143.110.148.234:8100"' >> ~/.zshrc
source ~/.zshrc
```

Verify it works:

```bash
curl http://143.110.148.234:8100/api/health
curl http://143.110.148.234:8100/api/starred | python3 -m json.tool | head -30
```
