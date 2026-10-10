# FLUID-Q economic-validity gate

## Current decision

**Promotion status: BLOCKED.** The current adjusted price series is a split/bonus-adjusted research proxy, not a verified total-return series. The adjustment pipeline explicitly records `dividend_adjustment=not_applied`. Performance statistics must not be represented as dividend-inclusive investor returns.

## Required gates

1. **Return-series integrity:** reconcile all material splits, bonuses, demergers, symbol transitions and missing/duplicate prices. Add dividend reinvestment/total-return treatment before interpreting long-run CAGR as investable performance.
2. **Execution economics:** compare the baseline first-session execution convention with one- and two-additional-session delays, at 0.15%, 0.30% and 0.50% transaction-cost assumptions. The cost parameter is applied to the existing one-way turnover estimate; it does not cover every tax, fee, spread, impact or liquidity effect.
3. **Untouched holdout:** lock 2026-09-01 through 2027-08-31 as a future evaluation period. Existing research inputs must end before 2026-09-01. Do not use holdout returns to tune factors, rebalance cadence, cost assumptions or candidate selection before the evaluation window is closed.
4. **Promotion standard:** the economic gate is separate from factor-selection significance. The selection-replay bootstrap currently does not establish that adaptive consensus adds value over the fixed baseline.

## Interpretation

GitHub Actions success means the diagnostic completed and its artifacts were generated. It does **not** mean FLUID-Q passed the investment-promotion gate. Keep the adaptive consensus research-only until the return series and holdout requirements are satisfied.
