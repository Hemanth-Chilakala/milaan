import argparse
import json
import uuid
from pathlib import Path
from time import perf_counter

from milaan.config import ROOT
from milaan.db import connect, execute_file

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Milaan Exasol pipeline")
    parser.add_argument("command", choices=["setup", "load"])
    parser.add_argument("--data", type=Path, default=ROOT / "data/1m")
    args = parser.parse_args()
    if args.command == "setup":
        setup()
    else:
        load(args.data)


if __name__ == "__main__":
    main()
