"""Load and cache OHLCV data (5-minute, 1-minute, 30-second, 1-second).

Parquet is preferred over CSV for all files — run scripts/convert_to_parquet.py
once after downloading new data to get faster reads and smaller files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "raw"


def _load_ohlcv(
    stem_path: Path,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load OHLCV from Parquet (preferred) or CSV, with optional date filtering.

    Parameters
    ----------
    stem_path : Path
        Path without extension (e.g. ``data/raw/GC_5m``).
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).

    Raises
    ------
    FileNotFoundError
        If neither .parquet nor .csv exists at the stem path.
    """
    parquet = stem_path.with_suffix(".parquet")
    csv = stem_path.with_suffix(".csv")

    if parquet.exists():
        df = pd.read_parquet(parquet)
    elif csv.exists():
        df = pd.read_csv(csv, parse_dates=["datetime"], index_col="datetime")
    else:
        raise FileNotFoundError(f"No .parquet or .csv found for {stem_path}")

    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    return df


def load_5m_data(
    filename: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load a 5-minute OHLCV file and return a datetime-indexed DataFrame.

    Prefers .parquet over .csv when both exist.

    Parameters
    ----------
    filename : str
        File name (looked up in data/raw/) or an absolute path.
        Extension may be .csv or .parquet — both are accepted.
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).
    """
    path = Path(filename)
    if not path.is_absolute():
        path = DATA_DIR / filename

    # Strip extension to get stem (handles both .csv and .parquet inputs)
    stem = path.with_suffix("")
    return _load_ohlcv(stem, start, end)


def load_1m_for_5m(
    filename_5m: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load the 1-minute file corresponding to a 5-minute data file.

    Derives the 1m path by replacing ``_5m`` with ``_1m`` in the stem.
    Prefers .parquet over .csv.

    Parameters
    ----------
    filename_5m : str
        The 5-minute file name or absolute path.
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).

    Raises
    ------
    FileNotFoundError
        If neither .parquet nor .csv exists for the derived 1-minute path.
    """
    stem_name = Path(Path(filename_5m).name).stem.replace("_5m", "_1m")

    path = Path(filename_5m)
    if path.is_absolute():
        stem = path.parent / stem_name
    else:
        stem = DATA_DIR / stem_name

    return _load_ohlcv(stem, start, end)


def load_30s_for_5m(
    filename_5m: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame | None:
    """Load the 30-second file corresponding to a 5-minute data file.

    Derives the 30s path by replacing ``_5m`` with ``_30s`` in the stem.
    Prefers .parquet over .csv. Currently only GC has a 30s file.

    Returns None silently if no 30s file exists, so callers can
    unconditionally attempt to load without guarding against missing data.

    Parameters
    ----------
    filename_5m : str
        The 5-minute file name or absolute path.
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).
    """
    stem_name = Path(Path(filename_5m).name).stem.replace("_5m", "_30s")

    path = Path(filename_5m)
    if path.is_absolute():
        stem = path.parent / stem_name
    else:
        stem = DATA_DIR / stem_name

    if not stem.with_suffix(".parquet").exists() and not stem.with_suffix(".csv").exists():
        return None

    return _load_ohlcv(stem, start, end)


def load_1s_for_5m(
    filename_5m: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame | None:
    """Load the 1-second file corresponding to a 5-minute data file.

    Derives the 1s path by replacing ``_5m`` with ``_1s`` in the stem.
    Prefers .parquet over .csv. Currently only GC has a 1s file.

    Returns None silently if no 1s file exists, so callers can
    unconditionally attempt to load without guarding against missing data.

    Parameters
    ----------
    filename_5m : str
        The 5-minute file name or absolute path.
    start : str, optional
        Start date filter (YYYY-MM-DD).
    end : str, optional
        End date filter (YYYY-MM-DD).
    """
    stem_name = Path(Path(filename_5m).name).stem.replace("_5m", "_1s")

    path = Path(filename_5m)
    if path.is_absolute():
        stem = path.parent / stem_name
    else:
        stem = DATA_DIR / stem_name

    if not stem.with_suffix(".parquet").exists() and not stem.with_suffix(".csv").exists():
        return None

    return _load_ohlcv(stem, start, end)
