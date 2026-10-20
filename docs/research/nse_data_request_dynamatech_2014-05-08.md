# NSE data request — DYNAMATECH, 2014-05-08

**Status:** DORMANT TEMPLATE ONLY — not to be sent in the current iteration. The user explicitly waived further DYNAMATECH 2014-05-08 retrieval on 2026-10-20. The row remains EXCLUDED / UNRESOLVED, not a recovered price or verified no-trade. Retain this text only in case the user later reopens the gap. This request has not been sent.

## Suggested email

**To:** marketdata@nse.co.in  
**Subject:** Request for NSE Capital Market bhavcopy / EOD record — DYNAMATECH — 08 May 2014

Dear NSE Market Data Team,

I am conducting a historical market-data quality review and would appreciate your help locating the original NSE Capital Market daily bhavcopy / end-of-day record for **08 May 2014**.

Could you please provide the original bhavcopy (CSV/ZIP or exchange-supplied equivalent) for that date, or confirm the authoritative archive/report reference? In particular, please confirm whether **DYNAMATECH** appears in the report and, if present, provide its exact security series and the published close price, previous close, traded quantity, traded value and number of trades.

If the symbol is absent from the report, please clarify whether the exchange record supports any specific interpretation (for example, no reported trade, suspension, non-listing on that date, or another status). I do not want to infer a no-trade classification merely from a missing row or an inaccessible URL.

For provenance, please include the report name, report date, and any reference/case number. I will retain the supplied original file unchanged and record its retrieval timestamp and SHA-256 hash for auditability.

Thank you for your assistance.

Regards,  
[Your name]

## Evidence handling when a response arrives

1. Save the original exchange attachment/file unchanged under the project's raw-evidence area; do not edit or resave it through a spreadsheet application.
2. Record the sender/source, received timestamp (with timezone), report date/name, and SHA-256 of the original bytes.
3. Parse the file with the existing `scripts/repair_price_gaps_bhavcopy.py` archive parser or the existing security-history parser as appropriate; inspect EQ, BE and BZ separately.
4. If an exact row exists, compare symbol, series, date, close and available volume/trade-count fields to the expected target. Preserve the original series.
5. If no row exists, do **not** classify it as no-trade from absence alone. Retain the complete authoritative report and obtain independent listing/suspension/trading-status evidence before disposition.
6. Rerun the price-gap readiness audit and relevant fast validation only after the evidence is recorded. Keep the blocker open until the audit accepts the evidence.

## Guardrails

- This is a request template only; no email has been sent.
- Do not enter a guessed close, interpolate, or automatically carry forward the prior close.
- Do not make total-return claims until dividend adjustment completeness is established.
- Keep the locked evaluation period **2026-09-01 through 2027-08-31** excluded from model selection.
