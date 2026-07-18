"""
Paper trading connector using Alpaca's free paper-trading API via the official alpaca-py SDK.
This trades SIMULATED money only - paper=True below is what enforces that.

Setup (run on your own machine, needs internet):
    1. Sign up free at https://alpaca.markets (choose "Paper Trading", no funding needed)
    2. Generate an API key/secret from Paper Accounts -> Manage Accounts in the dashboard
    3. pip install alpaca-py pandas numpy yfinance
    4. Set environment variables:
         Windows:  setx ALPACA_API_KEY "your_key"   (open a NEW terminal after this)
                   setx ALPACA_SECRET_KEY "your_secret"
         Mac/Linux: export ALPACA_API_KEY="your_key"
                    export ALPACA_SECRET_KEY="your_secret"
    5. python execution/paper_trader.py

DO NOT set paper=False below until:
  - You've paper-traded for at least several weeks across different market conditions
  - You've reviewed the results with clear eyes about win rate, drawdown, and whether
    the strategy actually has an edge after commissions/slippage
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from data.fetcher import fetch_recent
from strategies.signals import STRATEGIES
from risk.manager import RiskManager


def get_alpaca_client():
    from alpaca.trading.client import TradingClient

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise EnvironmentError(
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables first. "
            "Get free paper trading keys at https://alpaca.markets"
        )

    # paper=True is the safety switch - this must stay True until real-money trading
    # is a deliberate, reviewed decision, not an accident.
    return TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)


def run_paper_trading_cycle():
    """
    One evaluation cycle: pull recent data, compute signal, place/close paper orders.
    Intended to be run on a schedule (e.g. once per day after market close, or via cron).
    """
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.common.exceptions import APIError

    client = get_alpaca_client()
    account = client.get_account()
    print(f"Alpaca paper account equity: ${float(account.equity):,.2f} (sandbox balance - not used for sizing)")
    print(f"Risk sizing based on configured capital: ${config.STARTING_CAPITAL:,.2f}\n")

    risk = RiskManager(
        starting_capital=config.STARTING_CAPITAL,  # deliberately NOT account.equity -
        # Alpaca paper accounts default to $100k and resetting that isn't exposed simply in
        # the UI. Sizing off a fixed $1,000 config value keeps this an honest test of your
        # real intended capital regardless of what the sandbox account balance shows.
        max_risk_per_trade_pct=config.MAX_RISK_PER_TRADE_PCT,
        max_position_pct=config.MAX_POSITION_PCT,
        stop_loss_pct=config.STOP_LOSS_PCT,
        take_profit_pct=config.TAKE_PROFIT_PCT,
        max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT,
        max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
    )

    for symbol in config.SYMBOLS:
        asset_class = config.ASSET_CLASS.get(symbol, "equity")
        # Alpaca wants "BTC/USD" for crypto orders even though yfinance data uses "BTC-USD"
        order_symbol = symbol.replace("-USD", "/USD") if asset_class == "crypto" else symbol

        strategy_name = config.STRATEGY_MAP.get(symbol, config.STRATEGY)
        strategy_fn = STRATEGIES[strategy_name]

        df = fetch_recent(symbol, lookback_days=90)
        if strategy_name == "sma_crossover":
            df = strategy_fn(df, config.FAST_MA, config.SLOW_MA)
        else:
            df = strategy_fn(df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)

        latest = df.iloc[-1]
        price = latest["Close"]
        want_long = latest["position"] == 1

        try:
            current_position = client.get_open_position(order_symbol)
            currently_long = float(current_position.qty) > 0
        except APIError:
            currently_long = False  # no open position for this symbol

        print(f"{symbol} [{asset_class}, {strategy_name}]: price=${price:.2f} "
              f"want_long={want_long} currently_long={currently_long}")

        if want_long and not currently_long:
            if asset_class == "crypto":
                # crypto supports fractional sizing - use dollar-based risk sizing directly
                risk_dollars = risk.state.capital * risk.max_risk_per_trade_pct
                qty = round(risk_dollars / price, 6)
                time_in_force = TimeInForce.GTC  # crypto doesn't support DAY orders on Alpaca
            else:
                qty = risk.position_size(price)  # fractional - matches Alpaca's fractional share orders
                time_in_force = TimeInForce.DAY

            if qty > 0:
                order = MarketOrderRequest(
                    symbol=order_symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=time_in_force,
                )
                client.submit_order(order)
                print(f"  -> BUY {qty} of {order_symbol} (paper)")

        elif not want_long and currently_long:
            client.close_position(order_symbol)
            print(f"  -> CLOSE position in {order_symbol} (paper)")


if __name__ == "__main__":
    run_paper_trading_cycle()
