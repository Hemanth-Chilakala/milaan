from milaan.explain import explain, mask_pii, rupees


def test_indian_currency():
    assert rupees(48215000) == "₹4,82,150"
    assert rupees(-125) == "−₹1.25"


def test_batch_explanation_uses_evidence():
    text = explain(
        "MISSING_IN_LEDGER",
        {
            "amount_paise": 1299900,
            "bank_paise": 48215000,
            "fee_paise": 120400,
            "gst_paise": 21700,
            "batch_id": "B-1",
            "payment_count": 37,
            "matched_count": 36,
            "loan_id": "SFL-PL-0088213",
            "date": "2026-10-14",
        },
    )
    assert "37 payments" in text and "36 payments matched" in text
    assert "₹12,999" in text and "SFL-PL-0088213" in text


def test_invalid_evidence_falls_back():
    assert "incomplete" in explain("MISSING_IN_BANK", "broken JSON")
    assert "incomplete" in explain("MISSING_IN_BANK", {})


def test_masking_nested_evidence():
    source = {
        "customer_name": "Hemanth Chilakala",
        "loan_id": "SFL-PL-0088213",
        "records": [{"bank_ref": "123456789"}],
        "amount_paise": 1234,
    }
    masked = mask_pii(source)
    assert masked["customer_name"] == "H. C."
    assert masked["loan_id"].endswith("8213") and "SFL-" not in masked["loan_id"]
    assert masked["records"][0]["bank_ref"] == "*****6789"
    assert source["customer_name"] == "Hemanth Chilakala"
