from milaan.db import current_scope, scope, scoped_sql


def test_scope_is_nested_and_restored_on_error():
    assert current_scope() == "month"
    try:
        with scope("day"):
            assert current_scope() == "day"
            with scope("month"):
                assert current_scope() == "month"
            raise RuntimeError("example")
    except RuntimeError:
        pass
    assert current_scope() == "month"


def test_daily_routing_keeps_raw_sources_and_monthly_namespace_separate():
    sql = "SELECT * FROM MILAAN_CORE.LEDGER JOIN MILAAN_RES.LINK ON 1=1 JOIN MILAAN_AUDIT.RUN ON 1=1 JOIN MILAAN_STG.LEDGER ON 1=1"
    routed = scoped_sql(sql, "day")
    assert "MILAAN_DAY_CORE.LEDGER" in routed
    assert "MILAAN_DAY_RES.LINK" in routed
    assert "MILAAN_DAY_AUDIT.RUN" in routed
    assert "MILAAN_STG.LEDGER" in routed
    assert scoped_sql(sql, "month") == sql
