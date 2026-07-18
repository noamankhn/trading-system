# Paper Trading System

A risk-managed algorithmic trading system, built to be **tested on simulated money first**.
It does not touch real capital until you deliberately flip that on yourself, and even then
you should only do so after weeks of paper-trading review.

## What this is / isn't
- **Is:** a working pipeline (data → strategy → risk-managed backtest → paper trading → report) you can inspect, test, and improve.
- **Isn't:** a way to turn $1,000 into fast real income. Paper trading uses simulated money by design - that's the safety mechanism, not a bug to route around.

## Structure
```
config.py                 - all settings: symbols, strategy params, risk limits
data/fetcher.py            - pulls historical (backtest) and recent (live) price data
strategies/signals.py      - SMA crossover and RSI mean-reversion strategies
risk/manager.py            - position sizing, stop-loss, daily-loss and drawdown halts
backtest/engine.py         - runs a strategy over history with risk management applied
execution/paper_trader.py  - connects to Alpaca's free PAPER trading API
dashboard/report.py        - equity curve chart + metrics report
run_backtest_demo.py       - end-to-end demo (currently uses synthetic data)
```

## Setup (on your own machine - this sandbox has no internet)

```bash
pip install -r requirements.txt
```

1. **Get real backtest data**: in `run_backtest_demo.py`, set `USE_REAL_DATA = True`.
   This uses `yfinance` (free, no signup) to pull real historical prices.

2. **Run the backtest**:
   ```bash
   python run_backtest_demo.py
   ```
   Review the metrics: `total_return_pct`, `sharpe_ratio`, `max_drawdown_pct`, `win_rate_pct`.
   A Sharpe ratio above ~1.0 and a controlled max drawdown are the bar for "worth paper trading further" -
   most first-pass strategies will NOT clear this, and that's normal and useful information, not failure.

3. **Set up free Alpaca paper trading**:
   - Sign up at https://alpaca.markets, choose Paper Trading (no funding required)
   - Generate API keys, then:
     ```bash
     export ALPACA_API_KEY="your_key"
     export ALPACA_SECRET_KEY="your_secret"
     ```

4. **Run a paper trading cycle**:
   ```bash
   python execution/paper_trader.py
   ```
   This checks signals and places SIMULATED orders in your Alpaca paper account.
   Run it daily (e.g. via cron, once after market close) to build a track record over time.

5. **Generate a report**:
   ```bash
   python dashboard/report.py
   ```

## How to actually improve this system over time
- Change `STRATEGY` in `config.py` between `sma_crossover` and `rsi_mean_reversion`, compare metrics
- Adjust `FAST_MA`/`SLOW_MA` or `RSI_PERIOD` and re-run the backtest - avoid over-tuning to one narrow history (that's "overfitting" and it will fail on new data)
- Add new symbols to `SYMBOLS` one at a time and compare performance
- Track paper trading results for at least 4-8 weeks across varied market conditions before ever considering real capital
- Keep a simple log of what you changed and why - this is exactly the kind of before/after analysis you already do professionally

## Deploying to Render (free scheduled runs)
See the step-by-step walkthrough in chat. Short version: push this repo to GitHub, connect it
to Render as a Blueprint (it reads `render.yaml` automatically), set your Alpaca keys as env vars
in the Render dashboard (never in code), and it runs `execution/paper_trader.py` on a cron schedule
for free.

## The honest bar for "ready to consider real money" (not now)
- Positive Sharpe ratio in both backtest AND live paper trading
- Max drawdown you could genuinely stomach without panic-changing the system
- At least 30-50 completed paper trades to have any statistical meaning
- Capital you can fully afford to lose - never rent/family essentials money
