"""Load and cache 5-minute OHLCV data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "raw"


def load_5m_data(
    filename: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load a 5-minute CSV file and return a datetime-indexed DataFrame.

    Parameters
    ----------
    filename : str
        File name (looked up in data/raw/) or an absolute path.
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).
    """
    path = Path(filename)
    if not path.is_absolute():
        path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")

    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    return df
