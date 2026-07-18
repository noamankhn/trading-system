"""
Proves the pipeline runs end-to-end: data -> strategy -> risk-managed backtest -> metrics.
Uses per-symbol strategy assignment from config.STRATEGY_MAP (falls back to config.STRATEGY
for any symbol not explicitly mapped).

On your own machine (needs internet):
    pip install yfinance pandas numpy
    python run_backtest_demo.py
"""

import time
import config
from data.fetcher import generate_synthetic, fetch_historical
from strategies.signals import STRATEGIES
from backtest.engine import run_backtest

USE_REAL_DATA = True  # flip to False to test the pipeline offline with synthetic data

print(f"Default strategy: {config.STRATEGY}")
print(f"Per-symbol overrides: {config.STRATEGY_MAP}")
print(f"Symbols: {config.SYMBOLS}\n")

for idx, symbol in enumerate(config.SYMBOLS):
    if USE_REAL_DATA:
        if idx > 0:
            time.sleep(1.5)  # avoid Yahoo rate limiting
        df = fetch_historical(symbol, config.BACKTEST_START, config.BACKTEST_END)
    else:
        df = generate_synthetic(symbol, days=500, seed=hash(symbol) % 1000)

    strategy_name = config.STRATEGY_MAP.get(symbol, config.STRATEGY)
    strategy_fn = STRATEGIES[strategy_name]

    print(f"{symbol}: fetched {len(df)} rows, using '{strategy_name}'"
          if len(df) else f"{symbol}: EMPTY")

    df = strategy_fn(df, config.FAST_MA, config.SLOW_MA) if strategy_name == "sma_crossover" \
        else strategy_fn(df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)

    result = run_backtest(df, config, commission_pct=config.COMMISSION_PCT)

    print(f"── {symbol} ({strategy_name}) {'(SYNTHETIC DATA - demo only)' if not USE_REAL_DATA else ''} ──")
    for k, v in result["metrics"].items():
        print(f"  {k}: {v}")
    print()
