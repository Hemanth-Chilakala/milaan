"""Database integration checks replace current demo tables with a seeded fixture."""

import csv
import json
import random

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
