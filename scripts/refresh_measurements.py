"""Refresh unrecorded month and daily measurements against the retained 10M sources."""

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from time import perf_counter

from milaan.config import ROOT
from milaan.daily import recon_day
from milaan.db import connect, query, scope
from milaan.explain import generate_explanations
from milaan.pipeline import recon, setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepared-repeat",
        action="store_true",
        help="Measure the same reset state used by the recording workflow",
    )
    args = parser.parse_args()
    processes = subprocess.check_output(["ps", "-eo", "comm="], text=True).split()
    if any(name in {"ffmpeg", "chromium", "chrome", "Xvfb"} for name in processes):
        raise RuntimeError("Stop the browser and recorder before benchmarking")
    if shutil.disk_usage(ROOT).free < 6_000_000_000:
        raise RuntimeError("The workspace reserve is below 6 GB")
    accuracy = json.loads((ROOT / "docs/validation_results.json").read_text())
    normal = next(r for r in accuracy["results"] if r["label"] == "Normal")
    manifest = json.loads(query("SELECT manifest FROM MILAAN_AUDIT.DATASET")[0]["MANIFEST"])
    if manifest["source_rows"] != 10_000_000 or manifest.get("seed") != 42:
        raise RuntimeError("The retained 10M synthetic demo must be loaded")
    setup()
    reset_seconds = None
    if args.prepared_repeat:
        saved = json.loads((ROOT / "docs/benchmark_results.json").read_text())
        (ROOT / "docs/unprepared_repeat.json").write_text(
            json.dumps(saved, indent=2, default=str) + "\n"
        )
        from milaan.demo import reset_demo

        tick = perf_counter()
        reset_demo("month")
        reset_seconds = perf_counter() - tick
    month = recon()
    month["reset_before_run_seconds"] = reset_seconds
    month["starting_state"] = (
        "Demo reset; open tables prepared before timer"
        if args.prepared_repeat
        else "Previously closed month; restoring open tables inside timer"
    )

    tick = perf_counter()
    generate_explanations()
    month.update(
        source_rows=10_000_000,
        generation_reused=True,
        load_total_seconds=None,
        load_basis="Retained 10M sources; import and normalisation not rerun in this observation",
        explanation_seconds=perf_counter() - tick,
        scores=query("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type"),
        exceptions=query(
            'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
        ),
        pass_details=query(
            "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}", {"run": month["run_id"]}
        ),
    )
    payload = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "logical_cpus": len(os.sched_getaffinity(0)),
        "ram_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "database": "Exasol Personal 2026.2.0-nano.3",
        "recording": False,
        "results": [normal, month],
    }
    (ROOT / "docs/benchmark_results.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
    if args.prepared_repeat:
        daily_path = ROOT / "docs/daily_results.json"
        payload = json.loads(daily_path.read_text())
        from milaan.demo import reset_demo

        tick = perf_counter()
        reset_demo("day", "2026-10-14")
        reset_seconds = perf_counter() - tick
        result = recon_day("2026-10-14", warmup=False)
        result["reset_before_run_seconds"] = reset_seconds
        result["starting_state"] = (
            "Same-day demo replay after explicit reset; preparation inside timer"
        )
        with scope("day"):
            generate_explanations()
        payload["replay_baseline"] = result
        daily_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        print(
            json.dumps(
                {
                    "replay_baseline": result["run_id"],
                    "core": result["core_matching_seconds"],
                    "scoring": result["scoring_validation_seconds"],
                    "total": result["total_seconds"],
                }
            ),
            flush=True,
        )
        return
    observations = []
    for day, restart in (("2026-10-13", True), ("2026-10-14", False)):
        result = recon_day(day, restart=restart, warmup=False)
        with connect() as connection:
            expected = "SELECT x.* FROM MILAAN_RES.LINK x JOIN MILAAN_CORE.LEDGER l ON l.ledger_id=x.ledger_id JOIN MILAAN_CORE.BANK b ON b.bank_txn_id=x.bank_txn_id LEFT JOIN MILAAN_CORE.PG p ON p.pg_payment_id=x.pg_payment_id WHERE l.posted_date<=CAST({day!s} AS DATE) AND b.value_date<=CAST({day!s} AS DATE) AND (p.settlement_date IS NULL OR p.settlement_date<=CAST({day!s} AS DATE))"
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.MONTH_ELIGIBLE AS " + expected,
                {"day": day},
            )
            result["all_columns_differences"] = connection.execute(
                "SELECT COUNT(*) N FROM ((SELECT * FROM MILAAN_DAY_RES.LINK MINUS SELECT * FROM MILAAN_DAY_CORE.MONTH_ELIGIBLE) UNION ALL (SELECT * FROM MILAAN_DAY_CORE.MONTH_ELIGIBLE MINUS SELECT * FROM MILAAN_DAY_RES.LINK))"
            ).fetchone()["N"]
            connection.execute("DROP TABLE MILAAN_DAY_CORE.MONTH_ELIGIBLE")
            connection.commit()
        if result["all_columns_differences"]:
            raise RuntimeError("Daily results differ from eligible monthly links")
        with scope("day"):
            result["exceptions"] = query(
                'SELECT COUNT(*) N,COALESCE(SUM(amount_paise),0) PAISE FROM MILAAN_RES."EXCEPTION"'
            )[0]
            result["pass_details"] = query(
                "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}",
                {"run": result["run_id"]},
            )
            generate_explanations()
        observations.append(result)
        (ROOT / "docs/daily_results.json").write_text(
            json.dumps(
                {
                    "measured_at_utc": datetime.now(UTC).isoformat(),
                    "recording": False,
                    "monthly_source_rows": 10_000_000,
                    "monthly_links_unchanged": month["score"]["TRUE_POSITIVE"],
                    "results": observations,
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "day": day,
                    "run_id": result["run_id"],
                    "core": result["core_matching_seconds"],
                    "scoring": result["scoring_validation_seconds"],
                    "total": result["total_seconds"],
                }
            ),
            flush=True,
        )
    print("Unrecorded month and daily measurements complete", flush=True)


if __name__ == "__main__":
    main()
