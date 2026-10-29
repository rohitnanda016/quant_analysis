# Demerger-aware return convention

**Adopted for the research implementation:** 2026-10-20  
**Scope:** price-based momentum research; this is a documented research convention, not a claim of official exchange methodology and not a dividend-inclusive total-return policy.

## Decision

Maintain two explicitly distinct interpretations whenever a parent security undergoes a demerger, spin-off, composite scheme, or similar security-distribution event:

1. **Parent-price-only series.** Retain the actual parent security close and report its price return as a parent-price-only return. Do not silently relabel it as shareholder wealth or total return.
2. **Shareholder-wealth-continuous lineage series.** Use only where the entitlement and contemporaneous value of each distributed security are defensible from an authoritative source. For a single parent and one distributed security, the event-date return per one parent share is

   `R_t = (P_parent,t + q P_child,t) / P_parent,t-1 - 1`

   where `q` is the confirmed number of child shares distributed per one parent share and each price is for the correct security/series and event valuation date. For multiple distributed securities, add each confirmed entitlement multiplied by its admissible event-date value.

## Evidence and timing requirements

A wealth-continuous event is eligible only when the evidence ledger contains all of the following:

- The official/company scheme or exchange notice and exact parent/child lineage.
- The entitlement ratio, effective/ex-date and record-date interpretation, including any cash/other consideration.
- A valuation source available at the event decision time: for example, an official exchange-published ex-date reference/pre-open value or an actual child-security price available by the same event close. The source, timestamp, currency, security series and valuation method must be retained.
- The preceding parent close and event-date parent close from the exact price series used in the research panel.
- A reproducible audit row with source URL, retrieval timestamp, payload/hash where retrievable, value calculation and reviewer disposition.

Do not use a later child listing price, a later-discovered price, a news article's quoted close, a chart-derived adjustment factor, or a split ratio inferred from the price move to retrospectively invent an event-date child value. If the child is not priced contemporaneously, the wealth-continuous event return remains unresolved. Do not backfill it with hindsight.

## How unresolved events affect research

- Preserve the observed raw parent prices unchanged.
- Mark the event as `UNRESOLVED_NO_CONTEMPORANEOUS_VALUE` (or a more specific unresolved status) and keep it in audit output.
- Do not interpret the mechanical parent-price discontinuity as a clean momentum signal. Mask/omit the event-spanning return from the wealth-continuous momentum feature until evidence passes the rules above; do not substitute zero or carry forward a price.
- Keep parent-price-only diagnostics separately labelled and never conflate them with wealth-continuous or total-return results.
- After distribution, a genuine shareholder-wealth series must continue to value the distributed shares as well as the parent shares until the research position exits or the security lineage changes again. Merely adding a one-day child value and then dropping the child leg is not an investor-return series.
- A scheme notice/ex-date match alone is not enough to close a return-treatment row; entitlement and value evidence are both required.

## Separate dividend and holdout gates

This convention does not establish dividend completeness. Dividend-adjusted / total-return performance remains blocked until distributions and reinvestment treatment are independently proven complete. The locked evaluation window **2026-09-01 through 2027-08-31** must remain excluded from model selection and tuning.

## Current disposition

The policy is adopted, but it has **not been applied to any price row** by this document. The 23 Priority A ledger rows remain open for value/treatment closure unless their own row has complete evidence and review. No price or corporate-action factor is changed by accepting this convention.

## References and interpretation note

- NSE All Reports: https://www.nseindia.com/all-reports
- NSE EOD/historical data information: https://www.nseindia.com/static/market-data/eod-historical-data-subscription
- Nifty Indices' ABFRL demerger treatment release: https://www.niftyindices.com/Press_Release/ind_prs19052025.pdf

Index-provider treatment (including index divisor or dummy-constituent processes) is not automatically the same as the economically correct price-based single-stock return series. Use it as context, not as an unexplained adjustment instruction.
