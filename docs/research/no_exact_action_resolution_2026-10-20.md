# Resolution of 42 NO_EXACT_ACTION observations

**Prepared:** 2026-10-20  
**Source snapshot:** NSE Ticker-Lineage Replay #38 (18-Oct-2026)  
**Original count:** 42 rows in `results/price_quality/extreme_return_reconciliation.csv`  
**Status:** All 42 have a documented disposition. The four historic price-value disagreements are reconciled as a Last Price versus Close Price field distinction using the retained NSE historical-security source rows. No saved price values were changed.

## Summary

The old `NO_EXACT_ACTION` label meant only that the exact-date NSE corporate-action join found no matching action. It did not establish that the price move was erroneous, nor that there was no listing/event context. The 42 rows separate into:

| Disposition | Rows | Meaning |
|---|---:|---|
| Listing-day price discovery | 34 | First observation coincides with official NSE listing date; previous-close field is an IPO issue/reference price, not a close from a prior listed session. Exclude this pseudo-return from close-to-close daily momentum calculations. |
| Split/bonus found through historical symbol aliases | 2 | Actual corporate actions that were missed because the prior symbol was not connected to the event symbol. Action factors are 5x and 10x, sourced from NSE circulars. |
| NSE field distinction reconciled (news quote = Last Price; model series = Close Price) | 4 | The saved values match the official NSE historical-security endpoint’s separate Close Price field; the different news figures match its Last Price field. No price replacement was made. |
| Genuine market move and close corroborated by contemporaneous report | 2 | Price moves have contemporaneous public explanations, with closing values matching the saved row. Keep the moves; do not create corporate-action factors. |
| **Total** | **42** | |

This is a disposition of the original reconciliation statuses, not a statement that the full FLUID-Q data-readiness gate now passes.

## Listing-day / IPO price discovery — 34 rows

The original post-adjustment audit labelled all 34 as `series_start=True`; each date is the first observed session for that symbol and matches the listing date shown by the NSE equity security profile. The previous-close values in this audit are offer/reference-price fields rather than a prior close of an already-listed security. They are not close-to-close daily returns and must not be used to rank daily momentum.

