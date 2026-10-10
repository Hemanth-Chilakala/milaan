# Presentation dashboard and measured progress

Open the dashboard with `?present=1`, or set `MILAAN_PRESENT=1` before starting it.
Presentation mode uses the locally bundled Inter font and Milaan SVG wordmark,
larger type, and a clean layout without the Streamlit header, menu, status badge,
Deploy control or footer. The font's SIL Open Font License is included in
`docs/brand/fonts/OFL.txt`; colours and font metadata are in `docs/brand/brand.json`.

## Analyst flow

Choose **Full month (10M)** for the scale demonstration or **Today's close** for
the arrival-date workflow. The monthly heading identifies the full-month close;
the daily KPI distinguishes new arrivals from all records available through that
date. **Reset demo** prepares the selected scope's pre-run open items and clears
its current results while retaining source data, prior closed daily matches and
review history. Reset preparation happens before the next reconciliation timer.
A direct rerun of a completed month restores its open tables inside that timer.

The run button locks while reconciliation runs. The live screen shows a stable
seven-pass list, an elapsed clock, matched record percentage and unreconciled
receipt amount. Prior home panels are hidden during the live view and return
with the completed results. Matching completion is followed by explanation
generation before the home screen reports that results are ready.

The showcased settlement contains 37 gateway payments and 36 matched ledger
receipts. Its actual arithmetic is **₹6,07,085.27 − ₹4,856.70 − ₹874.21 =
₹6,01,354.36**. The missing receipt is **LN-100000-36, ₹16,425.71**. The detail
page places bank credit, gateway batch and ledger coverage together, highlights
the missing payment, and shows an evidence-backed explanation. Accept, Reject
and Assign write a decision to Exasol, then confirm it with a toast and an audit
entry. Review decisions remain separate from accounting postings.

## Where live numbers come from

`MILAAN_AUDIT.RUN_LIVE` stores committed progress snapshots. The daily scope uses
its corresponding `MILAAN_DAY_AUDIT` table. The UI polls small audit tables on a
350 ms interval; it does not retrieve transaction tables. The clock uses the
persisted start epoch, and completed passes read their measured seconds and link
counts from `PASS_TIMING`. Snapshot counts change only after real pass work.

The grouped percentage uses source-record membership, including the gateway
payments represented by a grouped bank settlement. Receipt links use a different
denominator. The pipeline verifies live membership against the final
`MATCH_MEMBER` count before completing. Unreconciled receipt rupees are the sum
of the remaining open ledger amounts; bank-only differences are in the exception
queue. For the 10M demonstration, this falls from **₹8,662.53 Cr to ₹167.55 Cr**.

## Recorded observations

These are separate measured runs on the same 4-vCPU machine, with no video
recorder. They supplement the performance benchmark rather than replacing it.

| Observation | Reconciliation seconds | Evidence |
|---|---:|---|
| Freshly loaded 10M month, live auditing enabled, no browser | 87.53 | [Snapshot](presentation_results.json) |
| Completed-month rerun; open tables restored inside the timer | 104.09 | [Retained slower observation](presentation_repeat_observation.json) |
| Browser run after Reset demo, before the final stale-panel correction | 83.41 | [Observation](presentation_month_ui.json) |
| Final browser run after Reset demo and stale-panel correction | 81.83 | [Verified monthly flow](presentation_month_verified.json) |
| 14 October daily close, incremental CLI run | 53.45 | [Daily measurements](daily_results.json) |
| 14 October daily close, browser run after Reset demo | 48.32 | [Browser flow](presentation_daily_ui.json) |

The 104.09-second job finished with unchanged counts after its browser check was
interrupted by a verification failure. The earlier 83.41-second browser check
exposed old panels below the live view. Both observations are retained. The final
monthly browser verification after that correction is recorded separately in
`presentation_month_verified.json`.

The monthly result remains **9,850,231 grouped records, 4,383,200 receipt links,
103,564 exceptions, zero false links and 1,779 missed links** against its synthetic
ground truth. The daily result remains **499,644 new arrivals**, **4,329,564
available records**, zero false links and 805 missed links. Normal, blind and hard
holdout results are also visible on the Accuracy page. Hard-mode precision is
99.1544% with 3,220 false links, exposing a reversal-handling gap; it is not
represented as production validation.

## Verification

The five pages are checked at 1920×1080 and 1366×768 for clipped text, horizontal
overflow, visible Streamlit chrome and local Inter typography. Screenshots of
every page are in `docs/screenshots/`; the layout measurements are in
`presentation_layouts.json`. Live monthly and daily views are also checked at
both sizes, including the locked run button, Reset demo and completed real runs.
The browser review verifies the showcase arithmetic and a persisted Accept
decision. These checks use the actual local database.

Thirty non-database tests and ten database tests passed. The database checks
include complete fixture reconciliation, stored expected links, conflict checks,
arrival-date replay and same-day Reset/replay preservation. The sequential daily
fixture produced the same 437 links as its monthly close across all seven link
fields. Database tests replace the demonstration tables; the protected 10M
dataset was restored afterwards. See [Daily-close design](daily.md) and
[Validation results](validation_results.json) for the detailed scope.
