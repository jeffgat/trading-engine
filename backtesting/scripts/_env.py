"""Environment helpers for local backtesting scripts."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_backtesting_env() -> Path:
    """Load backtesting/.env when present and return its path."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return env_path

    try:
        from dotenv import load_dotenv
    except ImportError:
        with env_path.open() as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    else:
        load_dotenv(env_path)

    return env_path
