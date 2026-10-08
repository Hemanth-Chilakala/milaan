from milaan.db import statements


def test_statement_separator_inside_evidence(tmp_path):
    path = tmp_path / "test.sql"
    path.write_text("SELECT 'Rule; payer''s reference agrees'; SELECT 2;")
    assert statements(path) == ["SELECT 'Rule; payer''s reference agrees'", "SELECT 2"]
