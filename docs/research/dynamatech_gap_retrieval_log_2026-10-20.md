# DYNAMATECH 2014-05-08 price-gap retrieval log

**Date checked:** 2026-10-20  
**Target:** NSE symbol DYNAMATECH, 2014-05-08  
**Disposition:** OPEN — no accepted price and no verified-no-trade classification.

## Retrieval attempts and findings

1. **Legacy NSE daily bhavcopy URL constructed from the documented historical pattern:**  
   https://archives.nseindia.com/content/historical/EQUITIES/2014/MAY/cm08MAY2014bhav.csv.zip  
   The current web retrieval interface returned an access error for this archive URL. This is a limitation of the retrieval interface, not proof that the archive is absent. No file bytes were obtained, so no hash, CSV row, close, volume, or trade count can be reported.

2. **Official NSE report entry point:**  
   https://www.nseindia.com/all-reports  
   NSE’s current EOD/historical data page describes end-of-day bhavcopy files and provides a paid historical-data route for data not readily retrieved from the public archive: https://www.nse.in/static/market-data/eod-historical-data-subscription  
   If the legacy file cannot be downloaded directly, use the official report portal or contact NSE Market Data for the relevant historical capital-market EOD file. Retain the response and source provenance.

3. **Secondary monthly-history result:**  
   https://stockpricearchive.com/yearly-data/dynamatech/2014/  
   It reports May 2014 monthly close ₹988.3 and monthly low ₹805. These monthly figures do not identify the close, volume, or trading status on 2014-05-08. They are not acceptable substitutes for the target daily row.

## Acceptance criteria

Do not close the blocker until one of the following is retained:

- Original exchange daily bhavcopy (or exchange-supplied equivalent) with a matching DYNAMATECH security-series row for 2014-05-08, including date, series, close and trade-volume/trade-count fields; record retrieval timestamp and SHA-256 hash; or
- A successfully retrieved authoritative report and documented proof that the symbol/series has no row, combined with independent evidence sufficient to classify the date as no-trade, suspended, not listed, or another specific status.

A failed HTTP/web fetch is not evidence of no-trade. A monthly OHLC record is not a daily close. Do not interpolate, carry forward, insert a price, or change readiness status based on the evidence above.

## Gate effect

The price-gap readiness gate remains blocked. No data values or factor calculations were changed by this research note. The 2026-09-01 through 2027-08-31 evaluation window remains excluded from model selection.
