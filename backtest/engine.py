"""
Backtest engine. Runs a strategy over historical data with the SAME risk-management
logic that paper/live trading will use, and reports the numbers that actually matter:
win rate, max drawdown, Sharpe ratio - not just "total return," which can be misleading.
"""

import pandas as pd
import numpy as np

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.manager import RiskManager


def run_backtest(df: pd.DataFrame, config, commission_pct: float = 0.001) -> dict:
    """
    df must already have a 'position' column (0 or 1) from a strategy function.
    Returns a results dict with the equity curve and performance metrics.
    """
    risk = RiskManager(
        starting_capital=config.STARTING_CAPITAL,
        max_risk_per_trade_pct=config.MAX_RISK_PER_TRADE_PCT,
        max_position_pct=config.MAX_POSITION_PCT,
        stop_loss_pct=config.STOP_LOSS_PCT,
        take_profit_pct=config.TAKE_PROFIT_PCT,
        max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT,
        max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
    )

    cash = config.STARTING_CAPITAL
    shares_held = 0
    entry_price = 0.0
    equity_curve = []
    trades = []
    halt_events = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        price = row["Close"]

        # mark-to-market equity
        equity = cash + shares_held * price
        was_halted = risk.state.halted
        risk.update_capital(equity)

        current_drawdown_pct = ((risk.state.peak_capital - equity) / risk.state.peak_capital) * 100

        equity_curve.append({
            "date": df.index[i],
            "equity": equity,
            "peak_equity": risk.state.peak_capital,
            "drawdown_pct": current_drawdown_pct,
            "halted": risk.state.halted,
        })

        if risk.state.halted and not was_halted:
            halt_events.append({"date": df.index[i], "reason": risk.state.halt_reason,
                                 "equity": equity})

        if risk.state.halted:
            # if halted, flatten any position and stop trading
            if shares_held > 0:
                cash += shares_held * price * (1 - commission_pct)
                trades.append({"date": df.index[i], "action": "HALT_EXIT",
                                "price": price, "shares": shares_held})
                shares_held = 0
            continue

        want_long = row["position"] == 1
        currently_long = shares_held > 0

        # stop-loss / take-profit check first
        if currently_long:
            change = (price - entry_price) / entry_price
            if change <= -risk.stop_loss_pct or change >= risk.take_profit_pct:
                proceeds = shares_held * price * (1 - commission_pct)
                cash += proceeds
                trades.append({"date": df.index[i], "action": "EXIT",
                                "price": price, "shares": shares_held, "pnl_pct": change,
                                "pnl_dollars": proceeds - (shares_held * entry_price)})
                shares_held = 0
                currently_long = False

        if want_long and not currently_long:
            size = risk.position_size(price)
            cost = size * price * (1 + commission_pct)
            if size > 0 and cost <= cash:
                cash -= cost
                shares_held = size
                entry_price = price
                trades.append({"date": df.index[i], "action": "BUY",
                                "price": price, "shares": size})

        elif not want_long and currently_long:
            change = (price - entry_price) / entry_price
            proceeds = shares_held * price * (1 - commission_pct)
            cash += proceeds
            trades.append({"date": df.index[i], "action": "SELL",
                            "price": price, "shares": shares_held,
                            "pnl_pct": change, "pnl_dollars": proceeds - (shares_held * entry_price)})
            shares_held = 0

    equity_df = pd.DataFrame(equity_curve).set_index("date")
    trades_df = pd.DataFrame(trades)
    halts_df = pd.DataFrame(halt_events)

    return {
        "equity_curve": equity_df,
        "trades": trades_df,
        "halt_events": halts_df,
        "risk_limits": {
            "max_risk_per_trade_pct": config.MAX_RISK_PER_TRADE_PCT * 100,
            "max_position_pct": config.MAX_POSITION_PCT * 100,
            "stop_loss_pct": config.STOP_LOSS_PCT * 100,
            "take_profit_pct": config.TAKE_PROFIT_PCT * 100,
            "max_daily_loss_pct": config.MAX_DAILY_LOSS_PCT * 100,
            "max_drawdown_pct": config.MAX_DRAWDOWN_PCT * 100,
        },
        "metrics": _compute_metrics(equity_df, trades_df, config.STARTING_CAPITAL, halts_df),
    }


def _compute_metrics(equity_df: pd.DataFrame, trades_df: pd.DataFrame, starting_capital: float,
                      halts_df: pd.DataFrame = None) -> dict:
    if equity_df.empty:
        return {}

    final_equity = equity_df["equity"].iloc[-1]
    total_return_pct = (final_equity - starting_capital) / starting_capital

    daily_returns = equity_df["equity"].pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)
              if daily_returns.std() > 0 else 0)

    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    max_drawdown = drawdown.min()

    exits = trades_df[trades_df["action"].isin(["EXIT", "SELL", "HALT_EXIT"])] if not trades_df.empty else pd.DataFrame()
    win_rate = None
    if not exits.empty and "pnl_pct" in exits.columns:
        priced = exits[exits["pnl_pct"].notna()]
        wins = (priced["pnl_pct"] > 0).sum()
        total = len(priced)
        win_rate = wins / total if total > 0 else None

    stop_loss_hits = 0
    take_profit_hits = 0
    if not exits.empty and "pnl_pct" in exits.columns:
        priced_exits = exits[exits["pnl_pct"].notna()]
        stop_loss_hits = int((priced_exits["pnl_pct"] <= 0).sum())
        take_profit_hits = int((priced_exits["pnl_pct"] > 0).sum())

    # Win/loss ratio (payoff ratio): average $ size of a winning trade vs average $ size of a
    # losing trade. This is DIFFERENT from win rate - a strategy can win rarely but still be
    # profitable if wins are much bigger than losses, or vice versa.
    avg_win_dollars = None
    avg_loss_dollars = None
    win_loss_ratio = None
    profit_factor = None
    if not exits.empty and "pnl_dollars" in exits.columns:
        priced_dollars = exits[exits["pnl_dollars"].notna()]
        winning_trades = priced_dollars[priced_dollars["pnl_dollars"] > 0]["pnl_dollars"]
        losing_trades = priced_dollars[priced_dollars["pnl_dollars"] <= 0]["pnl_dollars"]

        if len(winning_trades) > 0:
            avg_win_dollars = winning_trades.mean()
        if len(losing_trades) > 0:
            avg_loss_dollars = abs(losing_trades.mean())

        if avg_win_dollars is not None and avg_loss_dollars is not None and avg_loss_dollars > 0:
            win_loss_ratio = avg_win_dollars / avg_loss_dollars

        total_wins_dollars = winning_trades.sum() if len(winning_trades) > 0 else 0
        total_losses_dollars = abs(losing_trades.sum()) if len(losing_trades) > 0 else 0
        if total_losses_dollars > 0:
            profit_factor = total_wins_dollars / total_losses_dollars

    num_halts = len(halts_df) if halts_df is not None and not halts_df.empty else 0

    return {
        "starting_capital": starting_capital,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "num_trades": len(trades_df),
        "win_rate_pct": round(win_rate * 100, 2) if win_rate is not None else "n/a",
        "avg_win_dollars": round(avg_win_dollars, 2) if avg_win_dollars is not None else "n/a",
        "avg_loss_dollars": round(avg_loss_dollars, 2) if avg_loss_dollars is not None else "n/a",
        "win_loss_ratio": round(win_loss_ratio, 2) if win_loss_ratio is not None else "n/a",
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else "n/a",
        "stop_loss_exits": stop_loss_hits,
        "take_profit_exits": take_profit_hits,
        "risk_halts_triggered": num_halts,
    }
