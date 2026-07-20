"""
Central configuration for the trading system.
Copy this file to config_local.py and fill in your real keys - never commit real keys to git.

Tunable parameters (symbol lists, strategy assignments, risk parameters) load from
tunable_config.json - that's the ONLY file the self-improvement system is allowed to edit.
This file defines hard safety bounds that even an approved change cannot exceed.
"""

import os
import json

# ── Data source ──────────────────────────────────────────────
DATA_SOURCE = "yfinance"

# ── Alpaca paper trading (sign up free at alpaca.markets) ──────
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # PAPER endpoint - do not change to live without deliberate review

# ── Hard safety bounds - no approved change, human or automated, can exceed these ──
RISK_PARAM_BOUNDS = {
    "max_risk_per_trade_pct": (0.005, 0.05),   # 0.5% - 5% per trade, never more
    "max_position_pct": (0.05, 0.30),          # 5% - 30% max in one symbol
    "stop_loss_pct": (0.01, 0.08),             # 1% - 8%
    "take_profit_pct": (0.02, 0.15),           # 2% - 15%
    "max_daily_loss_pct": (0.02, 0.10),        # 2% - 10%
    "max_drawdown_pct": (0.05, 0.25),          # 5% - 25%
}
VALID_STRATEGIES = ["sma_crossover", "rsi_mean_reversion"]

_TUNABLE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunable_config.json")

_DEFAULT_TUNABLES = {
    "active_symbols": ["SPY", "GLD", "BTC-USD"],
    "watchlist_symbols": ["AAPL", "MSFT", "USO", "SLV", "ETH-USD"],
    "strategy_map": {
        "GLD": "sma_crossover", "SPY": "sma_crossover", "BTC-USD": "rsi_mean_reversion",
        "SLV": "sma_crossover", "MSFT": "rsi_mean_reversion", "AAPL": "sma_crossover",
        "USO": "sma_crossover", "ETH-USD": "sma_crossover",
    },
    "risk_parameters": {
        "max_risk_per_trade_pct": 0.02, "max_position_pct": 0.20, "stop_loss_pct": 0.03,
        "take_profit_pct": 0.06, "max_daily_loss_pct": 0.05, "max_drawdown_pct": 0.15,
    },
}


def _load_tunables():
    """Loads tunable_config.json, validating every value against RISK_PARAM_BOUNDS and
    VALID_STRATEGIES. Falls back to safe defaults for anything missing or out of bounds -
    a corrupted or maliciously-edited JSON file cannot push risk parameters outside
    the hard-coded safe range above."""
    try:
        with open(_TUNABLE_CONFIG_PATH) as f:
            loaded = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARNING: could not load tunable_config.json ({e}) - using safe defaults")
        return _DEFAULT_TUNABLES

    result = json.loads(json.dumps(_DEFAULT_TUNABLES))  # deep copy of defaults

    if isinstance(loaded.get("active_symbols"), list):
        result["active_symbols"] = loaded["active_symbols"]
    if isinstance(loaded.get("watchlist_symbols"), list):
        result["watchlist_symbols"] = loaded["watchlist_symbols"]

    if isinstance(loaded.get("strategy_map"), dict):
        for symbol, strategy in loaded["strategy_map"].items():
            if strategy in VALID_STRATEGIES:
                result["strategy_map"][symbol] = strategy
            else:
                print(f"WARNING: ignoring invalid strategy '{strategy}' for {symbol} in tunable_config.json")

    if isinstance(loaded.get("risk_parameters"), dict):
        for key, (lo, hi) in RISK_PARAM_BOUNDS.items():
            val = loaded["risk_parameters"].get(key)
            if isinstance(val, (int, float)) and lo <= val <= hi:
                result["risk_parameters"][key] = val
            elif val is not None:
                print(f"WARNING: {key}={val} in tunable_config.json is outside safe bounds "
                      f"({lo}-{hi}) - keeping default {result['risk_parameters'][key]}")

    return result


_tunables = _load_tunables()

# ── Universe (loaded from tunable_config.json, validated above) ────────────
ACTIVE_SYMBOLS = _tunables["active_symbols"]
WATCHLIST_SYMBOLS = _tunables["watchlist_symbols"]
STRATEGY_MAP = _tunables["strategy_map"]

EQUITY_SYMBOLS = ["AAPL", "MSFT", "SPY", "GLD", "USO", "SLV"]
CRYPTO_SYMBOLS_YFINANCE = ["BTC-USD", "ETH-USD"]
CRYPTO_SYMBOLS_ALPACA = ["BTC/USD", "ETH/USD"]

SYMBOLS = ACTIVE_SYMBOLS
ASSET_CLASS = {
    **{s: "equity" for s in EQUITY_SYMBOLS},
    **{s: "crypto" for s in CRYPTO_SYMBOLS_YFINANCE},
}
ALL_KNOWN_SYMBOLS = ACTIVE_SYMBOLS + WATCHLIST_SYMBOLS


def normalize_alpaca_symbol(alpaca_symbol):
    """
    Alpaca crypto positions/orders use "ETHUSD" style symbols; our config/data layer uses
    "ETH-USD". Converts Alpaca's format to ours so it can be matched against ALL_KNOWN_SYMBOLS,
    ACTIVE_SYMBOLS, STRATEGY_MAP, etc. Equity symbols (AAPL, SPY, ...) pass through unchanged.
    """
    if alpaca_symbol.endswith("USD") and "-" not in alpaca_symbol and "/" not in alpaca_symbol:
        base = alpaca_symbol[:-3]
        candidate = f"{base}-USD"
        if candidate in ALL_KNOWN_SYMBOLS:
            return candidate
    return alpaca_symbol


# ── Strategy parameters ─────────────────────────────────────
STRATEGY = "sma_crossover"  # default/fallback for any symbol not in STRATEGY_MAP
FAST_MA = 10
SLOW_MA = 30
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# ── Risk management (loaded from tunable_config.json, validated above) ──
STARTING_CAPITAL = 1000.0
MAX_RISK_PER_TRADE_PCT = _tunables["risk_parameters"]["max_risk_per_trade_pct"]
MAX_POSITION_PCT = _tunables["risk_parameters"]["max_position_pct"]
STOP_LOSS_PCT = _tunables["risk_parameters"]["stop_loss_pct"]
TAKE_PROFIT_PCT = _tunables["risk_parameters"]["take_profit_pct"]
MAX_DAILY_LOSS_PCT = _tunables["risk_parameters"]["max_daily_loss_pct"]
MAX_DRAWDOWN_PCT = _tunables["risk_parameters"]["max_drawdown_pct"]

# ── Backtest settings ────────────────────────────────────────
BACKTEST_START = "2022-01-01"
BACKTEST_END = "2025-12-31"
COMMISSION_PCT = 0.001
