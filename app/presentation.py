"""Small display helpers; all monetary comparisons remain in the database."""

from datetime import date, datetime
from html import escape

from milaan.explain import rupees

LABELS = {
    "BANK_REVERSAL": "Bank credit reversed",
    "NACH_BOUNCE_MISPOSTED": "NACH return posted as paid",
    "MISSING_IN_BANK": "Receipt missing from bank",
    "MISSING_IN_LEDGER": "Gateway receipt missing from ledger",
    "DUPLICATE_POSTING": "Duplicate receipt",
    "PARTIAL_PAYMENT": "Partial payment",
    "UNIDENTIFIED_CREDIT": "Unidentified bank credit",
    "NAME_MISMATCH": "Payer details need review",
    "EXACT": "Exact reference",
    "PG_BATCH": "Gateway batch",
    "FEE_AWARE": "Fee aware",
    "TOLERANT": "Timing & reference",
    "FUZZY": "Name similarity",
    "SPLIT_MERGE": "Split payments",
    "CLASSIFY": "Classify remaining",
    "CLEAN": "Clean receipt",
    "TIMING": "Settlement timing",
    "BATCH_SETTLEMENT": "Batch settlement",
    "FEE_NETTING": "Fee netting",
    "REF_TRUNCATED": "Shortened reference",
    "SPLIT_PAYMENT": "Split payment",
    "REFUND_REVERSAL": "Refund / reversal",
    "OVERALL": "Overall",
}


def label(value):
    return LABELS.get(value, str(value).replace("_", " ").capitalize())


def html_text(value):
    return escape(str(value if value is not None else "—"), quote=True)


def compact_money(paise):
    value = int(paise or 0) / 100
    if abs(value) >= 10000000:
        return f"₹{value / 10000000:,.2f} Cr"
    if abs(value) >= 100000:
        return f"₹{value / 100000:,.2f} L"
    return rupees(paise)


def business_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return "—"


def percent(value, decimals=2):
    return f"{100 * float(value):.{decimals}f}%" if value is not None else "—"


def ist_timestamp(value):
    """Format a timestamp already converted to IST by the query."""
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y · %H:%M") + " IST"
    except (TypeError, ValueError):
        return "—"


def display_evidence(value):
    """Format evidence dates for readers without changing stored values or amounts."""
    if isinstance(value, dict):
        return {
            key: business_date(item)
            if item is not None and (key.lower() == "date" or key.lower().endswith("_date"))
            else display_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [display_evidence(item) for item in value]
    return value
