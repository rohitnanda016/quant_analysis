# DYNAMATECH 2014-05-08 price-gap retrieval log

**Last checked:** 2026-10-20  
**Target:** NSE symbol DYNAMATECH, 2014-05-08  
**Disposition:** OPEN — no accepted price and no verified-no-trade classification.

## Retrieval attempts and findings

1. **Legacy NSE daily bhavcopy URL constructed from the historical pattern:**  
https://archives.nseindia.com/content/historical/EQUITIES/2014/MAY/cm08MAY2014bhav.csv.zip  
The current web retrieval interface returned an access error for this archive URL. This is a limitation of the retrieval interface, not proof that the archive is absent. No file bytes were obtained, so no hash, CSV row, close, volume, or trade count can be reported.

2. **Second pass through the NSE legacy archive host and PR-bhavcopy route:**  
Also attempted the equivalent nsearchives.nseindia.com host for the legacy daily bhavcopy and the legacy PR ZIP pattern https://archives.nseindia.com/archives/equities/bhavcopy/pr/PR080514.zip. The web retrieval interface reported these binary archive URLs as inaccessible. This does not establish a 404, missing report, or no-trade day; no archive payload was retrieved or inspected.

3. **Independent corroboration of the legacy filename convention (route validation only):**  
https://tejhq.dev/blog/sixteen-years-nse-bhavcopy  
This technical write-up describes the legacy pattern `https://archives.nseindia.com/content/historical/EQUITIES/YYYY/MMM/cmDDMMMYYYYbhav.csv.zip` for dates before the July 2024 format cutover. It corroborates the shape of the URL constructed above, but is not an NSE source and does not establish the availability or contents of the target archive.

4. **Official NSE Historical Reports page and live security archive UI:**  
https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives  
https://www.nseindia.com/report-detail/eq_security  
The historical reports page lists **Security-wise Price Volume Archives (Equities)** and **Archives of Daily / Monthly Reports (EQ)**. The security archive page exposes filters for symbol, series, date range and a CSV download, with columns including Close Price, Total Traded Quantity and No. of Trades. However, the accessible page extraction only exposed a stale example for SBIN; it did not return the requested DYNAMATECH row or prove whether the row exists for 2014-05-08. The UI route is a concrete manual retrieval path, not yet evidence resolving this blocker.

5. **Official NSE All Reports page:**  
https://www.nseindia.com/all-reports  
The page includes date-selectable report entries for capital-market bhavcopy and daily reports. NSE notes that the legacy CM Bhavcopy report was discontinued from 2024-07-08 and replaced by the new UDiFF common bhavcopy format; that cutover note does not itself determine the correct 2014 archive URL. The page extraction exposes current/sample report listings and does not provide a direct historical 2014 file payload in this retrieval session.

6. **Official NSE EOD/historical data subscription page and escalation contact:**  
https://www.nseindia.com/static/market-data/eod-historical-data-subscription  
NSE describes EOD files as including End of Day bhavcopy information and security/trade details. Its page directs historical-data requests to marketdata@nse.co.in or +91-22-2659 8385. If public archive retrieval continues to fail, request the Capital Market daily bhavcopy/EOD record for 2014-05-08 and ask NSE to confirm whether DYNAMATECH was present and which series/fields are in the source file. Retain the original response/file and provenance.

7. **Legacy report API route identified from a community-maintained NSE archive client (route lead only, not evidence):**  
https://github.com/jugaad-py/jugaad-data/blob/master/jugaad_data/nse/archives.py  
Its documented legacy route queries NSE's reports API for `CM - Bhavcopy(csv)` using the report date and equities segment. A direct web-tool attempt to open the equivalent 08-May-2014 API URL was inaccessible. This source is useful for reproducing the retrieval route, but it is not authoritative evidence of the missing price or no-trade status.

8. **Secondary monthly-history result:**  
https://stockpricearchive.com/yearly-data/dynamatech/2014/  
It reports May 2014 monthly close ₹988.3 and monthly low ₹805. These monthly figures do not identify the close, volume, or trading status on 2014-05-08. They are not acceptable substitutes for the target daily row.

## Manual retrieval procedure

On the official [Security-wise Archives (Equities)](https://www.nseindia.com/report-detail/eq_security) page, set symbol to DYNAMATECH, select the relevant series (verify EQ and any applicable BE/BZ series separately), set both date bounds to 08-05-2014, then use **View Data** and download the CSV if available. Preserve the downloaded original and compute SHA-256 before parsing. If the UI cannot query that far back, email marketdata@nse.co.in or call +91-22-2659 8385 to request the date-specific bhavcopy/EOD record. A missing row should only be classified after checking the exchange report and corroborating listing/suspension/trading-status evidence.

## Acceptance criteria

Do not close the blocker until one of the following is retained:

- Original exchange daily bhavcopy (or exchange-supplied equivalent) with a matching DYNAMATECH security-series row for 2014-05-08, including date, series, close and trade-volume/trade-count fields; record retrieval timestamp and SHA-256 hash; or
- A successfully retrieved authoritative report and documented proof that the symbol/series has no row, combined with independent evidence sufficient to classify the date as no-trade, suspended, not listed, or another specific status.

A failed HTTP/web fetch is not evidence of no-trade. A monthly OHLC record is not a daily close. A third-party retrieval implementation is a route lead, not primary price evidence. Do not interpolate, carry forward, insert a price, or change readiness status based on the evidence above.

## Gate effect

The price-gap readiness gate remains blocked. No data values or factor calculations were changed by this research note. The 2026-09-01 through 2027-08-31 evaluation window remains excluded from model selection.

## Scope decision — 2026-10-20

**User decision: stop spending research cycles on this gap for the current iteration.** Treat DYNAMATECH / 2014-05-08 as an explicitly waived, unresolved data exception—not as a recovered price, verified no-trade, or evidence that the exchange archive is absent. Do not make further retrieval attempts unless the user reopens this item.

For research outputs in this iteration, exclude this symbol-date observation from any price-dependent calculation that requires an observed value; do not interpolate, carry forward, or synthesize a row. Keep the exception in the audit trail and report it as excluded/unresolved. This scope decision alone does not justify a global price-gap PASS or total-return claim; other data-quality and corporate-action gates still require their own evidence and validation. If the current readiness script continues to fail on this pair, record that gate as waived for this scoped run only rather than changing its status to resolved.
