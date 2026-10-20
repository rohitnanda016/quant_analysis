# Priority A corporate-action evidence ledger

**Created:** 2026-10-20  
**Source snapshot:** FLUID-Q Ticker-Lineage Replay #38, 2026-10-18  
**Status:** Preliminary evidence ledger; not a readiness clearance.

This ledger separates a lead from verified price-series treatment. A source confirming that a demerger occurred does **not** by itself prove the correct daily adjustment factor or permit a return to be rewritten. Retrieve and retain the original exchange notice, relevant price/series record, retrieval date, and a documented disposition before closing any row.

## Adopted return convention — not yet applied to event prices

The research convention is documented in [Demerger-aware return convention](demerger_return_convention_2026-10-20.md). It keeps parent-price-only diagnostics separate from shareholder-wealth-continuous lineage returns. A demerger return is eligible for the latter only with documented lineage, entitlement ratio, correct effective timing, contemporaneous defensible valuation, and preceding/event-date parent prices from the intended source series.

For one distributed security, the event-date formula is `R_t = (P_{parent,t} + q P_{child,t}) / P_{parent,t-1} - 1`, where `q` is the confirmed child shares per parent share. No later child listing price or chart-derived factor may be used with hindsight. If contemporaneous value is unavailable, leave the event return unresolved and prevent the event-spanning discontinuity from being interpreted as a clean momentum signal. Do not alter raw prices or call the output total return. This convention is adopted for research governance on 2026-10-20; **it has not been applied to any price row**.

## Priority A rows

