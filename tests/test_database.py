"""Database integration checks replace current demo tables with a seeded fixture."""

import csv
import json
import random
from datetime import date, timedelta

import pytest

from generator.generate import generate, load_config
from milaan.analytics import decision, detail
from milaan.config import ROOT
from milaan.db import connect, query, statements
from milaan.explain import generate_explanations
from milaan.matching import unique_subset
from milaan.pipeline import load, recon, setup, validate

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def reconciled(tmp_path_factory):
    folder = tmp_path_factory.mktemp("reconciliation-fixture")
    generate(folder, 1000, fixture=True)
    setup()
    load(folder)
    result = recon()
    generate_explanations()
    return result


def test_fixture_known_links(reconciled):
    assert reconciled["score"]["FALSE_POSITIVE"] == 0
    assert reconciled["score"]["FALSE_NEGATIVE"] == 0
    assert reconciled["score"]["PRECISION_VALUE"] == 1
    categories = query("SELECT DISTINCT break_type FROM MILAAN_STG.GROUND_TRUTH")
    assert set(load_config()["break_rates"]) <= {r["BREAK_TYPE"] for r in categories}
    wrong = query(
        "SELECT COUNT(*) N FROM MILAAN_RES.LINK x LEFT JOIN MILAAN_STG.GROUND_TRUTH g ON x.ledger_id=g.ledger_id AND x.bank_txn_id=g.bank_txn_id AND COALESCE(x.pg_payment_id,'NO_PG')=COALESCE(g.pg_payment_id,'NO_PG') AND g.expected_match=1 WHERE g.event_id IS NULL"
    )
    assert wrong[0]["N"] == 0


def test_fixture_matches_stored_baseline(reconciled):
    expected = json.loads((ROOT / "tests/fixtures/expected_links.json").read_text())
    rows = query(
        "SELECT match_id,ledger_id,bank_txn_id,pg_payment_id,pass_name FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
    )
    assert [[row[column] for column in expected["columns"]] for row in rows] == expected["links"]
    assert (
        query(
            'SELECT exception_id,category,amount_paise FROM MILAAN_RES."EXCEPTION" ORDER BY exception_id'
        )
        == expected["exceptions"]
    )


def test_evidence_preserves_large_paise_and_escaped_text(reconciled):
    reason = 'Payer "A"\nReference\\123; मिलान'
    row = query(
        "SELECT MILAAN_CORE.EVIDENCE(NULL,NULL,NULL,NULL,9007199254740993,-9007199254740993,NULL,NULL,NULL,CAST('2026-10-14' AS DATE),{reason!s},'UPI',NULL,NULL,NULL,NULL,NULL) EVIDENCE",
        {"reason": reason},
    )[0]
    evidence = json.loads(row["EVIDENCE"])
    assert evidence["amount_paise"] == 9007199254740993
    assert evidence["bank_paise"] == -9007199254740993
    assert evidence["reason"] == reason
    assert evidence["date"] == "2026-10-14"
    assert evidence["ledger_id"] is None


def test_all_seven_passes_and_no_double_matches(reconciled):
    assert len(reconciled["passes"]) == 7
    with connect() as connection:
        validate(connection)
        connection.execute(
            "INSERT INTO MILAAN_RES.MATCH_MEMBER VALUES ('conflict','BANK',(SELECT MIN(txn_key) FROM MILAAN_RES.MATCH_MEMBER WHERE source_name='BANK'))"
        )
        with pytest.raises(RuntimeError, match="conflicting"):
            validate(connection)
        connection.rollback()


def test_native_subset_matches_python_oracle(reconciled, tmp_path):
    cases = [
        (100, [("A", 40), ("B", 60)]),
        (100, [("A", 40), ("B", 30), ("C", 30)]),
        (100, [("A", 50), ("B", 50), ("C", 50)]),
        (100, [("A", 50), ("A", 50)]),
        (100, [(str(i), 1) for i in range(13)]),
        (0, [("A", 40), ("B", 60)]),
        (9007199254740993, [("A", 9007199254740983), ("B", 10)]),
    ]
    rng = random.Random(71)
    for _ in range(40):
        cases.append(
            (
                rng.randint(80, 200),
                [(str(i), rng.randint(1, 80)) for i in range(rng.randint(2, 14))],
            )
        )
    expected, path = set(), tmp_path / "subset.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for index, (target, payments) in enumerate(cases):
            group = str(index)
            writer.writerows((group, bank, target, amount) for bank, amount in payments)
            expected.update((group, bank) for bank in (unique_subset(target, payments) or ()))
    with connect() as connection:
        connection.execute(
            "CREATE OR REPLACE TABLE MILAAN_CORE.SUBSET_FIXTURE (ledger_key VARCHAR(40),bank_key VARCHAR(40),target DECIMAL(18,0),amount DECIMAL(18,0))"
        )
        connection.import_from_file(path, ("MILAAN_CORE", "SUBSET_FIXTURE"))
        rows = connection.execute(
            "SELECT MILAAN_CORE.SUBSET(ledger_key,bank_key,target,amount) FROM MILAAN_CORE.SUBSET_FIXTURE GROUP BY ledger_key"
        ).fetchall()
        assert {(row["LEDGER_ID"], row["BANK_TXN_ID"]) for row in rows} == expected
        connection.execute("DROP TABLE MILAAN_CORE.SUBSET_FIXTURE")
        connection.commit()


