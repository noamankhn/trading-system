"""
Data layer. Pulls historical OHLCV data for backtesting and live/recent data for paper trading.

Run locally (needs internet):
    pip install yfinance pandas
"""

import pandas as pd


def fetch_historical(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily OHLCV history for backtesting.
    Returns a DataFrame indexed by date with columns: Open, High, Low, Close, Volume
    """
    import yfinance as yf
    import time

    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)

    # yfinance sometimes silently returns an empty/partial frame when Yahoo rate-limits
    # a rapid sequence of requests - retry once after a short pause before giving up.
    if df.empty or len(df) < 30:
        time.sleep(2)
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}. Check the symbol/date range.")

    # yfinance sometimes returns multi-index columns - flatten if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    if len(df) < 30:
        print(f"  WARNING: only {len(df)} rows returned for {symbol} - "
              f"likely rate-limited or bad symbol, results may be unreliable")

    return df


def fetch_recent(symbol: str, lookback_days: int = 60) -> pd.DataFrame:
    """
    Fetch recent data for live signal generation (paper trading loop + dashboard).
    """
    import yfinance as yf
    import time
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    df = yf.download(symbol, start=start_str, end=end_str, progress=False, auto_adjust=True)

    # Yahoo occasionally returns an empty/partial response transiently (rate limiting,
    # brief API hiccup) - retry once after a short pause before treating it as a real failure.
    if df.empty or len(df) < 5:
        time.sleep(2)
        df = yf.download(symbol, start=start_str, end=end_str, progress=False, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {symbol} after retry - "
                          f"this may be a transient Yahoo Finance issue, try again shortly")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.dropna()


def generate_synthetic(symbol: str = "SYNTH", days: int = 500, seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic-looking synthetic OHLCV data with no internet required.
    Used here to prove the pipeline works end-to-end without network access.
    DO NOT use synthetic data to evaluate a real strategy - it has no real market structure.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=days)
    n = len(dates)  # bdate_range can return a slightly different count than requested

    # random walk with slight upward drift, clipped volatility - just for pipeline testing
    returns = rng.normal(loc=0.0003, scale=0.015, size=n)
    price = 100 * (1 + returns).cumprod()

    high = price * (1 + rng.uniform(0, 0.01, n))
    low = price * (1 - rng.uniform(0, 0.01, n))
    open_ = price * (1 + rng.normal(0, 0.003, n))
    volume = rng.integers(1_000_000, 5_000_000, n)

    df = pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": price,
        "Volume": volume,
    }, index=dates)

    return df
