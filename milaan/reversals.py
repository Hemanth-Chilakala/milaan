"""Exclude cancelled credits and reopen groups cancelled by a later arrival."""

from milaan.config import ROOT
from milaan.db import execute_file


def prepare(connection, daily=False):
    execute_file(connection, ROOT / "sql/25_bank_reversals.sql")
    if not daily:
        return
    connection.execute(
        "CREATE OR REPLACE TABLE MILAAN_CORE.REVERSED_GROUP AS SELECT DISTINCT m.match_id FROM MILAAN_RES.MATCH_MEMBER m JOIN MILAAN_CORE.BANK_REVERSAL r ON m.source_name='BANK' AND m.txn_key=r.credit_id"
    )
    connection.execute(
        "CREATE OR REPLACE TABLE MILAAN_CORE.REOPEN_MEMBER AS SELECT m.* FROM MILAAN_RES.MATCH_MEMBER m JOIN MILAAN_CORE.REVERSED_GROUP g ON g.match_id=m.match_id"
    )
    for table in ("LINK", "MATCH_MEMBER", '"MATCH"'):
        connection.execute(
            f"DELETE FROM MILAAN_RES.{table} m WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.REVERSED_GROUP g WHERE g.match_id=m.match_id)"
        )
    from milaan.daily import KEYS, OPEN_COLUMNS

    for source, columns in OPEN_COLUMNS.items():
        key = KEYS[source]
        connection.execute(
            f"INSERT INTO MILAAN_CORE.OPEN_{source} SELECT {columns} FROM MILAAN_CORE.{source} s WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.REOPEN_MEMBER m WHERE m.source_name='{source}' AND m.txn_key=s.{key}) AND NOT EXISTS (SELECT 1 FROM MILAAN_CORE.OPEN_{source} o WHERE o.{key}=s.{key})"
        )
    # Reopened groups can contain the cancelled bank line itself.
    connection.execute(
        "DELETE FROM MILAAN_CORE.OPEN_BANK b WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.BANK_REVERSAL r WHERE r.credit_id=b.bank_txn_id OR r.debit_id=b.bank_txn_id)"
    )
