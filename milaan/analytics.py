import json
import uuid

from milaan.db import connect, query


def summary() -> dict:
    rows = query(
        "SELECT dataset_id,label,source_rows,as_of_date,manifest FROM MILAAN_AUDIT.DATASET"
    )
    if not rows:
        return {}
    result = rows[0]
    result["DAILY"] = json.loads(result.pop("MANIFEST")).get("daily_close", {})
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
    result["LIVE"] = {}
    if result["RUN"]:
        rows = query(
            "SELECT * FROM MILAAN_AUDIT.RUN_LIVE WHERE run_id={id!s}",
            {"id": result["RUN"]["RUN_ID"]},
        )
        result["LIVE"] = rows[0] if rows else {}
    if not result["LIVE"]:
        result["LIVE"] = query(
            "SELECT COALESCE(SUM(amount_paise),0) open_paise,COALESCE(SUM(amount_paise),0) before_paise FROM MILAAN_CORE.LEDGER"
        )[0]
    if result["RUN"]:
        try:
            timings = query(
                "SELECT * FROM MILAAN_AUDIT.DAILY_TIMING WHERE run_id={id!s}",
                {"id": result["RUN"]["RUN_ID"]},
            )
            result["DAILY_TIMING"] = timings[0] if timings else {}
        except Exception:
            result["DAILY_TIMING"] = {}
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
        'WITH page_records AS (SELECT e.*,x.explanation FROM MILAAN_RES."EXCEPTION" e LEFT JOIN MILAAN_RES.EXPLANATION x ON e.exception_id=x.exception_id WHERE '
        + " AND ".join(where)
        + " ORDER BY e.priority_score DESC,e.exception_id LIMIT 50 OFFSET {offset!d}), latest_review AS (SELECT * FROM MILAAN_AUDIT.DECISION QUALIFY ROW_NUMBER() OVER (PARTITION BY run_id,exception_id ORDER BY created_at DESC,decision_id DESC)=1) SELECT p.*,a.decision_action review_action,a.assignee review_assignee FROM page_records p LEFT JOIN latest_review a ON p.exception_id=a.exception_id AND p.run_id=a.run_id ORDER BY p.priority_score DESC,p.exception_id",
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


def batch_evidence(evidence: dict) -> dict:
    if not evidence.get("bank_txn_id") or not evidence.get("pg_payment_id"):
        return {}
    params = {"id": evidence["bank_txn_id"]}
    batches = query(
        "SELECT g.*,b.value_date,b.bank_ref,b.amount_paise bank_credit_paise FROM MILAAN_CORE.BATCH g JOIN MILAAN_CORE.BANK b ON g.batch_id=b.batch_id AND g.settlement_utr=b.bank_ref WHERE b.bank_txn_id={id!s} LIMIT 1",
        params,
    )
    if not batches:
        return {}
    batch = batches[0]
    for key in (
        "NET_PAISE",
        "GROSS_PAISE",
        "FEE_PAISE",
        "GST_PAISE",
        "REFUND_PAISE",
        "PAYMENT_COUNT",
        "BANK_CREDIT_PAISE",
    ):
        batch[key] = int(batch[key])
    batch["PAYMENTS"] = query(
        "SELECT p.pg_payment_id,p.loan_id,p.gross_paise,p.payment_date,CASE WHEN r.pg_payment_id IS NOT NULL THEN 'Matched' ELSE 'Missing in ledger' END receipt_status FROM MILAAN_CORE.PG p LEFT JOIN (SELECT pg_payment_id FROM MILAAN_RES.LINK WHERE bank_txn_id={id!s} GROUP BY pg_payment_id) r ON r.pg_payment_id=p.pg_payment_id WHERE p.settlement_batch_id={batch!s} AND p.settlement_utr={utr!s} AND p.gross_paise>0 ORDER BY p.pg_payment_id LIMIT 50",
        {**params, "batch": batch["BATCH_ID"], "utr": batch["SETTLEMENT_UTR"]},
    )
    batch["MATCHED_RECEIPTS"] = query(
        "SELECT COUNT(DISTINCT ledger_id) N FROM MILAAN_RES.LINK WHERE bank_txn_id={id!s}", params
    )[0]["N"]
    return batch


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


def showcase_id():
    rows = query("SELECT manifest FROM MILAAN_AUDIT.DATASET")
    if not rows:
        return ""
    manifest = json.loads(rows[0]["MANIFEST"])
    selected = manifest.get("showcase_details", {}).get("exception_id")
    if selected:
        return selected
    rows = query(
        "SELECT exception_id FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' LIMIT 1"
    )
    return rows[0]["EXCEPTION_ID"] if rows else ""
