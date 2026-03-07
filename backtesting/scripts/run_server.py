#!/usr/bin/env python3
"""Start the backtester API server."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import uvicorn

from orb_backtest.api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