def test_evidence_batch_and_decision_audit(reconciled):
    row = query(
        "SELECT exception_id FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' LIMIT 1"
    )[0]
    evidence = detail(row["EXCEPTION_ID"])
    assert "37 payments" in evidence["EXPLANATION"]
    assert json.loads(evidence["EVIDENCE"])["matched_count"] == 36
    identifier = decision(
        row["EXCEPTION_ID"], "ASSIGN", "Fixture analyst", "Collections", "Verify gateway receipt"
    )
    audit = query(
        "SELECT * FROM MILAAN_AUDIT.DECISION WHERE decision_id={id!s}", {"id": identifier}
    )
    assert audit[0]["DECISION_ACTION"] == "ASSIGN"
    assert audit[0]["RUN_ID"] == reconciled["run_id"]


def test_rerun_is_idempotent(reconciled):
    sql = "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
    before = query(sql)
    second = recon()
    assert second["score"]["FALSE_POSITIVE"] == 0
    assert second["score"]["FALSE_NEGATIVE"] == 0
    assert query(sql) == before


def test_wrong_link_counts_as_false_positive_in_its_category(reconciled):
    with connect() as connection:
        original = connection.execute(
            "SELECT * FROM MILAAN_RES.LINK WHERE pass_name='EXACT' LIMIT 1"
        ).fetchone()
        connection.execute(
            "INSERT INTO MILAAN_RES.LINK VALUES ('wrong-link',{ledger!s},'NONEXISTENT_BANK',NULL,'EXACT',1,'Injected scoring test')",
            {"ledger": original["LEDGER_ID"]},
        )
        connection.execute("TRUNCATE TABLE MILAAN_RES.SCORE")
        for sql in statements(ROOT / "sql/50_score.sql"):
            connection.execute(sql.replace("@RUN_ID@", "scoring-test"))
        scores = connection.execute(
            "SELECT break_type,false_positive FROM MILAAN_RES.SCORE WHERE false_positive>0"
        ).fetchall()
        assert len(scores) == 2
        assert next(r for r in scores if r["BREAK_TYPE"] == "OVERALL")["FALSE_POSITIVE"] == 1
        connection.rollback()


def test_daily_carry_forward_matches_full_month_without_future_records(reconciled):
    from milaan.daily import recon_day
    from milaan.db import scope

    start = date(2026, 10, 1)
    finish = date.fromisoformat(str(query("SELECT MAX(txn_date) D FROM MILAAN_CORE.TXN")[0]["D"]))
    before = query(
        "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
    )
    results = []
    day = start
    first = True
    while day <= finish:
        # Include grace days on which gateway credits or NACH returns arrive.
        if query(
            "SELECT is_business_day B FROM MILAAN_CORE.CALENDAR WHERE calendar_date=CAST({day!s} AS DATE)",
            {"day": str(day)},
        )[0]["B"]:
            result = recon_day(str(day), restart=first, warmup=False)
            results.append({"date": str(day), "seconds": result["seconds"], **result["daily"]})
            first = False
            with scope("day"):
                with connect() as connection:
                    validate(connection)
                for table, column in (
                    ("LEDGER", "posted_date"),
                    ("BANK", "value_date"),
                    ("PG", "settlement_date"),
                    ("NACH", "return_date"),
                ):
                    assert (
                        query(
                            f"SELECT COUNT(*) N FROM MILAAN_CORE.{table} WHERE {column}>CAST({{day!s}} AS DATE)",
                            {"day": str(day)},
                        )[0]["N"]
                        == 0
                    )
        day += timedelta(days=1)
    with scope("day"):
        after = query(
            "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
        )
    assert after == before
    assert (
        query("SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id")
        == before
    )
    # At least one earlier receipt is linked on a later bank-arrival day.
    carried = query(
        "SELECT COUNT(*) N FROM MILAAN_DAY_RES.LINK x JOIN MILAAN_DAY_CORE.LEDGER l ON x.ledger_id=l.ledger_id JOIN MILAAN_DAY_CORE.BANK b ON x.bank_txn_id=b.bank_txn_id WHERE b.value_date>l.posted_date"
    )[0]["N"]
    assert carried > 0
    (ROOT / "docs/daily_fixture_results.json").write_text(
        json.dumps(
            {
                "source_rows": 1000,
                "days": results,
                "final_links": len(after),
                "all_seven_link_columns_identical": True,
                "carried_ledger_bank_edges": carried,
            },
            indent=2,
        )
        + "\n"
    )