| Listing date | Symbol | NSE security profile |
|---|---|---|
| 2016-07-12 | QUESS | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=QUESS) |
| 2017-03-21 | DMART | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=DMART) |
| 2017-06-30 | CDSL | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=CDSL) |
| 2017-09-18 | DIXON | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=DIXON) |
| 2018-08-06 | HDFCAMC | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=HDFCAMC) |
| 2019-10-14 | IRCTC | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=IRCTC) |
| 2019-12-04 | CSBBANK | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=CSBBANK) |
| 2019-12-12 | UJJIVANSFB | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=UJJIVANSFB) |
| 2020-07-23 | ROSSARI | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=ROSSARI) |
| 2020-09-17 | HAPPSTMNDS | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=HAPPSTMNDS) |
| 2020-09-21 | ROUTE | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=ROUTE) |
| 2020-12-14 | RBA | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=RBA) |
| 2021-02-02 | INDIGOPNTS | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=INDIGOPNTS) |
| 2021-03-15 | MTARTECH | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=MTARTECH) |
| 2021-07-19 | CLEAN | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=CLEAN) |
| 2021-07-19 | GRINFRA | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=GRINFRA) |
| 2021-07-23 | ETERNAL (then ZOMATO) | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=ETERNAL) |
| 2021-09-14 | ACUTAAS (formerly AMIORG) | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=ACUTAAS) |
| 2021-11-10 | NYKAA | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=NYKAA) |
| 2021-11-23 | LATENTVIEW | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=LATENTVIEW) |
| 2021-11-30 | GOCOLORS | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=GOCOLORS) |
| 2021-12-13 | TEGA | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=TEGA) |
| 2023-07-27 | NETWEB | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=NETWEB) |
| 2023-08-16 | SBFC | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=SBFC) |
| 2023-11-29 | IREDA | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=IREDA) |
| 2023-11-30 | TATATECH | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=TATATECH) |
| 2023-12-20 | DOMS | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=DOMS) |
| 2024-05-15 | TBOTEK | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=TBOTEK) |
| 2024-09-03 | PREMIERENE | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=PREMIERENE) |
| 2024-09-16 | BAJAJHFL | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=BAJAJHFL) |
| 2024-10-28 | WAAREEENER | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=WAAREEENER) |
| 2025-08-05 | CPPLUS (Aditya Infotech) | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=CPPLUS) |
| 2025-09-17 | URBANCO | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=URBANCO) |
| 2025-12-10 | MEESHO | [NSE profile](https://www.nseindia.com/get-quotes/equity?symbol=MEESHO) |

Rule: these observations are retained for audit/history and marked `LISTING_DAY_PRICE_DISCOVERY`; they are not synthetic daily returns. Subsequent close-to-close returns continue normally once there is an actual previous listed-session close.

**Backtest integration check:** `scripts/run_fluidq_backtest.py` builds held-portfolio returns from the close-price panel using `pct_change(fill_method=None)` rather than the source `prev_close` field; a symbol's first close has no prior close in that panel and therefore produces no first-day close-to-close return. New holdings are executed at a future session close and begin earning returns on the following session. This check supports keeping the IPO reference-price gain in the audit as `LISTING_DAY_PRICE_DISCOVERY` without changing the close-to-close return formula.

## Split/bonus events hidden by ticker lineage — 2 rows resolved

| Original row | Actual action | Evidence / lineage repair | Previous close → ex-date close | Residual return after factor |
|---|---|---|---:|---:|
| IPAPPM, 2024-09-11 | Andhra Paper share split, face value Rs 10 → Rs 2; 5 shares per old share | [NSE circular CML/63530](https://nsearchives.nseindia.com/content/circulars/CML63530.pdf); ticker chain IPAPPM → ANDPAPER (effective 2020-01-22; [NSE CML/43237 mirror](https://www.steelcitynettrade.com/Circulars/Change%20in%20Symbol%20and%20Name%20of%20the%20Company%20-%20International%20Paper%20APPM.pdf)) → ANDHRAPAP (effective 2020-03-05; [NSE CML/43707 mirror](https://www.steelcitynettrade.com/Circulars/Change%20in%20trading%20Symbol%20of%20ANDHRA%20PAPER%20LIMITED.pdf)) | Rs 586.45 → Rs 110.40 | -5.87% |
| ANGELBRKG, 2026-02-26 | Angel One share split, face value Rs 10 → Re 1; 10 shares per old share | [NSE circular CML/72889](https://nsearchives.nseindia.com/content/circulars/CML72889.pdf); [NSE CML/50211 symbol-change circular mirror](https://www.steelcitynettrade.com/Circulars/Change%20in%20name%20and%20symbol%20of%20Angel%20Broking%20Limited.pdf) identifies ANGELBRKG → ANGELONE | Rs 2,489.90 → Rs 246.50 | -1.00% |

The supplemental corporate-action ledger now records the factors, and the ticker-lineage table contains both historical symbol chains. The reconciler deduplicates the same action if it appears both in the live NSE action feed and in the manual verified ledger; it also parses the per-row `subject` when the main action response has a blank `purpose`.

## Genuine market-event rows — 6 rows, no split/bonus factor

These are not split/bonus events. Their news/corporate context supports treating the move as a market event, while source-price verification is separately noted.

| Date | Symbol | Saved previous close → close | Return | Event evidence | Disposition |
|---|---|---:|---:|---|---|
| 2015-09-11 | AMTEKAUTO | Rs 30.50 → Rs 46.95 | +53.93% | [Business Standard report](https://www.business-standard.com/article/markets/amtek-auto-zooms-over-50-after-preferential-allotment-to-promoters-115091100560_1.html) describes the >50% rally after preferential promoter allotment and cites Rs 46.95 close | Market move supported; no factor to apply |
| 2018-05-17 | RCOM | Rs 10.50 → Rs 16.40 | +56.19% | [NSE historical-security endpoint](https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData) retained in replay output reports last Rs 17.40 and close Rs 16.40 | **RESOLVED — field distinction.** Article’s Rs 17.40 aligns to Last Price; saved/model value Rs 16.40 aligns to Close Price. No price changed. |
| 2018-09-28 | CCAVENUE (formerly INFIBEAM) | Rs 200.35 → Rs 58.45 | -70.83% | [Business Standard / PTI report](https://www.business-standard.com/article/pti-stories/infibeam-avenues-shares-nosedive-71-118092800967_1.html) explicitly reports NSE close Rs 58.45 and a 70.82% fall | Close corroborated; no factor to apply |
| 2019-06-20 | JETAIRWAYS | Rs 33.10 → Rs 62.85 | +89.88% | [NSE historical-security endpoint](https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData) retained in replay output reports last Rs 73.55 and close Rs 62.85 | **RESOLVED — field distinction.** Reported Rs 73.55 aligns to Last Price; saved/model value Rs 62.85 aligns to Close Price. No price changed. |
| 2020-03-06 | YESBANK | Rs 36.80 → Rs 16.15 | -56.11% | [NSE historical-security endpoint](https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData) retained in replay output reports last Rs 16.60 and close Rs 16.15 | **RESOLVED — field distinction.** Reported Rs 16.60 aligns to Last Price; saved/model value Rs 16.15 aligns to Close Price. No price changed. |
| 2020-03-17 | YESBANK | Rs 37.10 → Rs 58.65 | +58.09% | [NSE historical-security endpoint](https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData) retained in replay output reports last Rs 59.10 and close Rs 58.65 | **RESOLVED — field distinction.** Reported Rs 59.10 aligns to Last Price; saved/model value Rs 58.65 aligns to Close Price. No price changed. |

The four historic discrepancies are reconciled as field-definition differences using the retained official NSE historical-security source rows. NSE’s [All Reports / Security-wise Archives](https://www.nseindia.com/all-reports/) interface exposes separate Last Price and Close Price columns; the project downloader also maps last price and close price independently in `scripts/download_stage_a.py`. The four article figures match `last`, while the saved research observations match `close`. No price was overwritten. Row-level values and source hashes are recorded in `data/reference/price_close_vs_last_reconciliation_2026-10-20.csv`.

## Code/data changes in this branch

- `data/reference/nse_historical_symbol_changes.csv`: add IPAPPM → ANDPAPER → ANDHRAPAP and ANGELBRKG → ANGELONE historical mappings with source links.
- `data/input/verified_manual_corporate_actions.csv`: add the 2024 Andhra Paper 5x split and 2026 Angel One 10x split from NSE circulars.
- `data/input/verified_corporate_events.csv`: add 34 listing-day classifications, strengthen sources for six market-event cases, and record the two recovered splits.
- `scripts/reconcile_extreme_returns.py`: emit event evidence fields; classify IPO listing sessions and supported genuine-market events; preserve explicit price-field reconciliation status; deduplicate same action across NSE/manual inputs; read row-wise fallback from `subject`.
- `tests/test_reconcile_extreme_returns.py`: cover listing-day classification and historical ticker-alias split recovery.

No raw price values were edited. The two factor-adjusted returns are calculated from saved previous-close/close fields and the exchange factor; they are diagnostics, not replacement observations.

## Remaining actions / gates

1. Run full fast validation and re-run the reconciliation workflow using a newly archived NSE corporate-action payload (including source timestamps and SHA-256).
2. Four previously disputed price fields are reconciled against the official NSE historical-security output: news figures correspond to Last Price; the model panel uses Close Price. The saved values are unchanged; see the row-level audit CSV.
3. Confirm all 34 first-listing-session rows are excluded from any close-to-close daily momentum return input (not just the audit's `series_start` diagnostic).
4. Keep the separate 23 corporate-action/non-price-factor observations and dividend-completeness gate open. Keep the DYNAMATECH observation excluded/unresolved per user scope decision. Keep the locked evaluation period 2026-09-01 to 2027-08-31 out of model selection.

This report resolves the reason for each old `NO_EXACT_ACTION` label, but it does not claim the overall price-quality or backtest readiness gate passes.


## Source-price field reconciliation log — 2026-10-20

All four previously reported numeric differences have been reconciled as confusion between two distinct fields returned by NSE’s historical-security endpoint: last price and close price. NSE’s [Security-wise Archives (Equities)](https://www.nseindia.com/all-reports/) presents separate Last Price and Close Price columns. The project downloader maps these independently to last and close in `scripts/download_stage_a.py`. The historical rows below were retained in replay #40; the research panel’s saved price uses close, while the figures used in earlier news comparisons match last.

| Date | Symbol | Prev Close | NSE Last Price | NSE Close Price / saved value | Resolution |
|---|---|---:|---:|---:|---|
| 2018-05-17 | RCOM | ₹10.50 | ₹17.40 | ₹16.40 | Resolved as Last Price vs Close Price; no price substituted. |
| 2019-06-20 | JETAIRWAYS | ₹33.10 | ₹73.55 | ₹62.85 | Resolved as Last Price vs Close Price; no price substituted. |
| 2020-03-06 | YESBANK | ₹36.80 | ₹16.60 | ₹16.15 | Resolved as Last Price vs Close Price; no price substituted. |
| 2020-03-17 | YESBANK | ₹37.10 | ₹59.10 | ₹58.65 | Resolved as Last Price vs Close Price; no price substituted. |

**Reproducibility:** source endpoint https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData; replay run [#40](https://github.com/rohitnanda016/quant_analysis/actions/runs/39437085035); artifact ZIP SHA-256 `840ffd868e2ee3ce9b6f8d4d076afd46f142df75c76564a0c3ff73cacd711ccd`; artifact member `data/processed/adjusted/prices_adjusted_split_bonus.csv`, SHA-256 `b2dd83090ef37d9ebd76d6f6c1e443f0d20b8dfb7a57871a49c33ba831957b11` (645,145,031 bytes). The row-level CSV records adjustment_factor=1.0 and dividend_adjustment=not_applied for every row. These fields identify this as a close-vs-last reconciliation—not a split/bonus correction or dividend-adjusted total-return treatment.

NSE’s [SEBI-referenced closing-price methodology](https://www.sebi.gov.in/legal/circulars/jan-2026/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session_99122.html) states that before the later Closing Auction Session changes, cash-equity closing prices were based on the VWAP of trades in the last 30 minutes of continuous trading. This supports treating last-traded-price and official closing-price fields as distinct measures.

The original legacy daily bhavcopy ZIPs remain unavailable through this retrieval interface. However, the retained official NSE historical-security endpoint provides both fields on the exact dated rows and resolves these four specific disagreements without replacing any close. This does not clear unrelated demerger-lineage or dividend-completeness gates.
