# Resolution of 28 corporate-action ratio flags

**Prepared:** 2026-10-20  
**Input snapshot:** FLUID-Q Ticker-Lineage Replay #38, 2026-10-18  
**Scope:** The 28 observations labelled `ACTION_RATIO_MISMATCH` by the old reconciliation heuristic.  
**Disposition:** **Resolved as a classification defect, not by changing any corporate-action factor.**

## Finding

The old logic compared `prev_close / close` on the ex-date directly with the theoretical share-count factor and marked any difference greater than 8% as `ACTION_RATIO_MISMATCH`. That comparison conflates two distinct quantities:

- **Action factor:** the mechanically implied change in shares from a split and/or bonus, parsed from the NSE corporate-action purpose.
- **Ex-date market return:** the price move after putting the prior close on the new share basis. This can be positive or negative and need not be zero.

The correct diagnostic is:

`factor_adjusted_return = close_ex_date * inferred_factor / prev_close_raw - 1`

For combined events, split and bonus factors are multiplied. The factor must come from the action terms; it must not be back-solved from the observed stock price move. The adjusted return should preserve the actual market move.

In Replay #38, all 28 cases had a parseable same-date split/bonus factor. The saved post-adjustment artifact contains all 28 observations and their factor-adjusted returns. Those returns ranged from **-14.36% to +20.02%**; none remained an absolute return above 50%. Therefore the >50% raw moves were dominated by the share-count event, while the difference between the raw close ratio and the theoretical factor is explained by the residual ex-date move. No factor correction is justified by the 8% ratio heuristic alone.

## Per-event disposition

“Raw previous close → close” below refers to the raw values captured in the Replay #38 reconciliation output. “Factor-adjusted return” is from the corresponding post-adjustment audit output. The recorded price endpoint for the source rows is NSE's historical security-wise data API; the action purposes are from the same replay's NSE corporate-action reconciliation input. The underlying full NSE action-response CSV was not retained in this replay artifact, so the next run should archive that response for stronger row-level provenance.

| Ex-date | Canonical symbol | NSE action purpose captured in replay | Share factor | Raw previous close → close | Factor-adjusted return | Disposition |
|---|---|---|---:|---:|---:|---|
| 2014-08-26 | HAVELLS | Face Value Split Rs 5 to Re 1 | 5× | ₹1,243.90 → ₹272.40 | +9.49% | Factor identified; preserve residual return |
| 2014-12-18 | JKTYRE | Face Value Split Rs 10 to Rs 2 | 5× | ₹592.30 → ₹139.35 | +17.63% | Factor identified; preserve residual return |
| 2015-03-10 | PERSISTENT | Bonus 1:1 | 2× | ₹1,865.35 → ₹849.05 | -8.97% | Factor identified; preserve residual return |
| 2015-03-20 | AJANTPHARM | Face Value Split Rs 5 to Rs 2 | 2.5× | ₹3,067.25 → ₹1,130.80 | -7.83% | Factor identified; preserve residual return |
| 2015-06-25 | JMTAUTOLTD | Face Value Split Rs 10 to Rs 2 | 5× | ₹145.65 → ₹34.95 | +19.98% | Factor identified; preserve residual return |
| 2016-12-26 | BALMLAWRIE | Bonus 3:1 | 4× | ₹1,050.65 → ₹236.20 | -10.07% | Factor identified; preserve residual return |
| 2016-12-30 | ENGINERSIN | Bonus 1:1 | 2× | ₹336.35 → ₹151.00 | -10.21% | Factor identified; preserve residual return |
| 2017-03-24 | POLYMED | Bonus 1:1 | 2× | ₹544.35 → ₹246.95 | -9.27% | Factor identified; preserve residual return |
| 2018-03-22 | LAOPALA | Bonus 1:1 | 2× | ₹649.60 → ₹291.75 | -10.18% | Factor identified; preserve residual return |
| 2018-06-26 | AVANTIFEED | Bonus 1:2 and face value split Rs 2 to Re 1 | 3× | ₹1,563.35 → ₹599.30 | +15.00% | Combined factor identified; preserve residual return |
| 2018-08-02 | BORORENEW | Bonus 3:1 | 4× | ₹1,176.85 → ₹341.35 | +16.02% | Factor identified; preserve residual return |
| 2018-10-31 | JINDWORLD | Face Value Split Rs 5 to Re 1 | 5× | ₹328.10 → ₹71.40 | +8.81% | Factor identified; preserve residual return |
| 2019-12-13 | TRIDENT | Face Value Split Rs 10 to Rs 1 | 10× | ₹66.80 → ₹7.50 | +12.28% | Factor identified; preserve residual return |
| 2020-04-03 | IRCON | Face Value Split Rs 10 to Rs 2 | 5× | ₹393.25 → ₹90.85 | +15.51% | Factor identified; preserve residual return |
| 2021-03-18 | CCAVENUE | Bonus 1:1 | 2× | ₹101.00 → ₹43.25 | -14.36% | Factor identified; preserve residual return |
| 2021-05-07 | VAIBHAVGBL | Face Value Split Rs 10 to Rs 2 | 5× | ₹4,367.00 → ₹996.70 | +14.12% | Factor identified; preserve residual return |
| 2021-05-11 | ALKYLAMINE | Face Value Split Rs 5 to Rs 2 | 2.5× | ₹8,282.45 → ₹3,644.30 | +10.00% | Factor identified; preserve residual return |
| 2021-09-24 | KPRMILL | Face Value Split Rs 5 to Re 1 | 5× | ₹2,098.45 → ₹461.50 | +9.96% | Factor identified; preserve residual return |
| 2021-10-26 | GPIL | Bonus 1:1 and face value split Rs 10 to Rs 5 | 4× | ₹1,313.00 → ₹361.05 | +9.99% | Combined factor identified; preserve residual return |
| 2021-10-28 | IRCTC | Face Value Split Rs 10 to Rs 2 | 5× | ₹4,130.15 → ₹913.50 | +10.59% | Factor identified; preserve residual return |
| 2022-11-21 | EASEMYTRIP | Face Value Split Rs 2 to Re 1 and Bonus 3:1 | 8× | ₹381.95 → ₹57.30 | +20.02% | Combined factor identified; preserve residual return |
| 2023-02-22 | IRB | Face Value Split Rs 10 to Re 1 | 10× | ₹297.45 → ₹34.05 | +14.47% | Factor identified; preserve residual return |
| 2024-01-02 | ALLCARGO | Bonus 3:1 | 4× | ₹329.05 → ₹90.10 | +9.53% | Factor identified; preserve residual return |
| 2024-03-05 | CGCL | Bonus 1:1 and face value split Rs 2 to Re 1 | 4× | ₹964.15 → ₹289.25 | +20.00% | Combined factor identified; preserve residual return |
| 2024-05-24 | INOXWIND | Bonus 3:1 | 4× | ₹605.15 → ₹165.00 | +9.06% | Factor identified; preserve residual return |
| 2024-09-06 | VSTIND | Bonus 10:1 | 11× | ₹4,456.45 → ₹481.25 | +18.79% | Factor identified; preserve residual return |
| 2025-02-28 | JINDWORLD | Bonus 4:1 | 5× | ₹344.70 → ₹82.70 | +19.96% | Factor identified; preserve residual return |
| 2025-09-22 | ADANIPOWER | Face Value Split Rs 10 to Rs 2 | 5× | ₹709.40 → ₹170.25 | +20.00% | Factor identified; preserve residual return |

