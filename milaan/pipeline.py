import argparse
import fcntl
import json
import uuid
from pathlib import Path
from time import perf_counter

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
    manifest = json.loads((folder / "manifest.json").read_text())
    dataset_id = str(uuid.uuid4())
    times = {}
    with connect() as connection:
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
        # A new dataset invalidates current reconciliation results, not decision history.
        for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
            connection.execute(f'TRUNCATE TABLE MILAAN_RES."{table}"')
        execute_file(connection, ROOT / "sql/20_normalise.sql")
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


def validate(connection) -> None:
    conflicts = connection.execute(
        "SELECT COUNT(*) N FROM (SELECT source_name,txn_key FROM MILAAN_RES.MATCH_MEMBER GROUP BY source_name,txn_key HAVING COUNT(DISTINCT match_id)>1)"
    ).fetchone()["N"]
    if conflicts:
        raise RuntimeError(f"{conflicts} records belong to conflicting match groups")
    empty = connection.execute(
        'SELECT COUNT(*) N FROM MILAAN_RES."MATCH" WHERE rule IS NULL OR evidence IS NULL'
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


def _recon(progress=None) -> dict:
    run_id = str(uuid.uuid4())
    times = {}
    started = perf_counter()
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
            previous = 0
            for name, filename in PASSES:
                if progress:
                    progress(name, None, None)
                tick = perf_counter()
                for sql in statements(ROOT / "sql" / filename):
                    connection.execute(
                        f"/* MILAAN:{run_id}:{name} */\n" + sql.replace("@RUN_ID@", run_id)
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
                print(f"{name}: {count - previous:,} links, {seconds:.3f}s", flush=True)
                if progress:
                    progress(name, seconds, count - previous)
                previous = count
            for filename in ("40_results.sql", "50_score.sql"):
                for sql in statements(ROOT / "sql" / filename):
                    connection.execute(sql.replace("@RUN_ID@", run_id))
            validate(connection)
            elapsed = perf_counter() - started
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN SET status='COMPLETE',finished_at=CURRENT_TIMESTAMP,seconds={seconds} WHERE run_id={id!s}",
                {"seconds": elapsed, "id": run_id},
            )
            connection.commit()
            connection.execute("ALTER SESSION SET PROFILE='OFF'")
            connection.execute("FLUSH STATISTICS")
            connection.commit()
            for name, _ in PASSES:
                rows = connection.execute(
                    "SELECT PART_NAME,OBJECT_ROWS,OUT_ROWS,DURATION,CPU,TEMP_DB_RAM_PEAK,HDD_READ,HDD_WRITE,NET FROM EXA_USER_PROFILE_LAST_DAY WHERE SESSION_ID=CURRENT_SESSION AND SQL_TEXT LIKE {tag!s}",
                    {"tag": f"%MILAAN:{run_id}:{name}%"},
                ).fetchall()
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
            return {"run_id": run_id, "seconds": elapsed, "passes": times, "score": scores}
        except Exception as error:
            connection.rollback()
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
