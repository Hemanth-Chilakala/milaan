import argparse
import fcntl
import json
import uuid
from pathlib import Path
from time import perf_counter

from milaan import live
from milaan.config import ROOT
from milaan.db import connect, execute_file, statements

SOURCES = {
    "ledger": "MILAAN_STG.LEDGER",
    "bank_statement": "MILAAN_STG.BANK_STATEMENT",
    "pg_settlement": "MILAAN_STG.PG_SETTLEMENT",
    "nach_returns": "MILAAN_STG.NACH_RETURNS",
    "ground_truth": "MILAAN_STG.GROUND_TRUTH",
    "calendar": "MILAAN_CORE.CALENDAR",
}


def setup() -> None:
    with connect() as connection:
        execute_file(connection, ROOT / "sql/00_schema.sql")
        for file in sorted((ROOT / "udf").glob("*.sql")):
            execute_file(connection, file)
        connection.commit()
        print("Exasol schemas and UDFs ready.", flush=True)


def load(folder: Path, progress=None) -> dict:
    (ROOT / "private").mkdir(exist_ok=True)
    with (ROOT / "private/reconciliation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another reconciliation or load is running") from error
        return _load(folder, progress)


def _load(folder: Path, progress=None) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text())
    dataset_id = str(uuid.uuid4())
    times = {}
    with connect() as connection:
        connection.execute("TRUNCATE TABLE MILAAN_AUDIT.DATASET")
        connection.commit()
        for name, table in SOURCES.items():
            connection.execute(f"TRUNCATE TABLE {table}")
            started = perf_counter()
            connection.import_from_file(
                folder / f"{name}.csv", tuple(table.split(".")), import_params={"skip": 1}
            )
            elapsed = perf_counter() - started
            count = connection.execute(f"SELECT COUNT(*) AS N FROM {table}").fetchone()["N"]
            if count != manifest["source_counts"][name]:
                raise RuntimeError(f"Row-count mismatch for {name}")
            connection.execute(
                "INSERT INTO MILAAN_AUDIT.RUN_LOG VALUES ({run!s},'LOAD',{file!s},{count},{seconds},CURRENT_TIMESTAMP)",
                {"run": dataset_id, "file": name, "count": count, "seconds": elapsed},
            )
            connection.commit()
            times[name] = elapsed
            print(f"Loaded {name}: {count:,} rows in {elapsed:.3f}s", flush=True)
            if progress:
                progress(name, elapsed, count)
        # A new dataset invalidates current reconciliation results, not decision history.
        for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
            connection.execute(f'TRUNCATE TABLE MILAAN_RES."{table}"')
        # Commit each replacement so the previous table version can be reclaimed
        # within the small local database volume, instead of retaining all versions.
        for statement in statements(ROOT / "sql/20_normalise.sql"):
            connection.execute(statement)
            connection.commit()
        connection.execute("TRUNCATE TABLE MILAAN_AUDIT.DATASET")
        connection.execute(
            "INSERT INTO MILAAN_AUDIT.DATASET VALUES ({id!s},{label!s},{rows},CAST({asof!s} AS DATE),{manifest!s},CURRENT_TIMESTAMP)",
            {
                "id": dataset_id,
                "label": folder.name,
                "rows": manifest["source_rows"],
                "asof": manifest["as_of_date"],
                "manifest": json.dumps(manifest),
            },
        )
        connection.commit()
    return times


PASSES = [
    ("EXACT", "30_pass_exact.sql"),
    ("PG_BATCH", "31_pass_pg_batch.sql"),
    ("FEE_AWARE", "32_pass_fee_aware.sql"),
    ("TOLERANT", "33_pass_tolerant.sql"),
    ("FUZZY", "34_pass_fuzzy.sql"),
    ("SPLIT_MERGE", "35_pass_split_merge.sql"),
    ("CLASSIFY", "36_classify.sql"),
]


def validate(connection, run_id: str | None = None) -> None:
    tag = f"/* MILAAN:{run_id}:VALIDATION */ " if run_id else ""
    conflicts = connection.execute(
        tag
        + "SELECT COUNT(*) N FROM (SELECT source_name,txn_key FROM MILAAN_RES.MATCH_MEMBER GROUP BY source_name,txn_key HAVING MIN(match_id)<>MAX(match_id))"
    ).fetchone()["N"]
    if conflicts:
        raise RuntimeError(f"{conflicts} records belong to conflicting match groups")
    empty = connection.execute(
        tag + 'SELECT COUNT(*) N FROM MILAAN_RES."MATCH" WHERE rule IS NULL OR evidence IS NULL'
    ).fetchone()["N"]
    if empty:
        raise RuntimeError("Unexplained matches detected")