### Symbol lineage cross-check

Two observations are keyed under historical/canonical symbol mappings in the price artifact:
- **BORORENEW (2018-08-02):** raw price ticker `BOROSIL`, canonical ticker `BORORENEW`.
- **CCAVENUE (2021-03-18):** raw price ticker `INFIBEAM`, canonical ticker `CCAVENUE`.

The saved adjusted data maps both rows to the same canonical symbol used in reconciliation. The factors were therefore joined on the canonical identity, not simply on the current raw ticker.

## Code change

The reconciler now:
- labels same-date rows with a parsed split/bonus factor as `ACTION_FACTOR_IDENTIFIED`, instead of inferring factor validity from an 8% price-ratio threshold;
- exposes `observed_ratio_deviation` and `factor_adjusted_return` separately;
- retains `factor_error` only as a compatibility diagnostic, not as a factor-validation failure;
- keeps rows with no same-date action, and same-date actions without a parsed price factor, in their existing review categories.

No price or corporate-action factor was changed. This correction changes the classification logic and makes the actual ex-date move visible; it does not manufacture prices or claim dividend-adjusted total returns.

## Sources and reproducibility

- [NSE Corporate Actions page](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=INOXWIND&tabIndex=equity) — official action-purpose / ex-date records; sample exact rows were directly discoverable in the page, including INOXWIND Bonus 3:1 on 2024-05-24, and NSE's corporate-actions API is the source used by the replay workflow.
- [NSE security-wise historical data endpoint](https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData) — endpoint recorded in the Replay #38 price rows for all 28 observations.
- [Replay #38](https://github.com/rohitnanda016/quant_analysis/actions/runs/39104282795) — original reconciliation and post-adjustment artifacts.

For the next replay, archive the raw NSE corporate-action API payload with retrieval timestamp and SHA-256 alongside the reconciliation, so each purpose record can be independently rechecked without relying solely on the derived output.

## Result

- **28/28 prior ratio flags:** reclassified from heuristic ratio mismatch to identified split/bonus action factor with residual ex-date return.
- **Factor changes:** 0.
- **Price changes/imputation:** 0.
- **Residual adjusted returns above 50% among these 28:** 0.
- **Remaining separate gates:** the 42 no-exact-action cases, 23 non-price-factor corporate-event cases, price-gap scope decision and dividend-adjustment completeness remain separate work. This resolution does not clear the full backtest or total-return readiness gate.
