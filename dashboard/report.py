"""
Generates an HTML risk + performance report from a backtest result:
equity curve, drawdown vs risk limit, trade log, and risk management summary.
Risk management is treated as a first-class part of this report, not an afterthought -
the whole point of this system is that risk controls are visible and auditable.

Run locally after run_backtest_demo.py, or import generate_report() directly.
    pip install matplotlib pandas
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_report(result: dict, symbol: str, output_dir: str = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    equity_df = result["equity_curve"]
    metrics = result["metrics"]
    risk_limits = result.get("risk_limits", {})
    halt_events = result.get("halt_events", None)

    if output_dir is None:
        output_dir = "/home/claude/trading_system/logs"
    os.makedirs(output_dir, exist_ok=True)

    # ── Chart 1: Equity curve ──
    # ── Chart 2: Drawdown vs the max-drawdown risk limit (this is the risk visibility part) ──
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1]})

    ax1.plot(equity_df.index, equity_df["equity"], linewidth=1.5, color="#2563eb", label="Equity")
    ax1.plot(equity_df.index, equity_df["peak_equity"], linewidth=1, color="#94a3b8",
              linestyle="--", label="Peak equity")
    ax1.axhline(metrics["starting_capital"], linestyle=":", alpha=0.5, color="gray",
                label="Starting capital")

    if halt_events is not None and not halt_events.empty:
        ax1.scatter(halt_events["date"], halt_events["equity"], color="#dc2626",
                    zorder=5, s=60, marker="v", label="Risk halt triggered")

    ax1.set_title(f"{symbol} — Equity Curve & Risk Halts")
    ax1.set_ylabel("Account Equity ($)")
    ax1.legend(loc="best", fontsize=8)

    max_dd_limit = risk_limits.get("max_drawdown_pct", None)
    ax2.fill_between(equity_df.index, equity_df["drawdown_pct"], 0,
                      color="#dc2626", alpha=0.3)
    ax2.plot(equity_df.index, equity_df["drawdown_pct"], color="#dc2626", linewidth=1)
    if max_dd_limit is not None:
        ax2.axhline(max_dd_limit, color="#7f1d1d", linestyle="--", linewidth=1.2,
                    label=f"Max drawdown limit ({max_dd_limit:.1f}%)")
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="best", fontsize=8)
    ax2.invert_yaxis()  # drawdown grows downward visually

    fig.tight_layout()
    chart_path = os.path.join(output_dir, f"{symbol}_risk_report.png")
    fig.savefig(chart_path, dpi=120)
    plt.close(fig)
    print(f"Saved chart: {chart_path}")

    # ── Console summary ──
    print(f"\n{'='*50}\n{symbol} — PERFORMANCE\n{'='*50}")
    for k in ["starting_capital", "final_equity", "total_return_pct", "sharpe_ratio", "num_trades", "win_rate_pct"]:
        if k in metrics:
            print(f"  {k}: {metrics[k]}")

    print(f"\n{'='*50}\n{symbol} — RISK MANAGEMENT\n{'='*50}")
    print("  Configured limits:")
    for k, v in risk_limits.items():
        print(f"    {k}: {v}%")
    print("  Observed during backtest:")
    print(f"    max_drawdown_pct: {metrics.get('max_drawdown_pct')}")
    print(f"    stop_loss_exits: {metrics.get('stop_loss_exits')}")
    print(f"    take_profit_exits: {metrics.get('take_profit_exits')}")
    print(f"    risk_halts_triggered: {metrics.get('risk_halts_triggered')}")

    if halt_events is not None and not halt_events.empty:
        print("\n  Halt events:")
        for _, ev in halt_events.iterrows():
            print(f"    {ev['date'].date()}: {ev['reason']} (equity ${ev['equity']:.2f})")

    return chart_path


if __name__ == "__main__":
    import config
    from data.fetcher import generate_synthetic
    from strategies.signals import STRATEGIES
    from backtest.engine import run_backtest

    df = generate_synthetic("DEMO", days=500)
    strategy_fn = STRATEGIES[config.STRATEGY]
    df = strategy_fn(df, config.FAST_MA, config.SLOW_MA)
    result = run_backtest(df, config, commission_pct=config.COMMISSION_PCT)
    generate_report(result, "DEMO")
