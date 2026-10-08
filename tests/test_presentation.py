from app.presentation import compact_money, html_text, percent


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