| Date | Symbol | Replay status | Evidence lead / primary source | Retrieval date | Disposition |
|---|---|---|---|---|---|
| 2015-04-23 | SFCL | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange corporate-action notice not yet located | — | OPEN — verify demerger/scheme, security lineage and price treatment |
| 2026-02-26 | ANGELBRKG | NO_EXACT_ACTION | NSE daily bhavcopy, security history and corporate-action notices required | — | OPEN — verify raw and prior-close observations; classify |
| 2019-06-20 | JETAIRWAYS | NO_EXACT_ACTION | NSE daily bhavcopy, suspension/resumption and corporate-action notices required | — | OPEN — verify raw observation and trading status |
| 2015-06-03 | ADANIENT | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange scheme/corporate-action notice not yet located | — | OPEN — establish event terms and series treatment |
| 2024-09-11 | IPAPPM | NO_EXACT_ACTION | NSE daily bhavcopy, listing/series lineage and corporate-action notices required | — | OPEN — verify source price and classify |
| 2017-05-25 | SINTEX | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange scheme/corporate-action notice not yet located | — | OPEN — establish event terms and security continuity |
| 2016-03-15 | CGPOWER | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange scheme/corporate-action notice not yet located | — | OPEN — verify primary price treatment |
| 2018-09-28 | CCAVENUE | NO_EXACT_ACTION | NSE daily bhavcopy and symbol/series lineage required | — | OPEN — verify source prices and classify |
| 2025-05-22 | ABFRL | ACTION_ON_DATE_NON_PRICE_FACTOR | [Nifty Indices demerger treatment release](https://www.niftyindices.com/Press_Release/ind_prs19052025.pdf); [NSE circular](https://nsearchives.nseindia.com/content/circulars/FAOP68111.pdf); [company notice](https://www.abfrl.com/wp-content/uploads/2025/06/NewspaperAdvertisement.pdf) | 2026-10-20 | PARTIAL — event/ex-date supported; still need source close, entitlement/value and precise series convention |
| 2018-11-28 | ARVIND | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange demerger/scheme notice not yet located | — | OPEN — verify exchange circular, entitlement and factor |
| 2026-04-30 | VEDL | ACTION_ON_DATE_NON_PRICE_FACTOR | [NSE Clearing notice referencing the related NSE/NCL circulars](https://www.archive.nseclearing.in/content/circulars/CMPT73926.pdf) | 2026-10-20 | PARTIAL — event/ex-date lead; retrieve primary demerger terms and relevant price/value evidence |
| 2025-05-14 | RAYMOND | ACTION_ON_DATE_NON_PRICE_FACTOR | [NSE-hosted Raymond annual report excerpt](https://nsearchives.nseindia.com/corporate/RAYMOND_13072025135117_RLSEintimationsigned.pdf) confirms 2025-05-14 record date and 1:1 entitlement; [Raymond Realty abridged prospectus](https://api.raymond.in/uploads/investor/1735642427870RRL%20Abridged%20Prospectus.pdf) states scheme terms | 2026-10-20 | PARTIAL — entitlement/date supported; still need ex-date daily prices and defensible distributed-security valuation for return treatment |
| 2020-03-17 | YESBANK | NO_EXACT_ACTION | NSE bhavcopy, bank restructuring notices and raw source records required | — | OPEN — verify source price and contemporaneous event |
| 2016-01-20 | ABIRLANUVO | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange scheme/corporate-action notice not yet located | — | OPEN — verify event terms and security continuity |
| 2015-10-01 | IDFC | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange demerger/scheme notice not yet located | — | OPEN — verify terms, lineage and price treatment |
| 2020-03-04 | TATACHEM | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange demerger/scheme notice not yet located | — | OPEN — verify event terms and ex-date treatment |
| 2018-05-17 | RCOM | NO_EXACT_ACTION | NSE bhavcopy, series status and restructuring notices required | — | OPEN — verify source price and trading/security status |
| 2020-03-06 | YESBANK | NO_EXACT_ACTION | NSE bhavcopy and contemporaneous restructuring/price records required | — | OPEN — verify raw price and prior close |
| 2019-10-11 | ABREL | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange demerger/scheme notice not yet located | — | OPEN — verify entitlement, security lineage and price treatment |
| 2025-10-15 | SKFINDIA | ACTION_ON_DATE_NON_PRICE_FACTOR | [NSE-hosted company notice dated 2025-10-02](https://nsearchives.nseindia.com/corporate/SKFINDIA25_02102025134944_NSE.pdf) confirms 1:1 allotment and 2025-10-15 record date; [NSE filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_185491_11082026214204_iXBRL_WEB.html) confirms subsequent allotment/listing | 2026-10-20 | PARTIAL — entitlement/date supported; still need ex-date daily prices and defensible distributed-security valuation for return treatment |
| 2015-09-11 | AMTEKAUTO | NO_EXACT_ACTION | NSE bhavcopy, listing/series lineage and corporate-action notices required | — | OPEN — verify source price and classify |
| 2019-05-30 | IIFL | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange scheme/corporate-action notice not yet located | — | OPEN — verify terms and price treatment |
| 2025-04-15 | QUESS | ACTION_ON_DATE_NON_PRICE_FACTOR | Exchange demerger/scheme notice not yet located | — | OPEN — verify entitlement, security lineage and resulting security/value continuity |

## Separate unresolved price-gap blocker

**DYNAMATECH, 2014-05-08 — OPEN.** Replay #38 reported no target-date row after checking EQ/BE/BZ and CSV/JSON security-history variants, and no independent evidence of listing/suspension status. The historical NSE legacy bhavcopy archive convention gives this exact retrieval lead: [NSE archive file for 8 May 2014](https://archives.nseindia.com/content/historical/EQUITIES/2014/MAY/cm08MAY2014bhav.csv.zip). The archive URL could not be inspected through the current web retrieval interface, so this is **not** evidence that the file is absent, nor proof of any price or trading status. NSE's [official data details document](https://archives.nseindia.com/content/press/Data_details_CM.pdf) describes the bhavcopy fields, including the official closing price and trade quantity. The [NSE All Reports portal](https://www.nseindia.com/all-reports) is the official entry point for reports. A third-party monthly archive reports May 2014 monthly range and close ([monthly 2014 history](https://stockpricearchive.com/yearly-data/dynamatech/2014/)), but monthly OHLC cannot prove the 8 May daily close or a verified no-trade. Next retrieval should obtain the original daily archive through an exchange-supported route and preserve the raw file, retrieval timestamp, hash, and matching DYNAMATECH series row—or record that no row exists in a successfully retrieved file. Do not insert a price, carry forward, or mark verified no-trade on current evidence.

## Explicitly waived price-gap exception

**DYNAMATECH, 2014-05-08 — EXCLUDED / UNRESOLVED by user scope decision (2026-10-20).** Do not spend further retrieval effort on this pair for the current iteration. This is not a verified price, no-trade classification, or proof that an archive is absent. Do not fabricate or carry forward a value. Exclude the missing symbol-date observation from any calculation that requires an observed price, retain the exception in audit outputs, and disclose it as a limitation. This waiver does not clear unrelated price-quality, corporate-action, or dividend-adjustment gates and must not be represented as a global readiness PASS. Reopen only if the user asks.

## Gate policy

- Do not claim authoritative backtest readiness until price-gap and corporate-action gates pass.
- Do not claim total-return performance until dividend-adjustment completeness is demonstrated.
- Preserve unresolved observations and record why any row is accepted, adjusted, excluded, or left unresolved.
- Keep 2026-09-01 through 2027-08-31 excluded from tuning/model selection.
- Record original URL, retrieval timestamp, event effective date, source-price check, entitlement ratio, valuation method, factor, reviewer and disposition for each closure.


## Follow-up exchange-source research — 2026-10-20

The public exchange search surfaced additional event-date records for several rows. These improve event identification, but do **not** by themselves establish the appropriate return adjustment or distributed-security value.

| Observation | Source result | What it supports | What remains open |
|---|---|---|---|
| SFCL, 2015-04-23 | [NSE corporate filings for SFCL](https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol=SFCL&tabIndex=sme) shows a Scheme of Arrangement filing on 10-Apr-2015 and a record-date filing for 24-Apr-2015. | A scheme/record-date event exists around the flagged session. | Retrieve the scheme terms and exact effective/ex-date; establish entitlement, distributed-security valuation and correct parent/security lineage. |
| ADANIENT, 2015-06-03 | [MSEI corporate actions for ADANIENT](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=ADANIENT&type=4&vmode=vm) lists 03-Jun-2015 as the ex-date for a Scheme of Arrangement and 04-Jun-2015 as the record date. | Exchange-listed event date and event type corroborated. | Obtain the scheme/entitlement terms and contemporaneous valuation inputs; no split factor inferred. |
| CGPOWER, 2016-03-15 | [MSEI corporate actions for CGPOWER](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=CGPOWER&type=4&vmode=vm) lists 15-Mar-2016 as the ex-date for a Scheme of Arrangement. | Exchange-listed event date and event type corroborated. | Obtain scheme terms, security lineage, entitlement and defensible valuation. |
| IDFC, 2015-10-01 | [NSE corporate actions for IDFC](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=IDFC) lists an EQ-series Demerger with ex-date 01-Oct-2015 and record date 05-Oct-2015. | NSE record directly supports event type and date. | Confirm the exact entitlement/issued-security terms and contemporaneous distributed-security valuation; preserve series-specific price evidence. |
| SINTEX, 2017-05-25 | [Business Standard's contemporaneous report](https://www.business-standard.com/amp/article/markets/sintex-industries-trades-ex-spin-off-117052500315_1.html) states the stock began trading ex-scheme on 25-May-2017 and cites 26-May-2017 as record date. | Strong date/context corroboration. | Locate/retain the underlying exchange/company scheme notice and entitlement terms before valuation. |
| ARVIND, 2018-11-28 | [Contemporaneous report](https://timesofindia.indiatimes.com/business/india-business/arvind-shares-down-71-as-it-adjusts-for-demerger/articleshow/66841209.cms) states ARVIND traded ex-demerger on 28-Nov-2018; the [NSE-hosted Arvind Infrastructure scheme document](https://nsearchives.nseindia.com/corporates/offerdocument/scheme/IM_ARVINFRA_Scheme.pdf) establishes an earlier scheme/undertaking transfer. | Event context and scheme relationship supported. | Reconcile which demerged entity and entitlement correspond to this particular Replay observation; contemporaneous valuation still required. |

### Retrieval limitation for the four raw-price checks

The exact legacy NSE daily ZIP URLs for RCOM (2018-05-17), JETAIRWAYS (2019-06-20), YESBANK (2020-03-06), and YESBANK (2020-03-17) were tried via the available retrieval interface but could not be opened there. NSE's official [EOD/historical data page](https://www.nseindia.com/static/market-data/eod-historical-data-subscription) directs historical-data requests to marketdata@nse.co.in or +91-22-2659 8385. The rows remain blocked and unchanged until a raw NSE bhavcopy or the exact original vendor export is obtained. No secondary reported close has been substituted.

These follow-up findings are research leads and partial event verification only. No proposed shareholder-wealth-continuous formula has been applied, no non-price event has been closed for return treatment, and the dividend/readiness gates remain blocked.


### Additional event-date corroboration from follow-up searches

| Observation | Source | Supported conclusion | Still required |
|---|---|---|---|
| ABIRLANUVO, 2016-01-20 | [MSEI securities information](https://www.msei.in/hindi/markets/equity/get-quotes/default?symbol=ABIRLANUVO) lists a Scheme of Arrangement ex-date of 20-Jan-2016 and record date 21-Jan-2016. | Exchange event date/type supported. | Determine exact scheme entitlement and resulting-security continuity for this observation; no factor inferred. |
| TATACHEM, 2020-03-04 | [NSE Clearing circular NCL/CMPT/43675](https://archives.nseindia.com/content/circulars/CMPT43675.pdf) states the TATACHEM composite-scheme ex-date is 04-Mar-2020; [Tata Chemicals scheme page](https://www.tatachemicals.com/investors/financials/scheme-of-arrangements) lists the scheme and valuation/entitlement-report materials. | Official event date supported and a primary-source path for scheme materials identified. | Retrieve the entitlement/valuation report and establish the distributed-security value on the relevant date. |
| ABREL, 2019-10-11 | [MSEI corporate actions](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=ABREL&type=4&vmode=vm) lists 11-Oct-2019 as the Scheme of Arrangement ex-date and 14-Oct-2019 as record date. | Exchange event date/type supported. | Obtain scheme terms and entitlement/valuation inputs; do not apply a chart-derived adjustment factor. |
| QUESS, 2025-04-15 | [MSEI corporate actions](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=QUESS&type=4&vmode=vm) lists a spin-off on 13-Apr-2025, while the ledger observation is dated 15-Apr-2025. | There is a relevant spin-off event in the period, but the date discrepancy is material. | Resolve exchange-specific ex-date/calendar interpretation against NSE's own action record and price panel before classifying the 15-Apr observation. |
| SKFINDIA, 2025-10-15 | [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=SKFINDIA&tabIndex=sme) lists a Demerger with ex-date and record date 15-Oct-2025. | NSE supports the event date/type; previously collected company notice supports 1:1 entitlement. | Still require parent and distributed-security contemporaneous prices and an approved return convention. |

These are evidence upgrades only. No price or factor has been changed and no row is closed for return treatment.
