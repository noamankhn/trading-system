# Roadmap / Task Tracker

## Self-improvement system (added 2026-07-20)
Automated analysis → human-approved → auto-applied pipeline. Safety design:
- `tunable_config.json` is the ONLY file automated changes ever touch - never Python source
- `config.py` validates every value against hard-coded bounds on load (RISK_PARAM_BOUNDS) -
  even a corrupted/malicious JSON file can't push risk parameters outside safe ranges
- Only 3 proposal types exist: demote_to_watchlist, promote_to_active, adjust_risk_parameter -
  nothing else can be generated or applied, regardless of what any AI model suggests
- Nothing is ever applied without a human manually setting "approved": true and pushing

**How it works:**
1. `improvement/analyzer.py` runs weekly (GitHub Actions) - compares walk-forward evidence
   against current active/watchlist status, writes findings to `improvement_proposals.json`
2. `improvement/council.py` (optional) - if `OPENROUTER_API_KEY` is set, gets independent
   opinions from multiple frontier models + a judge consensus, added to each proposal for
   your reading. Costs real money per run via OpenRouter - entirely optional.
3. **You review `improvement_proposals.json`**, set `"approved": true` on what you agree
   with, and push
4. `improvement/apply_approved.py` runs automatically on that push - applies only approved,
   unapplied proposals to `tunable_config.json`, commits, done

**Calibration check (runs every cycle, between structural checks and proposal writing):**
`improvement/calibration.py` compares LIVE trade-level win rate against what the backtest
predicted, for each active symbol with enough real trades (5+) to judge. This catches drift
early - "live results don't match what we expected right now" - separately from the
demote/promote checks, which only look at historical walk-forward evidence. Calibration
findings (`calibration_drift`) are informational only: they're never in PROPOSAL_TYPES,
so apply_approved.py will never act on one even if accidentally approved (tested).

**To set up the optional AI council:** get an API key at openrouter.ai, add it as a GitHub
repo secret named `OPENROUTER_API_KEY`. Without it, the pipeline works identically minus
the multi-model review step.

## Decision log
- **2026-07-18: Reduced live trading universe from 8 symbols to 3**, based on walk_forward.py
  results (4 rolling 6-month out-of-sample windows per symbol on real historical data).
  Active: SPY, GLD, BTC-USD (consistent evidence across multiple periods).
  Paused to watchlist: AAPL, MSFT, USO, SLV, ETH-USD (inconsistent/weak evidence - one good
  backtest number doesn't mean a real edge). Rationale: trade fewer things well-evidenced
  rather than many things with unclear evidence. Watchlist symbols keep a STRATEGY_MAP entry
  for continued backtesting/research but are not risking real (paper) capital right now.

## In progress
- [ ] **Deploy paper trading to Render** - cron job + dashboard, so it runs daily without manual intervention
- [ ] Confirm first few automated daily cycles run correctly (check Alpaca Positions + dashboard)

## Next: Strategy expansion research (queued, start once paper trading is live and stable)
Goal: search a wider space to find stronger "winners" than the current 2-strategy setup, using the
now-corrected win/loss ratio and profit factor metrics as the real evaluation criteria - not just returns.

Planned dimensions to test:
- [ ] **More strategies** beyond SMA crossover / RSI mean-reversion - e.g. MACD, Bollinger Bands,
      breakout/channel strategies, volume-weighted signals
- [ ] **More timeframes** - current system is daily bars only; test weekly bars (less noise, fewer
      false signals) as a comparison point (NOT intraday - see earlier discussion on why that's a
      bigger, separate project)
- [ ] **Parameter sweeps** - test ranges of FAST_MA/SLOW_MA, RSI_PERIOD/thresholds instead of single
      fixed values, to see which parameter zones are robust vs. lucky
- [ ] **Position sizing / risk parameter variations** - test different MAX_RISK_PER_TRADE_PCT,
      STOP_LOSS_PCT, TAKE_PROFIT_PCT combinations, not just the strategy signal itself
- [ ] **Wider symbol universe** - test more equities/commodities/crypto beyond the current 8, to find
      assets that suit these strategies better

## Important discipline for this research phase (to avoid fooling ourselves)
- Split data into a training window and a held-out test window - only trust results that hold up
  on data NOT used to pick the winning parameters (avoids overfitting/curve-fitting)
- Judge candidates on profit factor + win/loss ratio + Sharpe together, not total return alone
- Any new "winner" found this way still needs its own weeks of paper-trading validation before
  being trusted - a good backtest is a hypothesis, not proof

## Revisit
- [ ] Once paper trading has run for ~1-2 weeks AND strategy expansion research has produced
      candidates, revisit the "can this become a full-time income" conversation with real data
      from both sides
