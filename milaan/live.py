"""Persist small progress snapshots; the dashboard never polls transaction tables."""

from time import time


def begin(connection, run_id, daily=False, elapsed=0):
    members = 0
    links = 0
    if daily:
        members = connection.execute("SELECT COUNT(*) N FROM MILAAN_CORE.CLOSED_MEMBER").fetchone()[
            "N"
        ]
        links = connection.execute("SELECT COUNT(*) N FROM MILAAN_CORE.CLOSED_LINK").fetchone()["N"]
    before = connection.execute(
        "SELECT COALESCE(SUM(amount_paise),0) N FROM MILAAN_CORE.OPEN_LEDGER"
    ).fetchone()["N"]
    rows = connection.execute("SELECT source_rows FROM MILAAN_AUDIT.DATASET").fetchone()[
        "SOURCE_ROWS"
    ]
    connection.execute(
        "INSERT INTO MILAAN_AUDIT.RUN_LIVE VALUES ({id!s},'RUNNING','PREPARATION',{epoch},0,{links},{members},{rows},{before},{before},{epoch})",
        {
            "id": run_id,
            "epoch": int((time() - elapsed) * 1000),
            "links": links,
            "members": members,
            "rows": rows,
            "before": before,
        },
    )
    connection.commit()
    return members


def phase(connection, run_id, name):
    connection.execute(
        "UPDATE MILAAN_AUDIT.RUN_LIVE SET current_pass={name!s},updated_epoch_ms={epoch} WHERE run_id={id!s}",
        {"id": run_id, "name": name, "epoch": int(time() * 1000)},
    )
    connection.commit()


def pass_members(connection, name, links):
    if name == "CLASSIFY":
        return 0
    if name == "PG_BATCH":
        row = connection.execute(
            "SELECT (SELECT COUNT(DISTINCT ledger_id) FROM MILAAN_CORE.PASS_LINK)+(SELECT COUNT(DISTINCT bank_txn_id) FROM MILAAN_CORE.PASS_LINK)+(SELECT COUNT(*) FROM MILAAN_CORE.PG p WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.PASS_LINK x JOIN MILAAN_CORE.BANK b ON x.bank_txn_id=b.bank_txn_id WHERE b.batch_id=p.settlement_batch_id AND b.bank_ref=p.settlement_utr)) N"
        ).fetchone()
        return int(row["N"])
    if name == "SPLIT_MERGE":
        return (
            links
            + connection.execute(
                "SELECT COUNT(DISTINCT ledger_id) N FROM MILAAN_CORE.PASS_LINK"
            ).fetchone()["N"]
        )
    return links * (3 if name == "FEE_AWARE" else 2)


def update(connection, run_id, elapsed, members, links, status="RUNNING"):
    amount = connection.execute(
        "SELECT COALESCE(SUM(amount_paise),0) N FROM MILAAN_CORE.OPEN_LEDGER"
    ).fetchone()["N"]
    connection.execute(
        "UPDATE MILAAN_AUDIT.RUN_LIVE SET status={status!s},elapsed_seconds={elapsed},members={members},links_found={links},open_paise={amount},updated_epoch_ms={epoch} WHERE run_id={id!s}",
        {
            "id": run_id,
            "status": status,
            "elapsed": elapsed,
            "members": members,
            "links": links,
            "amount": amount,
            "epoch": int(time() * 1000),
        },
    )
    connection.commit()


def snapshot(connection=None):
    from milaan.db import query

    def read(sql, params=None):
        return (
            connection.execute(sql, params or {}).fetchall() if connection else query(sql, params)
        )

    rows = read(
        "SELECT p.* FROM MILAAN_AUDIT.RUN_LIVE p JOIN MILAAN_AUDIT.RUN r ON p.run_id=r.run_id JOIN MILAAN_AUDIT.DATASET d ON r.dataset_id=d.dataset_id ORDER BY r.started_at DESC LIMIT 1"
    )
    if not rows:
        if connection:
            connection.commit()
        return {}
    result = rows[0]
    result["PASSES"] = read(
        "SELECT pass_name,seconds,links_added FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={id!s}",
        {"id": result["RUN_ID"]},
    )
    if connection:
        connection.commit()
    return result
