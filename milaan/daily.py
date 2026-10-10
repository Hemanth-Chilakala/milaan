"""Arrival-date closes with independent cumulative matches and carried open items."""

import argparse
import fcntl
import json
from datetime import date, timedelta
from time import perf_counter

from milaan.config import ROOT
from milaan.db import connect, scope, scoped_sql, statements
from milaan.pipeline import _recon

ARRIVAL = {
    "LEDGER": "posted_date",
    "BANK": "value_date",
    "PG": "settlement_date",
    "NACH": "return_date",
}
OPEN_COLUMNS = {
    "LEDGER": "ledger_id,loan_id,amount_paise,channel,external_ref,posted_date,status,ref_norm,name_norm,day_index,duplicate_rank,ref_suffix8",
    "BANK": "bank_txn_id,value_date,bank_ref,amount_paise,ref_norm,loan_id,batch_id,channel,name_norm,day_index,ref_suffix8",
    "PG": "pg_payment_id,gross_paise,fee_paise,gst_on_fee_paise,net_paise,settlement_batch_id,settlement_date,settlement_utr,loan_id,payment_ref",
}
KEYS = {"LEDGER": "ledger_id", "BANK": "bank_txn_id", "PG": "pg_payment_id"}


def initialise():
    # Monthly tables and UDFs are never replaced by the daily namespace.
    with connect() as connection:
        for sql in statements(ROOT / "sql/00_schema.sql"):
            for schema in ("CORE", "RES", "AUDIT"):
                sql = sql.replace(f"MILAAN_{schema}", f"MILAAN_DAY_{schema}")
            connection.execute(sql)
        for path in sorted((ROOT / "udf").glob("*.sql")):
            connection.execute(scoped_sql(statements(path)[0], "day"))
        connection.execute(
            "CREATE TABLE IF NOT EXISTS MILAAN_DAY_AUDIT.DAY_STATE (dataset_id VARCHAR(36),close_date DATE)"
        )
        connection.commit()


