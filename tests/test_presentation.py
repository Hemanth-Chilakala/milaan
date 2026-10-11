from app.presentation import compact_money, display_evidence, html_text, percent


def test_currency_totals_fit_without_losing_full_amount():
    assert compact_money(202200000000) == "₹202.20 Cr"
    assert compact_money(26668457) == "₹2.67 L"
    assert compact_money(1642571) == "₹16,425.71"


def test_unmeasured_accuracy_is_not_formatted_as_zero():
    assert percent(None) == "—"
    assert percent(0) == "0.00%"


def test_source_evidence_is_escaped_for_html_cards():
    assert (
        html_text('<script>"receipt"</script>')
        == "&lt;script&gt;&quot;receipt&quot;&lt;/script&gt;"
    )


def test_display_dates_preserve_source_evidence_and_integer_paise():
    original = {
        "date": "2026-10-27",
        "bank": [{"VALUE_DATE": "2026-10-29", "amount_paise": 9007199254740993}],
        "loan_id": "SFL-HL-4827316",
    }
    shown = display_evidence(original)
    assert shown["date"] == "27 Oct 2026"
    assert shown["bank"][0]["VALUE_DATE"] == "29 Oct 2026"
    assert shown["bank"][0]["amount_paise"] == 9007199254740993
    assert original["date"] == "2026-10-27" and shown["loan_id"] == original["loan_id"]
