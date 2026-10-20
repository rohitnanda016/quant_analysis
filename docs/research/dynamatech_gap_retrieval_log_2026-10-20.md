# DYNAMATECH 2014-05-08 price-gap retrieval log

**Last checked:** 2026-10-20  
**Target:** NSE symbol DYNAMATECH, 2014-05-08  
**Disposition:** OPEN — no accepted price and no verified-no-trade classification.

## Retrieval attempts and findings

1. **Legacy NSE daily bhavcopy URL constructed from the historical pattern:**  
   https://archives.nseindia.com/content/historical/EQUITIES/2014/MAY/cm08MAY2014bhav.csv.zip  
   The current web retrieval interface returned an access error for this archive URL. This is a limitation of the retrieval interface, not proof that the archive is absent. No file bytes were obtained, so no hash, CSV row, close, volume, or trade count can be reported.

2. **Official NSE Historical Reports page:**  
   https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives  
   The page explicitly lists **Security-wise Price Volume Archives (Equities)** and **Archives of Daily / Monthly Reports (EQ)**. This gives a second official route to retrieve/verify the target date, beyond the all-reports landing page: https://www.nseindia.com/all-reports. The page is accessible, but the current web retrieval interface did not expose the target-day report bytes or a DYNAMATECH row.

3. **Official NSE EOD/historical data subscription page:**  
   https://www.nseindia.com/static/market-data/eod-historical-data-subscription  
   NSE describes EOD files as including bhavcopy information and security/trade details. If public archive retrieval continues to fail, request the relevant historical capital-market EOD file from NSE Market Data and retain the response and source provenance.

4. **Legacy report API route identified from a community-maintained NSE archive client (route lead only, not evidence):**  
   https://github.com/jugaad-py/jugaad-data/blob/master/jugaad_data/nse/archives.py  
   Its documented legacy route queries NSE's reports API for `CM - Bhavcopy(csv)` using the report date and equities segment. A direct web-tool attempt to open the equivalent 08-May-2014 API URL was inaccessible. This source is useful for reproducing the retrieval route, but it is not authoritative evidence of the missing price or no-trade status.

5. **Secondary monthly-history result:**  
   https://stockpricearchive.com/yearly-data/dynamatech/2014/  
   It reports May 2014 monthly close ₹988.3 and monthly low ₹805. These monthly figures do not identify the close, volume, or trading status on 2014-05-08. They are not acceptable substitutes for the target daily row.

## Acceptance criteria

Do not close the blocker until one of the following is retained:

- Original exchange daily bhavcopy (or exchange-supplied equivalent) with a matching DYNAMATECH security-series row for 2014-05-08, including date, series, close and trade-volume/trade-count fields; record retrieval timestamp and SHA-256 hash; or
- A successfully retrieved authoritative report and documented proof that the symbol/series has no row, combined with independent evidence sufficient to classify the date as no-trade, suspended, not listed, or another specific status.

A failed HTTP/web fetch is not evidence of no-trade. A monthly OHLC record is not a daily close. A third-party retrieval implementation is a route lead, not primary price evidence. Do not interpolate, carry forward, insert a price, or change readiness status based on the evidence above.

## Gate effect

The price-gap readiness gate remains blocked. No data values or factor calculations were changed by this research note. The 2026-09-01 through 2027-08-31 evaluation window remains excluded from model selection.
