"""Database integration checks replace current demo tables with a seeded fixture."""

import json

import pytest

from generator.generate import generate, load_config
from milaan.analytics import decision, detail
from milaan.config import ROOT
from milaan.db import connect, query, statements
from milaan.explain import generate_explanations
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
    before = query("SELECT COUNT(*) N FROM MILAAN_RES.LINK")[0]["N"]
    second = recon()
    assert second["score"]["FALSE_POSITIVE"] == 0
    assert query("SELECT COUNT(*) N FROM MILAAN_RES.LINK")[0]["N"] == before


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
