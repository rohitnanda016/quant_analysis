# FLUID-Q data readiness and recovery plan

**Status date:** 2026-10-13  
**Branch:** `v1.2-factor-attribution`  
**Locked evaluation window:** 2026-09-01 through 2027-08-31 — do not use for tuning or factor selection.

## Current observed blockers

1. **Broad historical price-feed coverage holes.** The finalized raw artifact has 2,187,355 rows across 1,037 requested symbols. A scan of consecutive NSE market dates found 709 internal gap spans of at least 10 sessions, containing 42,741 requested-symbol/date pairs over 2,892 unique dates. That is a candidate set for source verification, not proof that every pair should have traded. Some absences may be genuine suspensions or no-trade days.
2. **IBVENTURES is a source omission, not an evidenced EQ suspension.** The raw strategy series jumps from the last valid close on 2018-06-28 (₹498.55) to the next observation on 2018-10-30 (₹414.05). NSE-hosted corporate material records fully paid IBVENTURES ordinary-share trading in August 2018. The July 2018 suspension circular applies to the separate partly-paid `E1` series, not ordinary fully paid `EQ`. Never fill the interval with invented prices.
3. **Corporate-action adjustment is incomplete.** The existing adjustment artifact reports 19 extreme events with no matching adjusted row and 15 continuity-relevant adjusted moves over 50%. This requires issuer/date-level reconciliation.
4. **Dividends are not incorporated.** `apply_verified_adjustments.py` labels the output `dividend_adjustment=not_applied`. Any return numbers from it are split/bonus-adjusted price returns, not total returns; the strategy cannot be promoted on these figures.
5. **Historical index-membership provenance needs a separate audit.** The membership snapshot contains 529 `snapshot_floor` rows out of 1,140 interval rows and 959 symbols. Verify those inferred starting intervals against dated official index notices before treating the entire 2014–2026 history as fully point-in-time and survivorship-bias-safe.
6. **The previous CI architecture repeated the same failure.** Research workflows consumed fixed historic price-integrity run IDs and started on code pushes. They could rerun expensive analyses against a stale artifact, fail at the same IBVENTURES return, and still produce no joined diagnosis.
7. **A green workflow was mistaken for validated inputs.** Basic OHLC / duplicate checks can pass while historical security/date rows are absent. Repair success and dataset readiness must be separate, explicit gates.

## Recovery design now implemented

- `scripts/repair_price_gaps_bhavcopy.py` now scopes long-gap repair to dated historical Nifty 500 membership intervals plus a 252-session warm-up for the momentum/200-DMA features. The exact date/symbol target inventory is fingerprinted in the checkpoint; a stale inventory cannot be resumed silently.
- The repair prefers actual `EQ` quotes and can preserve actual NSE `BE`/`BZ` closes as alternate-series price observations when no `EQ` close exists. Original series labels are retained; no `BE`/`BZ` row is relabelled as `EQ`. A symbol/date with no usable EQ/BE/BZ price row remains unresolved unless the no-trade/suspension case has independent evidence and explicit approval.
- Failed archive dates are recorded as fetch errors and as attempted dates. The batch chain moves forward rather than repeatedly retrying the same failed day forever; final readiness still blocks unresolved errors.
- `scripts/audit_price_quality.py` parses mixed historical date formats, counts invalid dates separately, and does not count all `SYMBOL|NaT` rows as duplicate observations. Series counts are aggregated across the full file.
- `scripts/audit_price_gap_readiness.py` reconciles the in-scope candidate pairs, actual EQ/BE/BZ observations, explicit no-trade evidence, archive errors and raw quality. It reports corporate-action/total-return blockers separately; a price-gap pass is not full research approval.
- `scripts/run_fluidq_backtest.py` now recognizes `valid_from`/`valid_to` membership intervals as well as dated review snapshots, and refuses an undated membership input rather than silently disabling the universe filter. Its price panel can use actual EQ/BE/BZ closes for continuity, but new rebalance selections remain limited to EQ. The strict missing-held-return error is retained.
- The targeted repair workflow is manual-dispatch only; ordinary code pushes no longer enqueue a full historical repair. It uploads diagnostics when readiness is blocked and publishes a research-input artifact only when the gates pass.
- Factor attribution, factor compression, robustness, economic-gate, walk-forward and factor-diagnostics workflows now require an explicit integrity run ID, check the readiness report, and are manual-dispatch only. They no longer re-run automatically on every engine/workflow push or fall back silently to old run IDs.
- The general full-history research workflow now runs the broad daily-bhavcopy repair and includes the no-trade ledger/readiness report in its artifact.

## Release gates

