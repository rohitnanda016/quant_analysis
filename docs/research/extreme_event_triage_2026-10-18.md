# Extreme-return triage — Replay #38

**Snapshot:** 2026-10-18  
**Branch:** `v1.2-factor-attribution`  
**Source run:** [Ticker-Lineage Replay #38](https://github.com/rohitnanda016/quant_analysis/actions/runs/39104282795)  
**Artifact:** `fluidq-symbol-lineage-replay-39104282795` (artifact ID `12128485442`)  
**Purpose:** Human-review queue only. This report does not verify corporate actions, authorize price carry-forward, or clear the research-data gate.

## Gate summary

- 293 extreme-return observations (>50% absolute raw return) reconciled to adjusted rows; 0 adjusted rows missing.
- 57 remain >50% in absolute adjusted return.
- 23 are marked continuity-relevant and require event-level investigation.
- Of the full 293-event reconciliation, 28 are `ACTION_RATIO_MISMATCH` and 42 are `NO_EXACT_ACTION`.
- Price-gap readiness remains **BLOCKED** by DYNAMATECH on 2014-05-08. Dividend adjustment is not proven complete; these are not total-return results.

## Priority A — continuity-relevant adjusted extremes

All rows below remain **open**. The event labels and raw price moves are diagnostic evidence, not proof of a price adjustment. For same-date demerger/scheme events, obtain the exchange circular and establish the price treatment / entitlement ratio before changing the series.

| Date | Symbol | Raw return | Adjusted return | Current status | Triage note |
|---|---|---:|---:|---|---|
| 2015-04-23 | SFCL | +184.4% | +184.4% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; determine whether price series/lineage changed and whether a factor is supported. |
| 2026-02-26 | ANGELBRKG | -90.1% | -90.1% | NO_EXACT_ACTION | No exact action matched; inspect exchange bhavcopy, symbol/series lineage and corporate-action notices. |
| 2019-06-20 | JETAIRWAYS | +89.9% | +89.9% | NO_EXACT_ACTION | No exact action matched; check trading/suspension/resumption context and raw source record. |
| 2015-06-03 | ADANIENT | -82.8% | -82.8% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date scheme of arrangement; exchange circular and entitlement/price treatment required. |
| 2024-09-11 | IPAPPM | -81.2% | -81.2% | NO_EXACT_ACTION | No exact action matched; inspect exchange bhavcopy, symbol/series lineage and corporate-action notices. |
| 2017-05-25 | SINTEX | -75.2% | -75.2% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date scheme of arrangement; establish whether restructuring changed the security/series. |
| 2016-03-15 | CGPOWER | -71.7% | -71.7% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date scheme of arrangement; establish price treatment from primary exchange evidence. |
| 2018-09-28 | CCAVENUE | -70.8% | -70.8% | NO_EXACT_ACTION | No exact action matched; inspect symbol lineage and raw/adjusted price inputs. |
| 2025-05-22 | ABFRL | -66.6% | -66.6% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify ex-date treatment and any resulting security/series mapping. |
| 2018-11-28 | ARVIND | -65.1% | -65.1% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify exchange circular, entitlement ratio and adjustment policy. |
| 2026-04-30 | VEDL | -64.9% | -64.9% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify event terms and correct treatment in the price series. |
| 2025-05-14 | RAYMOND | -64.8% | -64.8% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify security lineage and exchange-prescribed treatment. |
| 2020-03-17 | YESBANK | +58.1% | +58.1% | NO_EXACT_ACTION | No exact action matched; investigate contemporaneous restructuring/trading context and source prices. |
| 2016-01-20 | ABIRLANUVO | -57.3% | -57.3% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date scheme of arrangement; verify event terms and security continuity. |
| 2015-10-01 | IDFC | -57.2% | -57.2% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify exchange circular and factor/series treatment. |
| 2020-03-04 | TATACHEM | -56.5% | -56.5% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify ex-date treatment and entitlement/price relationship. |
| 2018-05-17 | RCOM | +56.2% | +56.2% | NO_EXACT_ACTION | No exact action matched; inspect exchange price records and security status. |
| 2020-03-06 | YESBANK | -56.1% | -56.1% | NO_EXACT_ACTION | No exact action matched; investigate contemporaneous event and confirm source price/series. |
| 2019-10-11 | ABREL | -55.4% | -55.4% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify event terms and security lineage. |
| 2025-10-15 | SKFINDIA | -54.8% | -54.8% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify official event terms and series treatment. |
| 2015-09-11 | AMTEKAUTO | +53.9% | +53.9% | NO_EXACT_ACTION | No exact action matched; investigate exchange record and corporate-action history. |
| 2019-05-30 | IIFL | -52.2% | -52.2% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date scheme of arrangement; verify official terms and price treatment. |
| 2025-04-15 | QUESS | -50.7% | -50.7% | ACTION_ON_DATE_NON_PRICE_FACTOR | Same-date demerger; verify official terms and resulting price/security continuity. |

## Priority B — 42 events with NO_EXACT_ACTION

These events have no exact corporate action matched by the current reconciliation. They are **not automatically errors**: some may reflect listing-day/initial-price effects, genuine extreme moves, restructuring, symbol mapping, or bad source observations. Each must be classified using primary exchange records before it is excluded, adjusted, or accepted.

| Date | Symbol | Raw return |
|---|---|---:|
| 2015-09-11 | AMTEKAUTO | +53.9% |
| 2016-07-12 | QUESS | +58.7% |
| 2017-03-21 | DMART | +114.6% |
| 2017-06-30 | CDSL | +75.6% |
| 2017-09-18 | DIXON | +63.7% |
| 2018-05-17 | RCOM | +56.2% |
| 2018-08-06 | HDFCAMC | +65.1% |
| 2018-09-28 | CCAVENUE | -70.8% |
| 2019-06-20 | JETAIRWAYS | +89.9% |
| 2019-10-14 | IRCTC | +127.4% |
| 2019-12-04 | CSBBANK | +53.9% |
| 2019-12-12 | UJJIVANSFB | +51.2% |
| 2020-03-06 | YESBANK | -56.1% |
| 2020-03-17 | YESBANK | +58.1% |
| 2020-07-23 | ROSSARI | +74.5% |
| 2020-09-17 | HAPPSTMNDS | +123.5% |
| 2020-09-21 | ROUTE | +86.1% |
| 2020-12-14 | RBA | +125.0% |
| 2021-02-02 | INDIGOPNTS | +109.2% |
| 2021-03-15 | MTARTECH | +88.3% |
| 2021-07-19 | CLEAN | +76.1% |
| 2021-07-19 | GRINFRA | +108.7% |
| 2021-07-23 | ETERNAL | +65.8% |
| 2021-09-14 | ACUTAAS | +53.3% |
| 2021-11-10 | NYKAA | +96.1% |
| 2021-11-23 | LATENTVIEW | +148.1% |
| 2021-11-30 | GOCOLORS | +81.7% |
| 2021-12-13 | TEGA | +60.3% |
| 2023-07-27 | NETWEB | +82.1% |
| 2023-08-16 | SBFC | +61.8% |
| 2023-11-29 | IREDA | +87.5% |
| 2023-11-30 | TATATECH | +162.6% |
| 2023-12-20 | DOMS | +67.9% |
| 2024-05-15 | TBOTEK | +52.9% |
| 2024-09-03 | PREMIERENE | +86.6% |
| 2024-09-11 | IPAPPM | -81.2% |
| 2024-09-16 | BAJAJHFL | +135.7% |
| 2024-10-28 | WAAREEENER | +55.6% |
| 2025-08-05 | CPPLUS | +60.4% |
| 2025-09-17 | URBANCO | +62.0% |
| 2025-12-10 | MEESHO | +53.2% |
| 2026-02-26 | ANGELBRKG | -90.1% |

## Required evidence for closure

For each open event, record:
1. Primary source (NSE circular/bhavcopy/security history; BSE only as corroboration where applicable) and retrieval date.
2. Whether the raw observation and prior close agree with the source.
3. Whether the event is an IPO/listing effect, split/bonus, demerger/restructuring, genuine market move, symbol/series transition, or unresolved.
4. A supported adjustment factor and effective date, if any. Do not infer factors solely from proximity or a large return.
5. Disposition: resolved / genuine event confirmed / excluded under a documented rule / unresolved. Keep unresolved events visible and block authoritative performance claims where they affect continuity.

## Separate unresolved price-gap blocker

`DYNAMATECH, 2014-05-08` remains an unresolved archive absence. No EQ/BE/BZ row or independent listing/suspension evidence was established in Replay #38. Monthly history is not sufficient proof of the daily observation or no-trade status. Do not carry forward or mark verified no-trade without independent evidence.

## Next action

Resolve the Priority A rows against primary event notices first, then work through Priority B and the 28 ratio mismatches. Re-run the price-gap and corporate-action gates after evidence is recorded. Keep the authoritative backtest blocked until the data gate passes; keep total-return claims blocked until dividend completeness is demonstrated.
