"""Arrival-date closes with independent cumulative matches and carried open items."""

import argparse
import fcntl
import json
from datetime import date, timedelta
from time import perf_counter

from milaan.config import ROOT
from milaan.db import connect, scope, scoped_sql, statements
from milaan.incremental import reconcile_incremental

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
        connection.execute(
            "CREATE TABLE IF NOT EXISTS MILAAN_DAY_AUDIT.DAILY_TIMING (run_id VARCHAR(36),core_seconds DOUBLE,review_seconds DOUBLE,scoring_validation_seconds DOUBLE,total_seconds DOUBLE)"
        )
        connection.commit()


def prepare(day: date, restart=False):
    with connect() as connection:
        connection.execute("ALTER SESSION SET PROFILE='ON'")
        execute = connection.execute

        def profiled(sql, *args, **kwargs):
            return execute(f"/* DAILY_PREPARATION:{day} */ " + sql, *args, **kwargs)

        connection.execute = profiled

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
        if fresh:
            for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
                connection.execute(f'TRUNCATE TABLE MILAAN_DAY_RES."{table}"')
            connection.commit()
        elif same_day:
            # Undo only this date's appended groups; preserve older closed groups.
            previous_run = connection.execute(
                "SELECT run_id FROM MILAAN_DAY_AUDIT.RUN WHERE dataset_id={id!s} AND status='COMPLETE' ORDER BY started_at DESC LIMIT 1",
                {"id": dataset["DATASET_ID"]},
            ).fetchone()
            if previous_run:
                for table in ("LINK", "MATCH_MEMBER"):
                    connection.execute(
                        f'DELETE FROM MILAAN_DAY_RES.{table} WHERE match_id IN (SELECT match_id FROM MILAAN_DAY_RES."MATCH" WHERE run_id={{run!s}})',
                        {"run": previous_run["RUN_ID"]},
                    )
                connection.execute(
                    'DELETE FROM MILAAN_DAY_RES."MATCH" WHERE run_id={run!s}',
                    {"run": previous_run["RUN_ID"]},
                )
        # Views reference the retained closed history; no cumulative copy is made.
        for name, table in (("CLOSED_LINK", "LINK"), ("CLOSED_MEMBER", "MATCH_MEMBER")):
            kind = connection.execute(
                "SELECT table_name FROM EXA_ALL_TABLES WHERE table_schema='MILAAN_DAY_CORE' AND table_name={name!s}",
                {"name": name},
            ).fetchone()
            if kind:
                connection.execute(f"DROP TABLE MILAAN_DAY_CORE.{name}")
            connection.execute(
                f"CREATE OR REPLACE VIEW MILAAN_DAY_CORE.{name} AS SELECT * FROM MILAAN_DAY_RES.{table}"
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
            table = connection.execute(
                "SELECT table_name FROM EXA_ALL_TABLES WHERE table_schema='MILAAN_DAY_CORE' AND table_name={name!s}",
                {"name": source},
            ).fetchone()
            if table:
                connection.execute(f"DROP TABLE MILAAN_DAY_CORE.{source}")
                connection.commit()
            # Immutable monthly sources are already normalised. An arrival view
            # exposes the arrived subset without another cumulative source copy.
            connection.execute(
                f"CREATE OR REPLACE VIEW MILAAN_DAY_CORE.{source} AS SELECT * FROM MILAAN_CORE.{source} WHERE {arrival}<=CAST({{day!s}} AS DATE)",
                {"day": str(day)},
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
                    missing_receipt = (
                        " OR (s.gross_paise>0 AND NOT EXISTS (SELECT 1 FROM MILAAN_DAY_CORE.LEDGER l WHERE l.external_ref=s.payment_ref))"
                        if source == "PG"
                        else ""
                    )
                    connection.execute(
                        f"CREATE OR REPLACE TABLE MILAAN_DAY_CORE.OPEN_{source} AS SELECT {OPEN_COLUMNS[source]} FROM MILAAN_DAY_CORE.{source} s WHERE NOT EXISTS (SELECT 1 FROM MILAAN_DAY_CORE.CLOSED_MEMBER m WHERE m.source_name='{source}' AND m.txn_key=s.{KEYS[source]})"
                        + missing_receipt
                    )
                else:
                    connection.execute(
                        f"INSERT INTO MILAAN_DAY_CORE.OPEN_{source} SELECT {OPEN_COLUMNS[source]} FROM MILAAN_CORE.{source} WHERE {arrival}>CAST({{previous!s}} AS DATE) AND {arrival}<=CAST({{day!s}} AS DATE)",
                        {"day": str(day), "previous": previous_day},
                    )
        table = connection.execute(
            "SELECT table_name FROM EXA_ALL_TABLES WHERE table_schema='MILAAN_DAY_CORE' AND table_name='LEDGER_REFERENCE'"
        ).fetchone()
        if table:
            connection.execute("DROP TABLE MILAAN_DAY_CORE.LEDGER_REFERENCE")
        connection.execute(
            "CREATE OR REPLACE VIEW MILAAN_DAY_CORE.LEDGER_REFERENCE AS SELECT external_ref FROM MILAAN_DAY_CORE.LEDGER"
        )
        connection.execute("TRUNCATE TABLE MILAAN_DAY_AUDIT.DATASET")
        manifest = json.loads(dataset["MANIFEST"])
        manifest["daily_close"] = {
            "date": str(day),
            "previous_date": previous_day,
            "fresh": fresh,
            "same_day": same_day,
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
        connection.execute("ALTER SESSION SET PROFILE='OFF'")
        connection.execute("FLUSH STATISTICS")
        connection.commit()
        profiles = execute(
            "SELECT PART_NAME,PART_INFO,OBJECT_NAME,OBJECT_ROWS,OUT_ROWS,DURATION,CPU FROM EXA_USER_PROFILE_LAST_DAY WHERE SESSION_ID=CURRENT_SESSION AND SQL_TEXT LIKE {tag!s}",
            {"tag": f"%DAILY_PREPARATION:{day}%"},
        ).fetchall()
        return {
            "preparation_profiles": profiles,
            "date": str(day),
            "new_source_counts": new_counts,
            "cumulative_source_rows": total,
            "fresh": fresh,
            "open_source_counts": open_counts,
        }


def score_arrivals(connection):
    """Maintain the independent arrival oracle only after matching has finished."""
    state = json.loads(
        connection.execute("SELECT manifest FROM MILAAN_AUDIT.DATASET").fetchone()["MANIFEST"]
    )["daily_close"]
    day = date.fromisoformat(state["date"])
    previous_day = state["previous_date"]
    fresh, same_day = state["fresh"], state["same_day"]
    # The oracle joins monthly sources explicitly; bypass only the day name mapper.
    execute = connection.connection.execute
    # This separate arrival oracle is used only by scoring. Matching has no
    # access to it. Cache arrival dates once, then append newly eligible labels.
    if fresh:
        execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.TRUTH_ARRIVAL AS SELECT g.*,GREATEST(COALESCE(l.posted_date,DATE '1900-01-01'),COALESCE(b.value_date,DATE '1900-01-01'),COALESCE(p.settlement_date,DATE '1900-01-01')) arrival_date FROM MILAAN_CORE.SCORING_TRUTH g LEFT JOIN MILAAN_CORE.LEDGER l ON g.ledger_id=l.ledger_id LEFT JOIN MILAAN_CORE.BANK b ON g.bank_txn_id=b.bank_txn_id LEFT JOIN MILAAN_CORE.PG p ON g.pg_key=p.pg_payment_id"
        )
        execute(
            "CREATE OR REPLACE TABLE MILAAN_DAY_CORE.SCORING_TRUTH AS SELECT event_id,ledger_id,bank_txn_id,pg_key,break_type,expected_match FROM MILAAN_DAY_CORE.TRUTH_ARRIVAL WHERE arrival_date<=CAST({day!s} AS DATE)",
            {"day": str(day)},
        )
    elif not same_day:
        execute(
            "INSERT INTO MILAAN_DAY_CORE.SCORING_TRUTH SELECT event_id,ledger_id,bank_txn_id,pg_key,break_type,expected_match FROM MILAAN_DAY_CORE.TRUTH_ARRIVAL WHERE arrival_date>CAST({previous!s} AS DATE) AND arrival_date<=CAST({day!s} AS DATE)",
            {"day": str(day), "previous": previous_day},
        )


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
        result = reconcile_incremental(progress, started=started)
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
