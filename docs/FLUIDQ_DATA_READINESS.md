# FLUID-Q data readiness and recovery plan

**Status date:** 2026-10-11  
**Branch:** `v1.2-factor-attribution`  
**Locked evaluation window:** 2026-09-01 through 2027-08-31 — do not use for tuning or factor selection.

## Current observed blockers

1. **Broad historical price-feed coverage holes.** The finalized raw artifact has 2,187,355 rows across 1,037 requested symbols. A scan of consecutive NSE market dates found 709 internal gap spans of at least 10 sessions, containing 42,741 requested-symbol/date pairs over 2,892 unique dates. That is a candidate set for source verification, not proof that every pair should have traded. Some absences may be genuine suspensions or no-trade days.
2. **IBVENTURES is a source omission, not an evidenced EQ suspension.** The raw file jumps from 2018-06-14/28 (depending on whether the diagnostic is based on raw requested rows or the strategy panel) to 2018-10-30. NSE-hosted corporate material records fully paid IBVENTURES ordinary-share trading in August 2018. The July 2018 suspension circular applies to the separate partly-paid `E1` series, not ordinary fully paid `EQ`. Never fill the interval with invented prices.
3. **Corporate-action adjustment is incomplete.** The existing adjustment artifact reports 19 extreme events with no matching adjusted row and 15 continuity-relevant adjusted moves over 50%. This requires issuer/date-level reconciliation.
4. **Dividends are not incorporated.** `apply_verified_adjustments.py` labels the output `dividend_adjustment=not_applied`. Any return numbers from it are split/bonus-adjusted price returns, not total returns; the strategy cannot be promoted on these figures.
5. **Historical index-membership provenance needs a separate audit.** The membership snapshot contains 529 `snapshot_floor` rows out of 1,140 interval rows and 959 symbols. Verify those inferred starting intervals against dated official index notices before treating the entire 2014–2026 history as fully point-in-time and survivorship-bias-safe.
6. **The previous CI architecture repeated the same failure.** Research workflows consumed fixed historic price-integrity run IDs and started on code pushes. They could rerun expensive analyses against a stale artifact, fail at the same IBVENTURES return, and still produce no joined diagnosis.
7. **A green workflow was mistaken for validated inputs.** Basic OHLC / duplicate checks can pass while historical security/date rows are absent. Repair success and dataset readiness must be separate, explicit gates.

## Recovery design now implemented

- `scripts/repair_price_gaps_bhavcopy.py` discovers long internal gaps and queries the official daily NSE bhavcopy once per affected date. It inserts only exact `EQ` rows present in the source.
- If the official daily archive was successfully parsed but contains no `EQ` row for a candidate symbol/date, the pair is recorded in `data/input/verified_no_trade_dates.csv`. This is evidence about the absence of a quoted trade, **not** a price row. Failed archive requests are explicitly unresolved and never counted as no-trade.
- `scripts/audit_price_gap_readiness.py` reconciles candidate pairs, archive failures, raw observations and the no-trade ledger. It also reports corporate-action/total-return blockers separately so a raw-gap pass is not mistaken for full research approval.
- `scripts/run_fluidq_backtest.py` retains the strict held-return error. It can carry forward a last-close mark across long gaps only when each such date is covered by the official no-trade ledger. The next actual quote still captures the cumulative move; no synthetic raw prices are inserted.
- The targeted repair workflow uploads a diagnostic artifact even when readiness is blocked. It publishes a research-input artifact only after the price-gap gate and adjustment build succeed.
- Factor attribution, factor compression, robustness, economic-gate, walk-forward and factor-diagnostics workflows now require an explicit integrity run ID, check the readiness report, and are manual-dispatch only. They no longer re-run automatically on every engine/workflow push or fall back silently to old run IDs.
- The general full-history research workflow now runs the broad daily-bhavcopy repair and includes the no-trade ledger/readiness report in its artifact.

## Release gates

### Gate A — source completeness
- No failed bhavcopy dates in the repair report.
- Every targeted long-gap pair is either backed by a raw NSE EQ observation, confirmed absent from a successfully parsed official daily EQ archive, or explicitly recorded as an unresolved exception.
- No row is fabricated, and the raw `EQ` series remains separate from E1/other series.
- The strict missing-held-return check remains enabled.

### Gate B — corporate actions
- Reconcile remaining large adjusted returns at the individual symbol/ex-date level, including splits, bonuses, rights, demergers, mergers and other capital restructurings.
- Missing adjusted rows must be explained or resolved.
- Dividends must be handled through a sourced total-return methodology before describing results as total return. Until then, all results are clearly labeled price-return-only and provisional.

### Gate C — universe integrity
- Validate historical Nifty 500 effective-from/effective-to intervals, symbol rename lineages and listing/delisting dates against dated primary records.
- Investigate `snapshot_floor` intervals rather than automatically assuming each is correct.
- Test survivorship/look-ahead controls, stale values, duplicate canonical issuer/date pairs, missing membership-price joins, and only-traded-EQ series.

### Gate D — research execution
- Only launch research with an explicit artifact run ID whose readiness report has `price_gap_integrity=PASS`.
- Preserve fixed monthly rebalance/execution timing, transaction-cost sensitivity and the strict held-return assertion.
- Keep the locked 2026-09-01–2027-08-31 evaluation window out of all tuning and candidate selection.
- Treat transaction costs as estimates and evaluate liquidity/slippage sensitivity separately.

## Status interpretation

- **PASS_PRICE_GAPS** means the targeted long-gap repair was reconciled against daily source files. It does not certify membership quality, a complete split/bonus history, dividend adjustment, or investment readiness.
- **PROVISIONAL price-return research** can help test plumbing and exploratory factor behavior once the gap gate passes.
- **Total-return readiness remains BLOCKED** until dividend treatment and corporate-action continuity are established. Do not claim production-grade results before then.
