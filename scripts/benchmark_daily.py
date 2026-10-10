"""Measure a prior close, a new day's close and carry-forward inside Exasol."""

import json
from datetime import UTC, datetime
from time import perf_counter

from milaan.config import ROOT
from milaan.daily import recon_day
from milaan.db import query, scope
from milaan.explain import generate_explanations
from milaan.pipeline import load, recon


def write_report(payload):
    table = [
        "| Close | New source records | Available through date | Core seconds | Complete call seconds | Carried receipts matched today |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in payload["results"]:
        d = r["daily"]
        table.append(
            f"| {d['date']} | {sum(d['new_source_counts'].values()):,} | {d['cumulative_source_rows']:,} | {r['seconds']:.3f} | {r['call_seconds']:.3f} | {r['carried_edges']:,} |"
        )
    measured = (
        "\n".join(table)
        + "\n\nThe 13 October run prepares the prior close. The 14 October run handles new arrivals and carried open items. Core time includes preparation, matching, results, scoring, validation, commits and live audit snapshots. Complete call time also includes namespace checks, profiling and connection cleanup. Explanation generation follows both figures.\n"
    )
    doc = (
        """# Daily close

`make recon-day DATE=2026-10-14` matches arriving records against earlier open items. The dashboard selects Today's close or Full month (10M). A first invocation prepares the prior close; that cost is shown separately.

"""
        + measured
        + """
## Arrival and carry-forward

Ledger receipts arrive on `posted_date`, bank lines on `value_date`, gateway reports on `settlement_date`, and NACH returns on `return_date`. Synthetic files use these as arrival dates. Real feeds would also need a received-at timestamp.

The independent `MILAAN_DAY_CORE`, `MILAAN_DAY_RES` and `MILAAN_DAY_AUDIT` schemas preserve the monthly demo. The first close selects arrived records. Subsequent closes append new arrivals to the daily sources and existing open-item tables. Closed source members cannot enter another match group. Earlier unlinked receipts remain available for later settlements. Classification can inspect a closed bank record when explaining a duplicate receipt.

Results and accuracy are cumulative through the close date. Expected scoring edges become eligible after every referenced source arrives; that arrival oracle is separate from matching. Same-date replay restores the original opening links and repeats the day's work. `--restart` begins a new replay. Reset retains source data and decision history.

## Verification and scope

The 1,000-record fixture includes every break type. Sequential business-day closes, including settlement grace days, reproduce all 437 monthly links across all seven link fields. Every close is checked for future records and conflicting groups. Same-date replay and reset reproduce the day's links while preserving monthly results. See [fixture observations](daily_fixture_results.json).

The 10M month was not replayed day by day in this check. Closed groups are preserved rather than reconsidered when later ambiguous or reversing evidence arrives. Cumulative results and scoring still grow with history. Initial catch-up and same-date replay cost more than an incremental new close. Bank reversal handling remains the gap measured by hard validation. Exception ages differ when daily and monthly as-of dates differ.

[Raw observations](daily_results.json) include run IDs, counts, accuracy and timings. [Previous daily implementation](daily_previous.json) preserves the measurements before incremental preparation.
"""
    )
    (ROOT / "docs/daily.md").write_text(doc)
    path = ROOT / "docs/benchmarks.md"
    text = path.read_text().split("## Daily close measurements")[0].rstrip()
    path.write_text(
        text
        + "\n\n## Daily close measurements\n\n"
        + measured
        + "\nSee [daily methodology](daily.md) and [raw observations](daily_results.json).\n"
    )


def main():
    current = query("SELECT source_rows FROM MILAAN_AUDIT.DATASET")
    if not current or current[0]["SOURCE_ROWS"] != 10_000_000:
        load(ROOT / "data/10000000")
        recon()
        generate_explanations()
    before = query("SELECT COUNT(*) N FROM MILAAN_RES.LINK")[0]["N"]
    observations = []
    for day, restart in (("2026-10-13", True), ("2026-10-14", False)):
        tick = perf_counter()
        result = recon_day(day, restart=restart, warmup=False)
        result["call_seconds"] = perf_counter() - tick
        result.pop("stage_profiles", None)
        with scope("day"):
            result["exceptions"] = query(
                'SELECT COUNT(*) N,COALESCE(SUM(amount_paise),0) PAISE FROM MILAAN_RES."EXCEPTION"'
            )[0]
            result["carried_edges"] = query(
                "SELECT COUNT(*) N FROM MILAAN_RES.LINK x JOIN MILAAN_CORE.LEDGER l ON x.ledger_id=l.ledger_id JOIN MILAAN_CORE.BANK b ON x.bank_txn_id=b.bank_txn_id WHERE l.posted_date<CAST({day!s} AS DATE) AND b.value_date=CAST({day!s} AS DATE)",
                {"day": day},
            )[0]["N"]
            result["pass_details"] = query(
                "SELECT pass_name,seconds,links_added FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={id!s}",
                {"id": result["run_id"]},
            )
            if day == "2026-10-14":
                generate_explanations()
        observations.append(result)
    after = query("SELECT COUNT(*) N FROM MILAAN_RES.LINK")[0]["N"]
    if before != after or after != 4_383_200:
        raise RuntimeError("Daily mode altered the monthly demo")
    payload = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "monthly_source_rows": 10_000_000,
        "monthly_links_unchanged": after,
        "results": observations,
    }
    (ROOT / "docs/daily_results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    write_report(payload)
    print(json.dumps(payload, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
