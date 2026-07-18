"""
Compares sma_crossover vs rsi_mean_reversion on specific symbols, side by side.
Use this to decide which strategy actually fits which asset, instead of guessing
or tuning one strategy's parameters to force a fit.

Usage:
    python compare_strategies.py MSFT BTC-USD
    python compare_strategies.py          (defaults to config.NEEDS_DIFFERENT_STRATEGY)
"""

import sys
import time
import config
from data.fetcher import fetch_historical
from strategies.signals import sma_crossover, rsi_mean_reversion
from backtest.engine import run_backtest

symbols = sys.argv[1:] if len(sys.argv) > 1 else config.NEEDS_DIFFERENT_STRATEGY

results = {}

for idx, symbol in enumerate(symbols):
    if idx > 0:
        time.sleep(1.5)  # avoid Yahoo rate limiting

    df = fetch_historical(symbol, config.BACKTEST_START, config.BACKTEST_END)
    print(f"{symbol}: fetched {len(df)} rows")

    df_sma = sma_crossover(df.copy(), config.FAST_MA, config.SLOW_MA)
    result_sma = run_backtest(df_sma, config, commission_pct=config.COMMISSION_PCT)

    df_rsi = rsi_mean_reversion(df.copy(), config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
    result_rsi = run_backtest(df_rsi, config, commission_pct=config.COMMISSION_PCT)

    results[symbol] = {"sma_crossover": result_sma["metrics"], "rsi_mean_reversion": result_rsi["metrics"]}

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

for symbol, strategies in results.items():
    print(f"\n{symbol}")
    print(f"{'Metric':<22}{'SMA Crossover':<20}{'RSI Mean-Reversion':<20}")
    print("-" * 62)
    keys = ["total_return_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct",
            "win_loss_ratio", "profit_factor", "num_trades", "risk_halts_triggered"]
    for k in keys:
        sma_val = strategies["sma_crossover"].get(k, "n/a")
        rsi_val = strategies["rsi_mean_reversion"].get(k, "n/a")
        print(f"{k:<22}{str(sma_val):<20}{str(rsi_val):<20}")

    sma_sharpe = strategies["sma_crossover"].get("sharpe_ratio", -999)
    rsi_sharpe = strategies["rsi_mean_reversion"].get("sharpe_ratio", -999)
    better = "RSI Mean-Reversion" if rsi_sharpe > sma_sharpe else "SMA Crossover"
    print(f"  -> Better fit by Sharpe ratio: {better}")
