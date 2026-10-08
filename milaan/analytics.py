import uuid

from milaan.db import connect, query


def summary() -> dict:
    rows = query("SELECT dataset_id,label,source_rows,as_of_date FROM MILAAN_AUDIT.DATASET")
    if not rows:
        return {}
    result = rows[0]
    result.update(
        query(
            'SELECT COUNT(*) EXCEPTIONS,COALESCE(SUM(amount_paise),0) OPEN_PAISE FROM MILAAN_RES."EXCEPTION"'
        )[0]
    )
    result["MEMBERS"] = query("SELECT COUNT(*) N FROM MILAAN_RES.MATCH_MEMBER")[0]["N"]
    latest = query(
        "SELECT * FROM MILAAN_AUDIT.RUN WHERE dataset_id={dataset!s} ORDER BY started_at DESC LIMIT 1",
        {"dataset": result["DATASET_ID"]},
    )
    result["RUN"] = latest[0] if latest else None
    return result


def exceptions(category="All", channel="All", age="All", amount="All", offset=0) -> list:
    if int(offset) < 0:
        raise ValueError("Page offset must be nonnegative")
    where, params = ["1=1"], {"offset": int(offset)}
    if category != "All":
        where.append("e.category={category!s}")
        params["category"] = category
    if channel != "All":
        where.append("e.channel={channel!s}")
        params["channel"] = channel
    ages = {
        "0–1": "BETWEEN 0 AND 1",
        "2–3": "BETWEEN 2 AND 3",
        "4–7": "BETWEEN 4 AND 7",
        "8+": ">7",
    }
    if age in ages:
        where.append("e.age_business_days " + ages[age])
    bands = {
        "Below ₹10,000": "<1000000",
        "₹10,000–₹25,000": "BETWEEN 1000000 AND 2500000",
        "Above ₹25,000": ">2500000",
    }
    if amount in bands:
        where.append("e.amount_paise " + bands[amount])
    return query(
        'SELECT e.*,x.explanation FROM MILAAN_RES."EXCEPTION" e LEFT JOIN MILAAN_RES.EXPLANATION x ON e.exception_id=x.exception_id WHERE '
        + " AND ".join(where)
        + " ORDER BY e.priority_score DESC,e.exception_id LIMIT 50 OFFSET {offset!d}",
        params,
    )


def detail(exception_id: str) -> dict:
    rows = query(
        'SELECT e.*,x.explanation FROM MILAAN_RES."EXCEPTION" e LEFT JOIN MILAAN_RES.EXPLANATION x ON e.exception_id=x.exception_id WHERE e.exception_id={id!s}',
        {"id": exception_id},
    )
    return rows[0] if rows else {}


def evidence_records(evidence: dict) -> dict:
    records = {}
    for label, table, key in (
        ("Ledger", "LEDGER", "ledger_id"),
        ("Bank", "BANK_STATEMENT", "bank_txn_id"),
        ("Gateway", "PG_SETTLEMENT", "pg_payment_id"),
    ):
        if evidence.get(key):
            records[label] = query(
                f"SELECT * FROM MILAAN_STG.{table} WHERE {key}={{id!s}} LIMIT 1",
                {"id": evidence[key]},
            )
    if evidence.get("loan_id"):
        records["NACH"] = query(
            "SELECT * FROM MILAAN_STG.NACH_RETURNS WHERE loan_id={id!s} LIMIT 3",
            {"id": evidence["loan_id"]},
        )
    return records


def decision(exception_id: str, action: str, analyst: str, assignee: str, note: str) -> str:
    if action not in {"ACCEPT", "REJECT", "ASSIGN"} or not analyst.strip():
        raise ValueError("Choose a valid decision and identify the analyst")
    identifier = str(uuid.uuid4())
    with connect() as connection:
        row = connection.execute(
            'SELECT run_id FROM MILAAN_RES."EXCEPTION" WHERE exception_id={id!s}',
            {"id": exception_id},
        ).fetchone()
        if not row:
            raise ValueError("This exception is no longer in the current run; refresh the queue")
        connection.execute(
            "INSERT INTO MILAAN_AUDIT.DECISION VALUES ({id!s},{run!s},{exception!s},{action!s},{analyst!s},{assignee!s},{note!s},CURRENT_TIMESTAMP)",
            {
                "id": identifier,
                "run": row["RUN_ID"],
                "exception": exception_id,
                "action": action,
                "analyst": analyst.strip(),
                "assignee": assignee,
                "note": note,
            },
        )
        connection.commit()
    return identifier
