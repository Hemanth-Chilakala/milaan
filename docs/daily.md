# Daily close

`make recon-day DATE=2026-10-14` matches arriving records against earlier open items. The dashboard selects Today's close or Full month (10M). A first invocation prepares the prior close; that cost is shown separately.

| Close | New source records | Available through date | Core seconds | Complete call seconds | Carried receipts matched today |
|---|---:|---:|---:|---:|---:|
| 2026-10-13 | 3,829,920 | 3,829,920 | 74.529 | 78.299 | 56,578 |
| 2026-10-14 | 499,644 | 4,329,564 | 53.447 | 56.893 | 56,625 |

The 13 October run prepares the prior close. The 14 October run handles new arrivals and carried open items. Core time includes preparation, matching, results, scoring, validation, commits and live audit snapshots. Complete call time also includes namespace checks, profiling and connection cleanup. Explanation generation follows both figures.

## Arrival and carry-forward

Ledger receipts arrive on `posted_date`, bank lines on `value_date`, gateway reports on `settlement_date`, and NACH returns on `return_date`. Synthetic files use these as arrival dates. Real feeds would also need a received-at timestamp.

The independent `MILAAN_DAY_CORE`, `MILAAN_DAY_RES` and `MILAAN_DAY_AUDIT` schemas preserve the monthly demo. The first close selects arrived records. Subsequent closes append new arrivals to the daily sources and existing open-item tables. Closed source members cannot enter another match group. Earlier unlinked receipts remain available for later settlements. Classification can inspect a closed bank record when explaining a duplicate receipt.

Results and accuracy are cumulative through the close date. Expected scoring edges become eligible after every referenced source arrives; that arrival oracle is separate from matching. Same-date replay restores the original opening links and repeats the day's work. `--restart` begins a new replay. Reset retains source data and decision history.

## Verification and scope

The 1,000-record fixture includes every break type. Sequential business-day closes, including settlement grace days, reproduce all 437 monthly links across all seven link fields. Every close is checked for future records and conflicting groups. Same-date replay and reset reproduce the day's links while preserving monthly results. See [fixture observations](daily_fixture_results.json).

The 10M month was not replayed day by day in this check. Closed groups are preserved rather than reconsidered when later ambiguous or reversing evidence arrives. Cumulative results and scoring still grow with history. Initial catch-up and same-date replay cost more than an incremental new close. Bank reversal handling remains the gap measured by hard validation. Exception ages differ when daily and monthly as-of dates differ.

[Raw observations](daily_results.json) include run IDs, counts, accuracy and timings. [Previous daily implementation](daily_previous.json) preserves the measurements before incremental preparation.
