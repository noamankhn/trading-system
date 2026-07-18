"""
Diagnostic: inspect exactly what the strategy computed for a symbol that produced
zero trades, to see whether it's a data issue, a NaN issue, or a genuine "no crossovers" case.

Usage:
    python diagnose.py MSFT
"""

import sys
import config
from data.fetcher import fetch_historical
from strategies.signals import sma_crossover

symbol = sys.argv[1] if len(sys.argv) > 1 else "MSFT"

df = fetch_historical(symbol, config.BACKTEST_START, config.BACKTEST_END)
print(f"Raw data shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Column dtypes:\n{df.dtypes}\n")
print(f"Close column - NaN count: {df['Close'].isna().sum()} / {len(df)}")
print(f"Close sample:\n{df['Close'].tail(5)}\n")

df2 = sma_crossover(df, config.FAST_MA, config.SLOW_MA)
print(f"fast_ma NaN count: {df2['fast_ma'].isna().sum()}")
print(f"slow_ma NaN count: {df2['slow_ma'].isna().sum()}")
print(f"\nLast 15 rows of Close / fast_ma / slow_ma / signal / position:")
print(df2[["Close", "fast_ma", "slow_ma", "signal", "position"]].tail(15).to_string())

print(f"\nsignal value counts:\n{df2['signal'].value_counts()}")
print(f"\nposition value counts:\n{df2['position'].value_counts()}")

crossovers = (df2["signal"].diff() != 0).sum()
print(f"\nNumber of signal changes (potential trade triggers): {crossovers}")
