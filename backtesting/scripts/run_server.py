#!/usr/bin/env python3
"""Start the backtester API server."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import uvicorn

# Local dev should serve the local SQLite DB unless a main DB URL is explicitly
# configured. This must happen before importing orb_backtest.api, because the
# experiments module selects local vs remote storage at import time.
if "MAIN_DB_URL" not in os.environ and "EXPERIMENTS_DB_URL" not in os.environ:
    os.environ["MAIN_DB_URL"] = ""
    os.environ["EXPERIMENTS_DB_URL"] = ""

from orb_backtest.api import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the backtester API server.")
    parser.add_argument("--host", default=os.environ.get("BACKTEST_API_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BACKTEST_API_PORT", "8000")))
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
