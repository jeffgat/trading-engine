#!/usr/bin/env python3
"""Start the backtester API server."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import uvicorn

from orb_backtest.api import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the backtester API server.")
    parser.add_argument("--host", default=os.environ.get("BACKTEST_API_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BACKTEST_API_PORT", "8000")))
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