def prepare(day: date, restart=False):
    with connect() as connection:
        dataset = connection.execute("SELECT * FROM MILAAN_AUDIT.DATASET").fetchone()
        if not dataset:
            raise RuntimeError("Load the monthly dataset first")
        last = connection.execute("SELECT * FROM MILAAN_DAY_AUDIT.DAY_STATE").fetchone()
        fresh = restart or not last or last["DATASET_ID"] != dataset["DATASET_ID"]
        if not fresh and day < date.fromisoformat(str(last["CLOSE_DATE"])):
            raise ValueError(
                "Daily closes must move forward; use --restart to replay earlier dates"
            )
        if not fresh:
            run = connection.execute(
                "SELECT status FROM MILAAN_DAY_AUDIT.RUN WHERE dataset_id={id!s} ORDER BY started_at DESC LIMIT 1",
                {"id": dataset["DATASET_ID"]},
            ).fetchone()
            if run and run["STATUS"] != "COMPLETE":
                if run["STATUS"] != "READY":
                    raise RuntimeError(
                        "Previous daily close did not complete; replay from --restart"
                    )
        same_day = not fresh and day == date.fromisoformat(str(last["CLOSE_DATE"]))
        connection.execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.CLOSED_LINK AS SELECT * FROM "
            + ("MILAAN_DAY_CORE.DAY_START_LINK" if same_day else "MILAAN_DAY_RES.LINK")
            + (" WHERE 1=0" if fresh else "")
        )
        connection.execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.CLOSED_MEMBER AS SELECT * FROM "
            + ("MILAAN_DAY_CORE.DAY_START_MEMBER" if same_day else "MILAAN_DAY_RES.MATCH_MEMBER")
            + (" WHERE 1=0" if fresh else "")
        )
        if not same_day:
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.DAY_START_LINK AS SELECT * FROM MILAAN_DAY_CORE.CLOSED_LINK"
            )
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.DAY_START_MEMBER AS SELECT * FROM MILAAN_DAY_CORE.CLOSED_MEMBER"
            )
        previous_day = str(last["CLOSE_DATE"]) if not fresh else str(date(1900, 1, 1))
        if same_day:
            saved = connection.execute("SELECT manifest FROM MILAAN_DAY_AUDIT.DATASET").fetchone()
            previous_day = json.loads(saved["MANIFEST"])["daily_close"]["previous_date"]
        connection.execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.CALENDAR AS SELECT * FROM MILAAN_CORE.CALENDAR"
        )
        new_counts, total = {}, 0
        for source, arrival in ARRIVAL.items():
            if fresh:
                connection.execute(
                    f"CREATE OR REPLACE TABLE MILAAN_DAY_CORE.{source} AS SELECT * FROM MILAAN_CORE.{source} WHERE {arrival}<=CAST({{day!s}} AS DATE)",
                    {"day": str(day)},
                )
            elif not same_day:
                connection.execute(
                    f"INSERT INTO MILAAN_DAY_CORE.{source} SELECT * FROM MILAAN_CORE.{source} WHERE {arrival}>CAST({{previous!s}} AS DATE) AND {arrival}<=CAST({{day!s}} AS DATE)",
                    {"day": str(day), "previous": previous_day},
                )
            count = connection.execute(
                f"SELECT COUNT(*) N FROM MILAAN_DAY_CORE.{source}"
            ).fetchone()["N"]
            total += count
            new_counts[source] = connection.execute(
                f"SELECT COUNT(*) N FROM MILAAN_DAY_CORE.{source} WHERE {arrival}>CAST({{previous!s}} AS DATE)",
                {"previous": previous_day},
            ).fetchone()["N"]
            if source in OPEN_COLUMNS:
                if fresh or same_day:
                    connection.execute(
                        f"CREATE OR REPLACE TABLE MILAAN_DAY_CORE.OPEN_{source} AS SELECT {OPEN_COLUMNS[source]} FROM MILAAN_DAY_CORE.{source} s WHERE NOT EXISTS (SELECT 1 FROM MILAAN_DAY_CORE.CLOSED_MEMBER m WHERE m.source_name='{source}' AND m.txn_key=s.{KEYS[source]})"
                    )
                else:
                    connection.execute(
                        f"DELETE FROM MILAAN_DAY_CORE.OPEN_{source} s WHERE EXISTS (SELECT 1 FROM MILAAN_DAY_CORE.CLOSED_MEMBER m WHERE m.source_name='{source}' AND m.txn_key=s.{KEYS[source]})"
                    )
                    connection.execute(
                        f"INSERT INTO MILAAN_DAY_CORE.OPEN_{source} SELECT {OPEN_COLUMNS[source]} FROM MILAAN_CORE.{source} WHERE {arrival}>CAST({{previous!s}} AS DATE) AND {arrival}<=CAST({{day!s}} AS DATE)",
                        {"day": str(day), "previous": previous_day},
                    )
        connection.execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.LEDGER_REFERENCE AS SELECT external_ref FROM MILAAN_DAY_CORE.LEDGER GROUP BY external_ref"
        )
        # This separate arrival oracle is used only by scoring. Matching has no
        # access to it. Cache arrival dates once, then append newly eligible labels.
        if fresh:
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.TRUTH_ARRIVAL AS SELECT g.*,GREATEST(COALESCE(l.posted_date,DATE '1900-01-01'),COALESCE(b.value_date,DATE '1900-01-01'),COALESCE(p.settlement_date,DATE '1900-01-01')) arrival_date FROM MILAAN_CORE.SCORING_TRUTH g LEFT JOIN MILAAN_CORE.LEDGER l ON g.ledger_id=l.ledger_id LEFT JOIN MILAAN_CORE.BANK b ON g.bank_txn_id=b.bank_txn_id LEFT JOIN MILAAN_CORE.PG p ON g.pg_key=p.pg_payment_id"
            )
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.SCORING_TRUTH AS SELECT event_id,ledger_id,bank_txn_id,pg_key,break_type,expected_match FROM MILAAN_DAY_CORE.TRUTH_ARRIVAL WHERE arrival_date<=CAST({day!s} AS DATE)",
                {"day": str(day)},
            )
        elif not same_day:
            connection.execute(
                "INSERT INTO MILAAN_DAY_CORE.SCORING_TRUTH SELECT event_id,ledger_id,bank_txn_id,pg_key,break_type,expected_match FROM MILAAN_DAY_CORE.TRUTH_ARRIVAL WHERE arrival_date>CAST({previous!s} AS DATE) AND arrival_date<=CAST({day!s} AS DATE)",
                {"day": str(day), "previous": previous_day},
            )
        connection.execute("TRUNCATE TABLE MILAAN_DAY_AUDIT.DATASET")
        manifest = json.loads(dataset["MANIFEST"])
        manifest["daily_close"] = {
            "date": str(day),
            "previous_date": previous_day,
            "new_source_counts": new_counts,
            "cumulative_source_rows": total,
        }
        connection.execute(
            "INSERT INTO MILAAN_DAY_AUDIT.DATASET VALUES ({id!s},{label!s},{rows},CAST({day!s} AS DATE),{manifest!s},CURRENT_TIMESTAMP)",
            {
                "id": dataset["DATASET_ID"],
                "label": "Daily close " + str(day),
                "rows": total,
                "day": str(day),
                "manifest": json.dumps(manifest),
            },
        )
        if fresh:
            connection.execute("TRUNCATE TABLE MILAAN_DAY_AUDIT.DAY_STATE")
        connection.commit()
        open_counts = {
            source: connection.execute(
                f"SELECT COUNT(*) N FROM MILAAN_DAY_CORE.OPEN_{source}"
            ).fetchone()["N"]
            for source in OPEN_COLUMNS
        }
        return {
            "date": str(day),
            "new_source_counts": new_counts,
            "cumulative_source_rows": total,
            "fresh": fresh,
            "open_source_counts": open_counts,
        }