def recon(progress=None) -> dict:
    (ROOT / "private").mkdir(exist_ok=True)
    with (ROOT / "private/reconciliation.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another reconciliation is running") from error
        return _recon(progress)


def _recon(progress=None, daily=False, started=None) -> dict:
    run_id = str(uuid.uuid4())
    times = {}
    stage_times = {}
    started = started if started is not None else perf_counter()
    with connect() as connection:
        dataset = connection.execute("SELECT dataset_id FROM MILAAN_AUDIT.DATASET").fetchone()
        if not dataset:
            raise RuntimeError("Load a dataset before reconciliation")
        connection.execute(
            "INSERT INTO MILAAN_AUDIT.RUN VALUES ({id!s},{dataset!s},'RUNNING',CURRENT_TIMESTAMP,NULL,NULL,NULL)",
            {"id": run_id, "dataset": dataset["DATASET_ID"]},
        )
        connection.commit()
        try:
            for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
                connection.execute(f'TRUNCATE TABLE MILAAN_RES."{table}"')
            connection.execute("ALTER SESSION SET PROFILE='ON'")
            tick = perf_counter()
            # Reset automatic result indexes; matching does not query old edges.
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_RES.LINK AS SELECT * FROM MILAAN_RES.LINK WHERE 1=0"
            )
            open_columns = {
                "LEDGER": "ledger_id,loan_id,amount_paise,channel,external_ref,posted_date,status,ref_norm,name_norm,day_index,duplicate_rank,ref_suffix8",
                "BANK": "bank_txn_id,value_date,bank_ref,amount_paise,ref_norm,loan_id,batch_id,channel,name_norm,day_index,ref_suffix8",
                "PG": "pg_payment_id,gross_paise,fee_paise,gst_on_fee_paise,net_paise,settlement_batch_id,settlement_date,settlement_utr,loan_id,payment_ref",
            }
            for source, columns in [] if daily else open_columns.items():
                # These tables are subsets of immutable normalised sources.
                # A full row count means load already prepared them. Reruns
                # restore removed records, and include that cost in the timer.
                counts = connection.execute(
                    f"SELECT (SELECT COUNT(*) FROM MILAAN_CORE.OPEN_{source}) N,(SELECT COUNT(*) FROM MILAAN_CORE.{source}) TOTAL"
                ).fetchone()
                if counts["N"] != counts["TOTAL"]:
                    connection.execute(
                        f"/* MILAAN:{run_id}:PREPARATION */ CREATE OR REPLACE TABLE MILAAN_CORE.OPEN_{source} AS SELECT {columns} FROM MILAAN_CORE.{source}"
                    )
            from milaan.reversals import prepare as prepare_reversals

            prepare_reversals(connection)
            stage_times["PREPARATION"] = perf_counter() - tick
            members = live.begin(connection, run_id, daily, perf_counter() - started)
            previous = 0
            for name, filename in PASSES:
                if daily and name == "CLASSIFY":
                    connection.execute(
                        "INSERT INTO MILAAN_RES.LINK SELECT * FROM MILAAN_CORE.CLOSED_LINK"
                    )
                    previous = connection.execute(
                        "SELECT COUNT(*) N FROM MILAAN_RES.LINK"
                    ).fetchone()["N"]
                if progress:
                    progress(name, None, None)
                live.phase(connection, run_id, name)
                tick = perf_counter()
                for sql in statements(ROOT / "sql" / filename):
                    connection.execute(
                        f"/* MILAAN:{run_id}:{name} */\n" + sql.replace("@RUN_ID@", run_id)
                    )
                if name != "CLASSIFY":
                    connection.execute(
                        f"/* MILAAN:{run_id}:{name} */ CREATE OR REPLACE TABLE MILAAN_CORE.PASS_LINK AS SELECT ledger_id,bank_txn_id,pg_payment_id FROM MILAAN_RES.LINK WHERE pass_name={{name!s}}",
                        {"name": name},
                    )
                    # Shrinking uses only this pass's edges, never the growing history.
                    sources = [("LEDGER", "ledger_id"), ("BANK", "bank_txn_id")]
                    if name in {"PG_BATCH", "FEE_AWARE"}:
                        sources.append(("PG", "pg_payment_id"))
                    for source, key in sources:
                        connection.execute(
                            f"/* MILAAN:{run_id}:{name} */ DELETE FROM MILAAN_CORE.OPEN_{source} o WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.PASS_LINK x WHERE x.{key}=o.{key})"
                        )
                connection.commit()
                seconds = perf_counter() - tick
                count = connection.execute("SELECT COUNT(*) N FROM MILAAN_RES.LINK").fetchone()["N"]
                connection.execute(
                    "INSERT INTO MILAAN_AUDIT.PASS_TIMING VALUES ({id!s},{name!s},{seconds},{count},NULL)",
                    {"id": run_id, "name": name, "seconds": seconds, "count": count - previous},
                )
                connection.commit()
                times[name] = seconds
                members += live.pass_members(connection, name, count - previous)
                live.update(connection, run_id, perf_counter() - started, members, count)
                print(f"{name}: {count - previous:,} links, {seconds:.3f}s", flush=True)
                if progress:
                    progress(name, seconds, count - previous)
                previous = count
            for filename in ("40_results.sql", "50_score.sql"):
                stage = "RESULTS" if filename.startswith("40_") else "SCORING"
                live.phase(connection, run_id, stage)
                tick = perf_counter()
                for sql in statements(ROOT / "sql" / filename):
                    connection.execute(
                        f"/* MILAAN:{run_id}:{stage} */\n" + sql.replace("@RUN_ID@", run_id)
                    )
                stage_times[stage] = perf_counter() - tick
            tick = perf_counter()
            validate(connection, run_id)
            actual_members = connection.execute(
                "SELECT COUNT(*) N FROM MILAAN_RES.MATCH_MEMBER"
            ).fetchone()["N"]
            if members != actual_members:
                raise RuntimeError("Live membership totals disagree with final match groups")
            stage_times["VALIDATION"] = perf_counter() - tick
            elapsed = perf_counter() - started
            live.update(connection, run_id, elapsed, members, previous, "COMPLETE")
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN SET status='COMPLETE',finished_at=CURRENT_TIMESTAMP,seconds={seconds} WHERE run_id={id!s}",
                {"seconds": elapsed, "id": run_id},
            )
            connection.commit()
            profile_started = perf_counter()
            connection.execute("ALTER SESSION SET PROFILE='OFF'")
            connection.execute("FLUSH STATISTICS")
            connection.commit()
            stage_profiles = {}
            for name in [name for name, _ in PASSES] + [
                "PREPARATION",
                "RESULTS",
                "SCORING",
                "VALIDATION",
            ]:
                rows = connection.execute(
                    "SELECT STMT_ID,PART_ID,PART_NAME,PART_INFO,OBJECT_NAME,OBJECT_ROWS,OUT_ROWS,DURATION,CPU,TEMP_DB_RAM_PEAK,HDD_READ,HDD_WRITE,NET,REMARKS FROM EXA_USER_PROFILE_LAST_DAY WHERE SESSION_ID=CURRENT_SESSION AND SQL_TEXT LIKE {tag!s}",
                    {"tag": f"%MILAAN:{run_id}:{name}%"},
                ).fetchall()
                if name in {"PREPARATION", "RESULTS", "SCORING", "VALIDATION"}:
                    stage_profiles[name] = rows
                    continue
                connection.execute(
                    "UPDATE MILAAN_AUDIT.PASS_TIMING SET profile_json={profile!s} WHERE run_id={id!s} AND pass_name={name!s}",
                    {"profile": json.dumps(rows, default=str), "id": run_id, "name": name},
                )
            connection.commit()
            scores = connection.execute(
                "SELECT * FROM MILAAN_RES.SCORE WHERE break_type='OVERALL'"
            ).fetchone()
            print(
                json.dumps({"run_id": run_id, "seconds": elapsed, "score": scores}, default=str),
                flush=True,
            )
            return {
                "run_id": run_id,
                "seconds": elapsed,
                "passes": times,
                "score": scores,
                "stage_times": stage_times,
                "stage_profiles": stage_profiles,
                "profile_collection_seconds": perf_counter() - profile_started,
            }
        except Exception as error:
            connection.rollback()
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN_LIVE SET status='FAILED' WHERE run_id={id!s}",
                {"id": run_id},
            )
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN SET status='FAILED',finished_at=CURRENT_TIMESTAMP,message={message!s} WHERE run_id={id!s}",
                {"id": run_id, "message": str(error)[:2000]},
            )
            connection.commit()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Milaan Exasol pipeline")
    parser.add_argument("command", choices=["setup", "load", "recon", "score"])
    parser.add_argument("--data", type=Path, default=ROOT / "data/1m")
    args = parser.parse_args()
    if args.command == "setup":
        setup()
    elif args.command == "load":
        load(args.data)
    elif args.command == "recon":
        recon()
    else:
        with connect() as connection:
            print(
                json.dumps(
                    connection.execute("SELECT * FROM MILAAN_RES.SCORE").fetchall(),
                    default=str,
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
