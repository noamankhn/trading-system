"""
Strategy layer. Deliberately simple, well-understood strategies -
the goal early on is a system you can fully explain and trust, not exotic alpha.

Each function takes a price DataFrame and returns it with a 'signal' column:
    1  = go long / hold long
    0  = flat / no position
   -1  = exit long (for these long-only starter strategies, -1 means "get out")
"""

import pandas as pd


def sma_crossover(df: pd.DataFrame, fast: int = 10, slow: int = 30) -> pd.DataFrame:
    """
    Classic trend-following strategy: buy when fast MA crosses above slow MA,
    exit when it crosses back below. Simple, transparent, easy to debug.
    """
    df = df.copy()
    df["fast_ma"] = df["Close"].rolling(fast).mean()
    df["slow_ma"] = df["Close"].rolling(slow).mean()

    df["signal"] = 0
    df.loc[df["fast_ma"] > df["slow_ma"], "signal"] = 1
    df.loc[df["fast_ma"] <= df["slow_ma"], "signal"] = 0

    # position = signal shifted by 1 day (can't trade on the same bar the signal forms)
    df["position"] = df["signal"].shift(1).fillna(0)
    return df


def rsi_mean_reversion(df: pd.DataFrame, period: int = 14,
                        oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
    """
    Mean-reversion strategy: buy when RSI shows oversold conditions,
    exit when it recovers to/above overbought threshold.
    """
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))

    df["signal"] = 0
    df.loc[df["rsi"] < oversold, "signal"] = 1
    df.loc[df["rsi"] > overbought, "signal"] = 0

    df["position"] = df["signal"].shift(1).fillna(0)
    return df


STRATEGIES = {
    "sma_crossover": sma_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
}
