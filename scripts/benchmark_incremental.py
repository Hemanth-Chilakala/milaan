"""Measure daily matching and audit stages, then compare three days with the month."""

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from milaan.config import ROOT
from milaan.daily import recon_day
from milaan.db import connect, query, scope
from milaan.explain import generate_explanations
from milaan.pipeline import load, recon


def measure(folder, reuse_month=False):
    processes = subprocess.check_output(["ps", "-eo", "comm="], text=True).split()
    if any(name in {"ffmpeg", "chromium", "chrome", "Xvfb"} for name in processes):
        raise RuntimeError("Stop browsers and recording before measuring.")
    if shutil.disk_usage(ROOT).free < 6_000_000_000:
        raise RuntimeError("Restore the 6 GB disk reserve before measuring.")
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest["source_rows"] != 10_000_000:
        raise ValueError("This replay requires the 10M source dataset.")
    if reuse_month:
        saved = json.loads((ROOT / "docs/daily_incremental_results.json").read_text())
        month = saved["month"]
        actual = query("SELECT run_id FROM MILAAN_RES.SCORE WHERE break_type='OVERALL'")
        if not actual or actual[0]["RUN_ID"] != month["run_id"]:
            raise RuntimeError("Monthly score no longer corresponds to the retained benchmark.")
    else:
        load(folder)
        month = recon()
        month.pop("stage_profiles", None)
    observations = []
    for day, restart in [
        ("2026-10-13", True),
        ("2026-10-14", False),
        ("2026-10-15", False),
        ("2026-10-16", False),
    ]:
        tick = perf_counter()
        result = recon_day(day, restart=restart, warmup=False)
        result["complete_call_seconds"] = perf_counter() - tick
        with connect() as connection:
            expected = "SELECT x.* FROM MILAAN_RES.LINK x JOIN MILAAN_CORE.LEDGER l ON l.ledger_id=x.ledger_id JOIN MILAAN_CORE.BANK b ON b.bank_txn_id=x.bank_txn_id LEFT JOIN MILAAN_CORE.PG p ON p.pg_payment_id=x.pg_payment_id WHERE l.posted_date<=CAST({day!s} AS DATE) AND b.value_date<=CAST({day!s} AS DATE) AND (p.settlement_date IS NULL OR p.settlement_date<=CAST({day!s} AS DATE))"
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.MONTH_ELIGIBLE AS " + expected,
                {"day": day},
            )
            for name, columns in [
                ("all_columns", "*"),
                ("edge_keys", "ledger_id,bank_txn_id,pg_payment_id"),
            ]:
                count = connection.execute(
                    f"SELECT COUNT(*) N FROM ((SELECT {columns} FROM MILAAN_DAY_RES.LINK MINUS SELECT {columns} FROM MILAAN_DAY_CORE.MONTH_ELIGIBLE) UNION ALL (SELECT {columns} FROM MILAAN_DAY_CORE.MONTH_ELIGIBLE MINUS SELECT {columns} FROM MILAAN_DAY_RES.LINK))"
                ).fetchone()["N"]
                result[name + "_differences"] = count
            result["cumulative_links"] = connection.execute(
                "SELECT COUNT(*) N FROM MILAAN_DAY_RES.LINK"
            ).fetchone()["N"]
            connection.execute("DROP TABLE MILAAN_DAY_CORE.MONTH_ELIGIBLE")
            connection.commit()
        with scope("day"):
            result["profiles"] = query(
                "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}",
                {"run": result["run_id"]},
            )
            result["exception_count"] = query('SELECT COUNT(*) N FROM MILAAN_RES."EXCEPTION"')[0][
                "N"
            ]
        observations.append(result)
        report = {
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "source_rows": 10_000_000,
            "recording": False,
            "month": month,
            "results": observations,
            "workspace_free_bytes": shutil.disk_usage(ROOT).free,
        }
        (ROOT / "docs/daily_incremental_results.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n"
        )
        print(
            day,
            result["core_matching_seconds"],
            result["scoring_validation_seconds"],
            result["total_seconds"],
            result["edge_keys_differences"],
            flush=True,
        )
    generate_explanations()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/10000000")
    parser.add_argument(
        "--reuse-month",
        action="store_true",
        help="Replay days against the verified retained monthly run without reloading",
    )
    args = parser.parse_args()
    measure(args.data, args.reuse_month)


if __name__ == "__main__":
    main()
