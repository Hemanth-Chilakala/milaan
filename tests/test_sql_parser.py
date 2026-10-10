from milaan.db import statements


def test_statement_separator_inside_evidence(tmp_path):
    path = tmp_path / "test.sql"
    path.write_text("SELECT 'Rule; payer''s reference agrees'; SELECT 2;")
    assert statements(path) == ["SELECT 'Rule; payer''s reference agrees'", "SELECT 2"]


def test_udf_body_is_a_single_statement(tmp_path):
    for language in ("PYTHON3", "LUA"):
        path = tmp_path / "udf.sql"
        script = f"CREATE OR REPLACE {language} SCALAR SCRIPT T.PING() RETURNS VARCHAR(10) AS\nreturn 'a;b'\n/\n"
        path.write_text(script)
        assert statements(path) == [script.rsplit("\n/", 1)[0]]
