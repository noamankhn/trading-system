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
# Updated 2026-07-18 based on walk_forward.py results (4 rolling 6-month out-of-sample
# windows per symbol, real historical data). Decision rule: trade live only what showed
# consistent evidence across MULTIPLE windows, not just one favorable backtest period.

# ACTIVE: profitable in most/all walk-forward windows with reasonable consistency
# (low Sharpe standard deviation across windows) - these are what actually gets traded live.
#   SPY:     4/4 windows profitable, avg Sharpe 1.23, very consistent (std 0.18)
#   BTC-USD: 4/4 windows profitable, avg Sharpe 0.70, consistent (std 0.33)
#   GLD:     3/4 windows profitable, avg Sharpe 0.85, but one clearly bad window - included
#            with caution, revisit if the pattern continues
ACTIVE_SYMBOLS = ["SPY", "GLD", "BTC-USD"]

# WATCHLIST: paused from live trading - inconsistent or weak walk-forward evidence.
# Still tracked in research/backtesting, NOT traded with real risk until they show
# consistent evidence the way SPY/BTC-USD/GLD did.
#   AAPL:    1/4 windows profitable, negative avg Sharpe - no real edge shown
#   MSFT:    2/4 windows profitable, ~flat avg Sharpe - coin-flip, not edge
#   USO:     2/4 windows profitable, weak avg Sharpe - inconsistent
#   SLV:     2/4 windows profitable, weak avg Sharpe - inconsistent
#   ETH-USD: 3/4 windows profitable but one window lost -5.3% with Sharpe -2.58 -
#            one bad period did real damage to an otherwise-decent average
WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "USO", "SLV", "ETH-USD"]

EQUITY_SYMBOLS = ["AAPL", "MSFT", "SPY", "GLD", "USO", "SLV"]
CRYPTO_SYMBOLS_YFINANCE = ["BTC-USD", "ETH-USD"]
CRYPTO_SYMBOLS_ALPACA = ["BTC/USD", "ETH/USD"]

# What actually gets traded live and shown on the dashboard - the vetted set only.
SYMBOLS = ACTIVE_SYMBOLS
ASSET_CLASS = {  # used by execution/paper_trader.py to route order format correctly
    **{s: "equity" for s in EQUITY_SYMBOLS},
    **{s: "crypto" for s in CRYPTO_SYMBOLS_YFINANCE},
}

# ── Curated tiers (kept for reference/backtesting scripts like compare_strategies.py) ──
PROVEN_WITH_SMA = ["GLD", "SPY"]
NEEDS_DIFFERENT_STRATEGY = ["MSFT", "BTC-USD"]
UNCLEAR = ["AAPL", "USO", "SLV", "ETH-USD"]

# ── Strategy parameters ─────────────────────────────────────
STRATEGY = "sma_crossover"  # default/fallback for any symbol not in STRATEGY_MAP below
FAST_MA = 10
SLOW_MA = 30
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Per-symbol strategy assignment. GLD/SPY use trend-following (SMA); BTC-USD uses
# mean-reversion (RSI) - both confirmed by walk_forward.py across multiple out-of-sample
# periods, not just one backtest window. Watchlist symbols keep a mapping for research/
# backtesting purposes even though they're not actively traded right now.
STRATEGY_MAP = {
    "GLD": "sma_crossover",
    "SPY": "sma_crossover",
    "BTC-USD": "rsi_mean_reversion",
    "SLV": "sma_crossover",
    "MSFT": "rsi_mean_reversion",
    "AAPL": "sma_crossover",
    "USO": "sma_crossover",
    "ETH-USD": "sma_crossover",
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
