"""Append daily matches from persistent open items; audit validation separately."""

import json
import uuid
from time import perf_counter

from milaan import live
from milaan.config import ROOT
from milaan.db import connect, statements


def reconcile_incremental(progress=None, started=None):
    from milaan.pipeline import PASSES, validate

    started = started if started is not None else perf_counter()
    run_id = str(uuid.uuid4())
    times, stage_times = {}, {}
    with connect() as connection:
        dataset = connection.execute(
            "SELECT dataset_id,manifest FROM MILAAN_AUDIT.DATASET"
        ).fetchone()
        previous_date = json.loads(dataset["MANIFEST"])["daily_close"]["previous_date"]
        connection.execute(
            "INSERT INTO MILAAN_AUDIT.RUN VALUES ({run!s},{dataset!s},'RUNNING',CURRENT_TIMESTAMP,NULL,NULL,NULL)",
            {"run": run_id, "dataset": dataset["DATASET_ID"]},
        )
        connection.execute("ALTER SESSION SET PROFILE='ON'")
        try:
            stage_times["ARRIVAL_PREPARATION"] = perf_counter() - started
            work_started = perf_counter()
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_CORE.DELTA_LINK AS SELECT * FROM MILAAN_RES.LINK WHERE 1=0"
            )
            # Preserve only this close's active source sets for batch evidence.
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_CORE.WORK_PG AS SELECT p.* FROM MILAAN_CORE.PG p JOIN MILAAN_CORE.OPEN_PG o ON p.pg_payment_id=o.pg_payment_id"
            )
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_CORE.WORK_BANK AS SELECT * FROM MILAAN_CORE.OPEN_BANK"
            )
            members = live.begin(connection, run_id, daily=True, elapsed=perf_counter() - started)
            old_links = connection.execute("SELECT COUNT(*) N FROM MILAAN_RES.LINK").fetchone()["N"]
            stage_times["ACTIVE_SETS_AND_LIVE_START"] = perf_counter() - work_started
            previous = 0
            for name, filename in PASSES[:-1]:
                if progress:
                    progress(name, None, None)
                live.phase(connection, run_id, name)
                tick = perf_counter()
                for sql in statements(ROOT / "sql" / filename):
                    sql = sql.replace("MILAAN_RES.LINK", "MILAAN_CORE.DELTA_LINK").replace(
                        "MILAAN_CORE.PG ", "MILAAN_CORE.WORK_PG "
                    )
                    # At least one arrival is new. Split groups retain their earlier
                    # components when any bank component for that loan is new.
                    new_pair = "(l.posted_date>CAST({previous!s} AS DATE) OR b.value_date>CAST({previous!s} AS DATE))"
                    if name == "PG_BATCH":
                        sql = sql.replace(
                            "b.bank_txn_id,b.batch_id,b.ref_norm,",
                            "b.bank_txn_id,b.batch_id,b.ref_norm,b.value_date,",
                        )
                        sql = sql.replace(
                            "WHERE b.candidate_count=1",
                            "WHERE (l.posted_date>CAST({previous!s} AS DATE) OR p.settlement_date>CAST({previous!s} AS DATE) OR b.value_date>CAST({previous!s} AS DATE)) AND b.candidate_count=1",
                        )
                    elif name == "FEE_AWARE":
                        new_pair = "(l.posted_date>CAST({previous!s} AS DATE) OR b.value_date>CAST({previous!s} AS DATE) OR p.settlement_date>CAST({previous!s} AS DATE))"
                    elif name == "SPLIT_MERGE":
                        new_pair = "(l.posted_date>CAST({previous!s} AS DATE) OR EXISTS (SELECT 1 FROM MILAAN_CORE.OPEN_BANK arriving WHERE arriving.loan_id=l.loan_id AND arriving.value_date>CAST({previous!s} AS DATE)))"
                    if name != "PG_BATCH":
                        sql = sql.replace(
                            "WHERE l.duplicate_rank=1",
                            "WHERE " + new_pair + " AND l.duplicate_rank=1",
                        )
                    connection.execute(
                        f"/* MILAAN:{run_id}:{name} */ " + sql.replace("@RUN_ID@", run_id),
                        {"previous": previous_date},
                    )
                connection.execute(
                    "CREATE OR REPLACE TABLE MILAAN_CORE.PASS_LINK AS SELECT ledger_id,bank_txn_id,pg_payment_id FROM MILAAN_CORE.DELTA_LINK WHERE pass_name={name!s}",
                    {"name": name},
                )
                for source, key in [("LEDGER", "ledger_id"), ("BANK", "bank_txn_id")] + (
                    [("PG", "pg_payment_id")] if name in {"PG_BATCH", "FEE_AWARE"} else []
                ):
                    connection.execute(
                        f"DELETE FROM MILAAN_CORE.OPEN_{source} o WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.PASS_LINK x WHERE x.{key}=o.{key})"
                    )
                connection.commit()
                seconds = perf_counter() - tick
                count = connection.execute(
                    "SELECT COUNT(*) N FROM MILAAN_CORE.DELTA_LINK"
                ).fetchone()["N"]
                added = count - previous
                connection.execute(
                    "INSERT INTO MILAAN_AUDIT.PASS_TIMING VALUES ({run!s},{name!s},{seconds},{added},NULL)",
                    {"run": run_id, "name": name, "seconds": seconds, "added": added},
                )
                members += live.pass_members(connection, name, added, active=True)
                live.update(
                    connection, run_id, perf_counter() - started, members, old_links + count
                )
                times[name] = seconds
                previous = count
                print(f"{name}: {added:,} links, {seconds:.3f}s", flush=True)
                if progress:
                    progress(name, seconds, added)
            tick = perf_counter()
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_CORE.DELTA_MEMBER AS SELECT * FROM MILAAN_RES.MATCH_MEMBER WHERE 1=0"
            )
            for sql in statements(ROOT / "sql/40_results.sql"):
                connection.execute(
                    f"/* MILAAN:{run_id}:RESULTS */ "
                    + sql.replace("MILAAN_RES.LINK", "MILAAN_CORE.DELTA_LINK")
                    .replace("MILAAN_RES.MATCH_MEMBER", "MILAAN_CORE.DELTA_MEMBER")
                    .replace("MILAAN_CORE.BANK ", "MILAAN_CORE.WORK_BANK ")
                    .replace("MILAAN_CORE.PG ", "MILAAN_CORE.WORK_PG ")
                    .replace("@RUN_ID@", run_id)
                )
            connection.execute(
                "INSERT INTO MILAAN_RES.MATCH_MEMBER SELECT * FROM MILAAN_CORE.DELTA_MEMBER"
            )
            connection.execute("INSERT INTO MILAAN_RES.LINK SELECT * FROM MILAAN_CORE.DELTA_LINK")
            # A batch closes every bank-backed gateway member, including refund
            # lines and a receipt missing from the ledger. Carry that review item
            # separately, rather than re-aggregating the closed batch next day.
            connection.execute(
                "DELETE FROM MILAAN_CORE.OPEN_PG p WHERE EXISTS (SELECT 1 FROM MILAAN_CORE.DELTA_MEMBER m WHERE m.source_name='PG' AND m.txn_key=p.pg_payment_id)"
            )
            connection.commit()
            stage_times["RESULTS"] = perf_counter() - tick
            matching_before_review = perf_counter() - started
            # Review generation inspects active rows. Historical matches remain append-only.
            tick = perf_counter()
            if progress:
                progress("CLASSIFY", None, None)
            live.phase(connection, run_id, "CLASSIFY")
            connection.execute(
                "CREATE OR REPLACE TABLE MILAAN_CORE.CARRIED_PG_REVIEW AS SELECT * FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER'"
            )
            connection.execute('TRUNCATE TABLE MILAAN_RES."EXCEPTION"')
            connection.execute("TRUNCATE TABLE MILAAN_RES.EXPLANATION")
            for sql in statements(ROOT / "sql/36_classify.sql"):
                sql = sql.replace("MILAAN_CORE.BANK ", "MILAAN_CORE.WORK_BANK ").replace(
                    "MILAAN_CORE.PG ", "MILAAN_CORE.WORK_PG "
                )
                connection.execute(
                    f"/* MILAAN:{run_id}:CLASSIFY */ " + sql.replace("@RUN_ID@", run_id)
                )
            connection.execute(
                'INSERT INTO MILAAN_RES."EXCEPTION" SELECT r.exception_id,{run!s},r.source_name,r.txn_key,r.category,r.loan_id,r.channel,r.amount_paise,GREATEST(0,c.business_day_index-p.day_index),r.risk_weight,r.amount_paise/100.0*GREATEST(c.business_day_index-p.day_index,1)*r.risk_weight,r.suggested_action,r.evidence FROM MILAAN_CORE.CARRIED_PG_REVIEW r JOIN MILAAN_CORE.PG p ON p.pg_payment_id=r.txn_key CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date WHERE NOT EXISTS (SELECT 1 FROM MILAAN_RES."EXCEPTION" e WHERE e.exception_id=r.exception_id)',
                {"run": run_id},
            )
            connection.commit()
            review_seconds = perf_counter() - tick
            times["CLASSIFY"] = review_seconds
            core_seconds = matching_before_review + review_seconds
            connection.execute(
                "INSERT INTO MILAAN_AUDIT.PASS_TIMING VALUES ({run!s},'CLASSIFY',{seconds},0,NULL)",
                {"run": run_id, "seconds": review_seconds},
            )
            if progress:
                progress("CLASSIFY", review_seconds, 0)
            tick = perf_counter()
            from milaan.daily import score_arrivals

            score_arrivals(connection)
            live.phase(connection, run_id, "SCORING")
            connection.execute("TRUNCATE TABLE MILAAN_RES.SCORE")
            for sql in statements(ROOT / "sql/50_score.sql"):
                connection.execute(
                    f"/* MILAAN:{run_id}:SCORING */ " + sql.replace("@RUN_ID@", run_id)
                )
            validate(connection, run_id)
            actual = connection.execute(
                "SELECT COUNT(*) N FROM MILAAN_RES.MATCH_MEMBER"
            ).fetchone()["N"]
            if actual != members:
                raise RuntimeError(f"Live memberships disagree: {members} vs {actual}")
            connection.commit()
            scoring_seconds = perf_counter() - tick
            total = perf_counter() - started
            connection.execute(
                "INSERT INTO MILAAN_AUDIT.DAILY_TIMING VALUES ({run!s},{core},{review},{scoring},{total})",
                {
                    "run": run_id,
                    "core": core_seconds,
                    "review": review_seconds,
                    "scoring": scoring_seconds,
                    "total": total,
                },
            )
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN SET status='COMPLETE',finished_at=CURRENT_TIMESTAMP,seconds={total} WHERE run_id={run!s}",
                {"total": total, "run": run_id},
            )
            live.update(connection, run_id, total, members, old_links + previous, "COMPLETE")
            connection.execute("ALTER SESSION SET PROFILE='OFF'")
            connection.execute("FLUSH STATISTICS")
            connection.commit()
            for name, _ in PASSES:
                rows = connection.execute(
                    "SELECT PART_NAME,PART_INFO,OBJECT_NAME,OBJECT_ROWS,OUT_ROWS,DURATION,CPU FROM EXA_USER_PROFILE_LAST_DAY WHERE SESSION_ID=CURRENT_SESSION AND SQL_TEXT LIKE {tag!s}",
                    {"tag": f"%MILAAN:{run_id}:{name}%"},
                ).fetchall()
                connection.execute(
                    "UPDATE MILAAN_AUDIT.PASS_TIMING SET profile_json={profile!s} WHERE run_id={run!s} AND pass_name={name!s}",
                    {"profile": json.dumps(rows, default=str), "run": run_id, "name": name},
                )
            connection.commit()
            score = connection.execute(
                "SELECT * FROM MILAAN_RES.SCORE WHERE break_type='OVERALL'"
            ).fetchone()
            return dict(
                run_id=run_id,
                seconds=total,
                core_matching_seconds=core_seconds,
                review_seconds=review_seconds,
                scoring_validation_seconds=scoring_seconds,
                total_seconds=total,
                passes=times,
                stage_times=stage_times,
                score=score,
            )
        except Exception as error:
            connection.rollback()
            connection.execute(
                "UPDATE MILAAN_AUDIT.RUN SET status='FAILED',finished_at=CURRENT_TIMESTAMP,message={message!s} WHERE run_id={run!s}",
                {"message": str(error)[:2000], "run": run_id},
            )
            connection.commit()
            raise
