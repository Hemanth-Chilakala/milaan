"""Restore a repeatable pre-run view while retaining source data and audit history."""

import fcntl
import uuid
from datetime import date

from milaan import live
from milaan.config import ROOT
from milaan.db import connect, scope


def is_running():
    (ROOT / "private").mkdir(exist_ok=True)
    with (ROOT / "private/reconciliation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def reset_demo(scope_name="month", day="2026-10-14"):
    from milaan.daily import OPEN_COLUMNS, prepare

    with (ROOT / "private/reconciliation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Wait for the current reconciliation to finish") from error
        if scope_name == "day":
            with scope("month"):
                prepare(date.fromisoformat(day))
        with scope(scope_name), connect() as connection:
            if scope_name == "month":
                for source, columns in OPEN_COLUMNS.items():
                    connection.execute(
                        f"CREATE OR REPLACE TABLE MILAAN_CORE.OPEN_{source} AS SELECT {columns} FROM MILAAN_CORE.{source}"
                    )
            for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
                connection.execute(f'TRUNCATE TABLE MILAAN_RES."{table}"')
            if scope_name == "day":
                connection.execute(
                    "INSERT INTO MILAAN_RES.LINK SELECT * FROM MILAAN_CORE.CLOSED_LINK"
                )
                connection.execute(
                    "INSERT INTO MILAAN_RES.MATCH_MEMBER SELECT * FROM MILAAN_CORE.CLOSED_MEMBER"
                )
            run_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO MILAAN_AUDIT.RUN SELECT {id!s},dataset_id,'READY',CURRENT_TIMESTAMP,NULL,NULL,'Demo reset' FROM MILAAN_AUDIT.DATASET",
                {"id": run_id},
            )
            live.begin(connection, run_id, daily=scope_name == "day")
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN_LIVE SET status='READY',current_pass='PREPARATION' WHERE run_id={id!s}",
                {"id": run_id},
            )
            connection.commit()
            return run_id
