"""
Walk-forward analysis: splits the available historical data into many rolling
train/test windows and evaluates each symbol's assigned strategy on each OUT-OF-SAMPLE
test window. This gives a much larger, faster read on robustness than waiting for live
paper-trading days to accumulate one at a time - without compromising validity, since
each test window is still data the "decision" wasn't fitted to.

This does NOT replace live paper trading. It answers a different, complementary question:
  - Live paper trading: "does this hold up on days that didn't exist when we chose it?"
  - Walk-forward analysis: "does this hold up across MANY different historical periods,
    or did it only work in the one window we happened to look at?"

Usage:
    python walk_forward.py                  (all symbols in config.SYMBOLS)
    python walk_forward.py AAPL MSFT         (specific symbols)
"""

import sys
import time
import pandas as pd
import config
from data.fetcher import fetch_historical
from strategies.signals import STRATEGIES
from backtest.engine import run_backtest


def make_windows(df, train_months=18, test_months=6, step_months=6):
    """
    Generates rolling (train_start, train_end, test_start, test_end) windows across
    the full date range available. Only the TEST window's results are reported -
    the train period exists conceptually (where you'd tune parameters) but since this
    system uses fixed parameters, train/test here really means "in-sample vs out-of-sample
    time periods," which is still meaningful for checking consistency across time.
    """
    start = df.index.min()
    end = df.index.max()
    windows = []

    test_start = start + pd.DateOffset(months=train_months)
    while test_start + pd.DateOffset(months=test_months) <= end:
        test_end = test_start + pd.DateOffset(months=test_months)
        windows.append((test_start, test_end))
        test_start = test_start + pd.DateOffset(months=step_months)

    return windows


def run_walk_forward(symbol):
    strategy_name = config.STRATEGY_MAP.get(symbol, config.STRATEGY)
    strategy_fn = STRATEGIES[strategy_name]

    df = fetch_historical(symbol, config.BACKTEST_START, config.BACKTEST_END)
    windows = make_windows(df)

    if not windows:
        print(f"{symbol}: not enough history for walk-forward windows (need ~2 years minimum)")
        return []

    results = []
    for test_start, test_end in windows:
        window_df = df[(df.index >= test_start) & (df.index < test_end)].copy()
        if len(window_df) < 30:
            continue

        if strategy_name == "sma_crossover":
            window_df = strategy_fn(window_df, config.FAST_MA, config.SLOW_MA)
        else:
            window_df = strategy_fn(window_df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)

        result = run_backtest(window_df, config, commission_pct=config.COMMISSION_PCT)
        m = result["metrics"]
        results.append({
            "symbol": symbol,
            "strategy": strategy_name,
            "window": f"{test_start.date()} to {test_end.date()}",
            "return_pct": m["total_return_pct"],
            "sharpe": m["sharpe_ratio"],
            "max_dd_pct": m["max_drawdown_pct"],
            "win_rate_pct": m["win_rate_pct"],
            "profit_factor": m["profit_factor"],
            "num_trades": m["num_trades"],
        })

    return results


def summarize(all_results):
    df = pd.DataFrame(all_results)
    if df.empty:
        print("No walk-forward windows produced results.")
        return

    print("\n" + "=" * 90)
    print("WALK-FORWARD RESULTS - PER WINDOW")
    print("=" * 90)
    for symbol in df["symbol"].unique():
        sub = df[df["symbol"] == symbol]
        print(f"\n{symbol} ({sub['strategy'].iloc[0]}):")
        print(sub[["window", "return_pct", "sharpe", "max_dd_pct", "win_rate_pct", "profit_factor", "num_trades"]]
              .to_string(index=False))

    print("\n" + "=" * 90)
    print("CONSISTENCY SUMMARY - does this hold up across MANY periods, or just one?")
    print("=" * 90)
    for symbol in df["symbol"].unique():
        sub = df[df["symbol"] == symbol]
        numeric_returns = pd.to_numeric(sub["return_pct"], errors="coerce").dropna()
        numeric_sharpe = pd.to_numeric(sub["sharpe"], errors="coerce").dropna()
        positive_windows = (numeric_returns > 0).sum()
        total_windows = len(numeric_returns)
        print(f"\n{symbol}: profitable in {positive_windows}/{total_windows} windows "
              f"({100*positive_windows/total_windows:.0f}% of periods)" if total_windows else f"\n{symbol}: no valid windows")
        if total_windows:
            print(f"  Return range across windows: {numeric_returns.min():.2f}% to {numeric_returns.max():.2f}%")
            print(f"  Average Sharpe across windows: {numeric_sharpe.mean():.2f}")
            print(f"  Sharpe std deviation (consistency - lower is more consistent): {numeric_sharpe.std():.2f}")


if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else config.SYMBOLS

    all_results = []
    for idx, symbol in enumerate(symbols):
        if idx > 0:
            time.sleep(1.5)  # avoid Yahoo rate limiting
        print(f"Running walk-forward analysis for {symbol}...")
        all_results.extend(run_walk_forward(symbol))

    summarize(all_results)
