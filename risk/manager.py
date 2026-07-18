"""
Risk management layer - this is the part that actually protects capital.
A strategy with a great win rate can still blow up an account without this layer.
"""

from dataclasses import dataclass


@dataclass
class RiskState:
    capital: float
    peak_capital: float
    daily_start_capital: float
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self, starting_capital: float, max_risk_per_trade_pct: float,
                 max_position_pct: float, stop_loss_pct: float, take_profit_pct: float,
                 max_daily_loss_pct: float, max_drawdown_pct: float):
        self.state = RiskState(
            capital=starting_capital,
            peak_capital=starting_capital,
            daily_start_capital=starting_capital,
        )
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct

    def position_size(self, price: float) -> float:
        """
        Returns number of shares (fractional) to buy given current capital and risk limits.
        Sizes the position so that a stop-loss hit only costs max_risk_per_trade_pct of capital.

        Uses fractional shares deliberately: with small accounts, integer-share rounding
        can silently round a valid position down to 0 for higher-priced assets (e.g. a $200
        cap ÷ a $480 stock = 0.4 shares -> truncates to 0 -> the strategy can never trade it).
        Alpaca supports fractional/notional share orders, so this matches real execution.
        """
        if self.state.halted:
            return 0.0

        risk_dollars = self.state.capital * self.max_risk_per_trade_pct
        loss_per_share = price * self.stop_loss_pct
        shares_by_risk = (risk_dollars / loss_per_share) if loss_per_share > 0 else 0.0

        max_position_dollars = self.state.capital * self.max_position_pct
        shares_by_cap = (max_position_dollars / price) if price > 0 else 0.0

        shares = max(0.0, min(shares_by_risk, shares_by_cap))
        return round(shares, 6)

    def update_capital(self, new_capital: float):
        self.state.capital = new_capital
        self.state.peak_capital = max(self.state.peak_capital, new_capital)
        self._check_halts()

    def new_day(self):
        self.state.daily_start_capital = self.state.capital
        self.state.halted = False
        self.state.halt_reason = ""

    def _check_halts(self):
        drawdown = (self.state.peak_capital - self.state.capital) / self.state.peak_capital
        if drawdown >= self.max_drawdown_pct:
            self.state.halted = True
            self.state.halt_reason = f"Max drawdown hit: {drawdown:.1%}"
            return

        daily_loss = (self.state.daily_start_capital - self.state.capital) / self.state.daily_start_capital
        if daily_loss >= self.max_daily_loss_pct:
            self.state.halted = True
            self.state.halt_reason = f"Max daily loss hit: {daily_loss:.1%}"