### Gate A — source completeness
- No failed bhavcopy dates in the repair report.
- Every targeted long-gap pair must be backed by an actual EQ/BE/BZ price observation or an independently evidenced, explicitly approved no-trade/suspension case. A bhavcopy absence alone stays unresolved and blocks the gate.
- No row is fabricated and source series labels are never rewritten. E1 and other non-price-equivalent series must not be mixed into the EQ/BE/BZ equity-price continuity panel.
- The strict missing-held-return check remains enabled.

### Gate B — corporate actions
- Reconcile remaining large adjusted returns at the individual symbol/ex-date level, including splits, bonuses, rights, demergers, mergers and other capital restructurings.
- Missing adjusted rows must be explained or resolved.
- Dividends must be handled through a sourced total-return methodology before describing results as total return. Until then, all results are clearly labeled price-return-only and provisional.

### Gate C — universe integrity
- Validate historical Nifty 500 effective-from/effective-to intervals, symbol rename lineages and listing/delisting dates against dated primary records.
- Investigate `snapshot_floor` intervals rather than automatically assuming each is correct.
- Test survivorship/look-ahead controls, stale values, duplicate canonical issuer/date pairs, missing membership-price joins, and the separation between EQ-only selection eligibility and BE/BZ mark-to-market continuity.

### Gate D — research execution
- Only launch research with an explicit artifact run ID whose readiness report has `price_gap_integrity=PASS`.
- Preserve fixed monthly rebalance/execution timing, transaction-cost sensitivity and the strict held-return assertion.
- Keep the locked 2026-09-01–2027-08-31 evaluation window out of all tuning and candidate selection.
- Treat transaction costs as estimates and evaluate liquidity/slippage sensitivity separately.

## Status interpretation

- **PASS_PRICE_GAPS** means the targeted long-gap repair was reconciled against daily source files. It does not certify membership quality, a complete split/bonus history, dividend adjustment, or investment readiness.
- **PROVISIONAL price-return research** can help test plumbing and exploratory factor behavior once the gap gate passes.
- **Total-return readiness remains BLOCKED** until dividend treatment and corporate-action continuity are established. Do not claim production-grade results before then.


## Operational runbook — current repair generation

1. Use **FLUID-Q Targeted Price Gap Repair** on branch `v1.2-factor-attribution` with base run ID `36875371038` (the source artifact `fluidq-finalized-full-history-36875371038`). The workflow now runs a parser preflight for legacy and UDiFF schemas before downloading the 254 MB dataset.
2. The repair calls `NSEArchives.bhavcopy_raw`, which selects the legacy archive for historical dates and supports UDiFF-era files from 8 July 2024. The parser normalizes both schemas and converts legacy `TURNOVER_LACS` into rupees. Each daily response must contain at least 500 EQ rows to pass the archive completeness sanity check; that threshold does not turn an absent ticker into a no-trade approval.
3. The membership-scoped inventory produced 9,781 candidate symbol/date pairs over 2,209 archive dates (versus the previous unscoped inventory of over 42,000 pairs). The first 1,200 dates were processed in two 600-date batches: 5,574 actual rows added, 5,499 of those BE/BZ rows, 261 absences still unresolved, and zero archive-fetch errors. Run #45 continues the remaining dates; these intermediate counts are not a final readiness result.
4. Inspect `results/price_quality/price_gap_readiness.json` and `data/input/unresolved_gap_exceptions.csv` in the run artifact. Use the artifact as an exploratory **price-return** input only if `status=PASS_PRICE_GAPS` and all missing pairs have an observation or independent evidence. The gate also requires basic raw-price quality and current archive-adapter provenance. If blocked, use the diagnostic artifact, not the research-input artifact.
5. Research workflows are manual-only and require the explicit run ID of the gated artifact. Old queued runs that were created before this change may still be running against a fixed historic price-integrity artifact; their output is stale/unqualified even if a job says success. Do not use those outputs for factor selection or reports.

## Remaining release work after source-gap repair

- **Corporate actions:** the current adjustment is split/bonus-only. Resolve the residual outliers against issuer/ex-date evidence, then build dividend-aware total return. Keep `total_return_ready=false` in all outputs until that is verified.
- **Membership:** review every `snapshot_floor` historical interval against dated evidence and re-run survivorship/look-ahead tests. The backtest loader now applies dated validity intervals; that does not resolve the separate provenance problem in inferred starting dates.
- **Execution and costs:** re-check the close-to-close timing with signal/execution dates, bid/ask and liquidity sensitivity, and alternate cost assumptions. The current linear transaction-cost estimate is a sensitivity model, not a fill simulation.
- **Benchmarks:** report both price-index-relative momentum (if retained as a factor) and total-return benchmark performance once a sourced TRI series is available.
- **Locked evaluation:** do not use 2026-09-01 through 2027-08-31 to choose factor weights, rebalance frequency, exposure thresholds, or holding counts.
