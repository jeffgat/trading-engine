"""FastAPI server for the ORB+FVG backtester."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import (
    default_config,
    with_overrides,
    NY_SESSION,
    ASIA_SESSION,
    LDN_SESSION,
)
from .data.instruments import get_instrument
from .data.loader import load_5m_data
from .engine.simulator import run_backtest, EXIT_NO_FILL
from .results.export import (
    results_to_dict,
    save_backtest_result,
    list_backtest_results,
    load_backtest_result,
    delete_backtest_result,
)
from .results.metrics import compute_metrics

app = FastAPI(title="ORB+FVG Backtester API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_MAP = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}


class BacktestRequest(BaseModel):
    instrument: str = "NQ"
    sessions: list[str] = ["NY"]
    start: Optional[str] = None
    end: Optional[str] = None
    rr: Optional[float] = None
    tp1_ratio: Optional[float] = None
    risk_usd: Optional[float] = None
    atr_length: Optional[int] = None
    be_offset_ticks: Optional[int] = None
    ny_stop_atr_pct: Optional[float] = None
    ny_min_gap_atr_pct: Optional[float] = None
    ny_max_gap_points: Optional[float] = None
    asia_stop_atr_pct: Optional[float] = None
    asia_min_gap_atr_pct: Optional[float] = None
    asia_max_gap_points: Optional[float] = None
    ldn_stop_atr_pct: Optional[float] = None
    ldn_min_gap_atr_pct: Optional[float] = None
    ldn_max_gap_points: Optional[float] = None


@app.post("/api/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown instrument: {req.instrument}")

    sessions = []
    for s in req.sessions:
        if s not in SESSION_MAP:
            raise HTTPException(status_code=400, detail=f"Unknown session: {s}")
        sessions.append(SESSION_MAP[s])

    config = default_config(instrument)
    config = with_overrides(config, sessions=tuple(sessions))

    # Apply param overrides
    overrides = {}
    for field in (
        "rr", "tp1_ratio", "risk_usd", "atr_length", "be_offset_ticks",
        "ny_stop_atr_pct", "ny_min_gap_atr_pct", "ny_max_gap_points",
        "asia_stop_atr_pct", "asia_min_gap_atr_pct", "asia_max_gap_points",
        "ldn_stop_atr_pct", "ldn_min_gap_atr_pct", "ldn_max_gap_points",
    ):
        val = getattr(req, field)
        if val is not None:
            overrides[field] = val

    if overrides:
        config = with_overrides(config, **overrides)

    # Load data
    data_file = instrument.data_file
    try:
        df = load_5m_data(data_file, start=req.start, end=req.end)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Run backtest
    trades = run_backtest(df, config, start_date=req.start)

    # Build response with equity curve
    result = results_to_dict(
        trades, config,
        include_trades=True,
        include_equity_curve=True,
    )

    # Auto-save
    result_id = save_backtest_result(result)
    result["id"] = result_id

    return result


@app.get("/api/backtests")
def list_backtests():
    return list_backtest_results()


@app.get("/api/backtests/{result_id}")
def get_backtest(result_id: str):
    data = load_backtest_result(result_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    data["id"] = result_id
    return data


@app.delete("/api/backtests/{result_id}")
def delete_backtest(result_id: str):
    if not delete_backtest_result(result_id):
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"ok": True}