def recon_day(day: str, progress=None, restart=False, warmup=True):
    with scope("month"):
        return _recon_day(day, progress, restart, warmup)


def _recon_day(day: str, progress=None, restart=False, warmup=True):
    close_date = date.fromisoformat(day)
    (ROOT / "private").mkdir(exist_ok=True)
    with (ROOT / "private/reconciliation.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another reconciliation is running") from error
        initialise()
        with connect() as connection:
            last = connection.execute("SELECT * FROM MILAAN_DAY_AUDIT.DAY_STATE").fetchone()
            dataset = connection.execute(
                "SELECT dataset_id,manifest FROM MILAAN_AUDIT.DATASET"
            ).fetchone()
        if not dataset:
            raise RuntimeError("Load a dataset first")
        manifest = json.loads(dataset["MANIFEST"])
        if (
            not date.fromisoformat(manifest["start_date"])
            <= close_date
            <= date.fromisoformat(manifest["as_of_date"])
        ):
            raise ValueError("Choose a close date within the loaded dataset's calendar")
        if warmup and (restart or not last or last["DATASET_ID"] != dataset["DATASET_ID"]):
            start = date.fromisoformat(json.loads(dataset["MANIFEST"])["start_date"])
            if close_date > start:
                print("Preparing prior close and its carried open items", flush=True)
                _close(close_date - timedelta(days=1), progress, restart=True)
                restart = False
        return _close(close_date, progress, restart)


def _close(day, progress, restart=False):
    started = perf_counter()
    context = prepare(day, restart)
    prep_seconds = perf_counter() - started
    with scope("day"):
        result = _recon(progress, daily=True, started=started)
        with connect() as connection:
            connection.execute("TRUNCATE TABLE MILAAN_DAY_AUDIT.DAY_STATE")
            connection.execute(
                "INSERT INTO MILAAN_DAY_AUDIT.DAY_STATE SELECT dataset_id,CAST({day!s} AS DATE) FROM MILAAN_AUDIT.DATASET",
                {"day": str(day)},
            )
            connection.commit()
    result["daily"] = {**context, "preparation_seconds": prep_seconds}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    print(json.dumps(recon_day(args.date, restart=args.restart), default=str, indent=2))


if __name__ == "__main__":
    main()
