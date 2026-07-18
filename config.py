"""
Central configuration for the trading system.
Copy this file to config_local.py and fill in your real keys - never commit real keys to git.
"""

import os

# ── Data source ──────────────────────────────────────────────
# Free options: yfinance (no key needed) or Alpaca (free key, better for live data)
DATA_SOURCE = "yfinance"  # "yfinance" or "alpaca"

# ── Alpaca paper trading (sign up free at alpaca.markets) ──────
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # PAPER endpoint - do not change to live without deliberate review

# ── Universe ─────────────────────────────────────────────────
# Equities: standard tickers, works with yfinance and Alpaca out of the box.
EQUITY_SYMBOLS = ["AAPL", "MSFT", "SPY"]

# Commodities: true futures (CL=F, GC=F) need a futures broker Alpaca doesn't provide.
# The practical, broker-compatible proxy is commodity ETFs - same price exposure,
# tradable through the same equity pipeline and the same Alpaca paper account.
COMMODITY_SYMBOLS = ["GLD", "USO", "SLV"]  # Gold, Oil, Silver ETFs

# Crypto: Alpaca supports commission-free crypto paper trading directly.
# Format matters - Alpaca crypto symbols use this "BASE/QUOTE" form, yfinance uses "BASE-USD".
CRYPTO_SYMBOLS_ALPACA = ["BTC/USD", "ETH/USD"]
CRYPTO_SYMBOLS_YFINANCE = ["BTC-USD", "ETH-USD"]

# ── Curated tiers, based on first backtest results with sma_crossover ──────
# PROVEN: showed Sharpe > 0.5 and win rate near/above 50% with the trend-following strategy.
# These are the ones actually worth paper-trading live right now.
PROVEN_WITH_SMA = ["GLD", "SLV", "SPY"]

# NEEDS_DIFFERENT_STRATEGY: lost money and tripped risk halts under trend-following.
# Not necessarily bad assets - just a bad fit for THIS strategy. Test with mean-reversion
# before writing them off entirely.
NEEDS_DIFFERENT_STRATEGY = ["MSFT", "BTC-USD"]

# UNCLEAR: mixed/weak results, not yet in either bucket.
UNCLEAR = ["AAPL", "USO", "ETH-USD"]

# What actually gets backtested/traded when you run the scripts - combine as you like.
SYMBOLS = EQUITY_SYMBOLS + COMMODITY_SYMBOLS + CRYPTO_SYMBOLS_YFINANCE
ASSET_CLASS = {  # used by execution/paper_trader.py to route order format correctly
    **{s: "equity" for s in EQUITY_SYMBOLS + COMMODITY_SYMBOLS},
    **{s: "crypto" for s in CRYPTO_SYMBOLS_YFINANCE},
}

# ── Strategy parameters ─────────────────────────────────────
STRATEGY = "sma_crossover"  # default/fallback for any symbol not in STRATEGY_MAP below
FAST_MA = 10
SLOW_MA = 30
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Per-symbol strategy assignment, based on comparison testing (compare_strategies.py).
# Trend-following (SMA) suited GLD/SLV/SPY; mean-reversion (RSI) clearly suited MSFT/BTC-USD better.
# NOTE: this was decided using the same historical window it was tested on - treat this as a
# working hypothesis to validate further in paper trading, not a proven result yet.
STRATEGY_MAP = {
    "GLD": "sma_crossover",
    "SLV": "sma_crossover",
    "SPY": "sma_crossover",
    "MSFT": "rsi_mean_reversion",
    "BTC-USD": "rsi_mean_reversion",
    # AAPL, USO, ETH-USD: unclear results so far - defaults to STRATEGY above until tested further
}

# ── Risk management (this is the part that protects your capital) ──
STARTING_CAPITAL = 1000.0
MAX_RISK_PER_TRADE_PCT = 0.02      # never risk more than 2% of capital on one trade
MAX_POSITION_PCT = 0.20            # never put more than 20% of capital in one symbol
STOP_LOSS_PCT = 0.03               # exit if price moves 3% against us
TAKE_PROFIT_PCT = 0.06             # exit if price moves 6% in our favor
MAX_DAILY_LOSS_PCT = 0.05          # halt trading for the day if down 5%
MAX_DRAWDOWN_PCT = 0.15            # halt the whole system if account down 15% from peak

# ── Backtest settings ────────────────────────────────────────
BACKTEST_START = "2022-01-01"
BACKTEST_END = "2025-12-31"
COMMISSION_PCT = 0.001  # 0.1% per trade, roughly realistic for a retail broker