def test_daily_replay_and_reset_preserve_the_day_and_month(reconciled):
    from milaan.daily import recon_day
    from milaan.db import scope
    from milaan.demo import reset_demo

    monthly = query(
        "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
    )
    first = recon_day("2026-10-14", restart=True)
    with scope("day"):
        expected = query(
            "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
        )
    second = recon_day("2026-10-14")
    assert first["daily"]["new_source_counts"] == second["daily"]["new_source_counts"]
    with scope("day"):
        assert (
            query(
                "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
            )
            == expected
        )
    reset_demo("day", "2026-10-14")
    with scope("day"):
        assert (
            query("SELECT status FROM MILAAN_AUDIT.RUN ORDER BY started_at DESC LIMIT 1")[0][
                "STATUS"
            ]
            == "READY"
        )
        assert query('SELECT COUNT(*) N FROM MILAAN_RES."EXCEPTION"')[0]["N"] == 0
    recon_day("2026-10-14")
    with scope("day"):
        assert (
            query(
                "SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id"
            )
            == expected
        )
    assert (
        query("SELECT * FROM MILAAN_RES.LINK ORDER BY match_id,ledger_id,bank_txn_id,pg_payment_id")
        == monthly
    )


def test_reversal_cancels_month_and_previously_closed_daily_credit(tmp_path):
    from generator.generate import add_business_days
    from milaan.daily import recon_day
    from milaan.db import scope

    folder = tmp_path / "bank-reversal"
    generate(folder, 1000, fixture=True)

    def read(name):
        with (folder / f"{name}.csv").open() as stream:
            return list(csv.DictReader(stream))

    ledger, bank, truth = read("ledger"), read("bank_statement"), read("ground_truth")
    upi = {row["ledger_id"] for row in ledger if row["channel"] == "UPI"}
    target = next(
        row
        for row in truth
        if row["break_type"] == "CLEAN" and row["ledger_id"] in upi and row["expected_match"] == "1"
    )
    credit = next(row for row in bank if row["bank_txn_id"] == target["bank_txn_id"])
    debit_day = add_business_days(date.fromisoformat(credit["value_date"]), 1, set())
    debit = dict(
        credit,
        bank_txn_id=credit["bank_txn_id"] + "-RV",
        value_date=str(debit_day),
        narration="REVERSAL " + credit["narration"],
        credit_paise="0",
        debit_paise=credit["credit_paise"],
    )
    bank.append(debit)
    target["expected_match"] = "0"
    target["expected_category"] = "BANK_REVERSAL"
    for name, rows in (("bank_statement", bank), ("ground_truth", truth)):
        with (folder / f"{name}.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_counts"]["bank_statement"] += 1
    manifest["source_rows"] += 1
    manifest_path.write_text(json.dumps(manifest))
    load(folder)
    result = recon()
    assert result["score"]["FALSE_POSITIVE"] == 0
    assert not query(
        "SELECT * FROM MILAAN_RES.LINK WHERE bank_txn_id={id!s}", {"id": credit["bank_txn_id"]}
    )
    assert query(
        "SELECT * FROM MILAAN_RES.\"EXCEPTION\" WHERE category='BANK_REVERSAL' AND txn_key={id!s}",
        {"id": credit["bank_txn_id"]},
    )
    recon_day(credit["value_date"], restart=True, warmup=False)
    with scope("day"):
        assert query(
            "SELECT * FROM MILAAN_RES.LINK WHERE bank_txn_id={id!s}", {"id": credit["bank_txn_id"]}
        )
    recon_day(str(debit_day), warmup=False)
    with scope("day"):
        assert not query(
            "SELECT * FROM MILAAN_RES.LINK WHERE bank_txn_id={id!s}", {"id": credit["bank_txn_id"]}
        )
        assert query(
            "SELECT * FROM MILAAN_RES.\"EXCEPTION\" WHERE category='BANK_REVERSAL' AND txn_key={id!s}",
            {"id": credit["bank_txn_id"]},
        )
        with connect() as connection:
            validate(connection)
