# DYNAMATECH 2014-05-08 price-gap retrieval log

**Last checked:** 2026-10-20  
**Target:** NSE symbol DYNAMATECH, 2014-05-08  
**Disposition:** OPEN — no accepted price and no verified-no-trade classification.

## Retrieval attempts and findings

1. **Legacy NSE daily bhavcopy URL constructed from the historical pattern:**  
   https://archives.nseindia.com/content/historical/EQUITIES/2014/MAY/cm08MAY2014bhav.csv.zip  
   The current web retrieval interface returned an access error for this archive URL. This is a limitation of the retrieval interface, not proof that the archive is absent. No file bytes were obtained, so no hash, CSV row, close, volume, or trade count can be reported.

2. **Official NSE Historical Reports page and live security archive UI:**  
   https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives  
   https://www.nseindia.com/report-detail/eq_security  
   The historical reports page lists **Security-wise Price Volume Archives (Equities)** and **Archives of Daily / Monthly Reports (EQ)**. The security archive page exposes filters for symbol, series, date range and a CSV download, with columns including Close Price, Total Traded Quantity and No. of Trades. However, the accessible page extraction only exposed a stale example for SBIN; it did not return the requested DYNAMATECH row or prove whether the row exists for 2014-05-08. The UI route is a concrete manual retrieval path, not yet evidence resolving this blocker.

3. **Official NSE All Reports page:**  
   https://www.nseindia.com/all-reports  
   The page includes date-selectable report entries for capital-market bhavcopy and daily reports. NSE notes that the legacy CM Bhavcopy report was discontinued from 2024-07-08 and replaced by the new UDiFF common bhavcopy format; that cutover note does not itself determine the correct 2014 archive URL.

4. **Official NSE EOD/historical data subscription page:**  
   https://www.nseindia.com/static/market-data/eod-historical-data-subscription  
   NSE describes EOD files as including bhavcopy information and security/trade details. If public archive retrieval continues to fail, request the relevant historical capital-market EOD file from NSE Market Data and retain the response and source provenance.

5. **Legacy report API route identified from a community-maintained NSE archive client (route lead only, not evidence):**  
   https://github.com/jugaad-py/jugaad-data/blob/master/jugaad_data/nse/archives.py  
   Its documented legacy route queries NSE's reports API for `CM - Bhavcopy(csv)` using the report date and equities segment. A direct web-tool attempt to open the equivalent 08-May-2014 API URL was inaccessible. This source is useful for reproducing the retrieval route, but it is not authoritative evidence of the missing price or no-trade status.

6. **Secondary monthly-history result:**  
   https://stockpricearchive.com/yearly-data/dynamatech/2014/  
   It reports May 2014 monthly close ₹988.3 and monthly low ₹805. These monthly figures do not identify the close, volume, or trading status on 2014-05-08. They are not acceptable substitutes for the target daily row.

## Manual retrieval procedure

On the official [Security-wise Archives (Equities)](https://www.nseindia.com/report-detail/eq_security) page, set symbol to `DYNAMATECH`, select the relevant series (verify EQ and any applicable BE/BZ series separately), set both date bounds to `08-05-2014`, then use **View Data** and download the CSV if available. Preserve the downloaded original and compute SHA-256 before parsing. If the UI cannot query that far back, request the date-specific bhavcopy/EOD record from NSE Data & Analytics. A missing row should only be classified after checking the exchange report and corroborating listing/suspension/trading-status evidence.

## Acceptance criteria

Do not close the blocker until one of the following is retained:

- Original exchange daily bhavcopy (or exchange-supplied equivalent) with a matching DYNAMATECH security-series row for 2014-05-08, including date, series, close and trade-volume/trade-count fields; record retrieval timestamp and SHA-256 hash; or
- A successfully retrieved authoritative report and documented proof that the symbol/series has no row, combined with independent evidence sufficient to classify the date as no-trade, suspended, not listed, or another specific status.

A failed HTTP/web fetch is not evidence of no-trade. A monthly OHLC record is not a daily close. A third-party retrieval implementation is a route lead, not primary price evidence. Do not interpolate, carry forward, insert a price, or change readiness status based on the evidence above.

## Gate effect

The price-gap readiness gate remains blocked. No data values or factor calculations were changed by this research note. The 2026-09-01 through 2027-08-31 evaluation window remains excluded from model selection.
