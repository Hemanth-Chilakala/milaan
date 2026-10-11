"""Deterministic explanations composed from recorded reconciliation evidence."""

import json
import re
from datetime import date


def rupees(paise: int | None) -> str:
    value = int(paise or 0)
    whole, fraction = divmod(abs(value), 100)
    digits = str(whole)
    tail = digits[-3:]
    head = digits[:-3]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    formatted = ",".join(groups + [tail])
    return ("−" if value < 0 else "") + "₹" + formatted + (f".{fraction:02d}" if fraction else "")


def explain(category: str, evidence: str | dict) -> str:
    try:
        e = json.loads(evidence) if isinstance(evidence, str) else evidence
        if not isinstance(e, dict) or e.get("amount_paise") is None:
            raise ValueError("Missing amount evidence")
        amount = rupees(e["amount_paise"])
        loan = e.get("loan_id") or "an unidentified loan"
        try:
            day = date.fromisoformat(str(e.get("date"))[:10]).strftime("%d %b %Y")
        except (ValueError, TypeError):
            day = "an unrecorded date"
        if category == "MISSING_IN_LEDGER" and e.get("batch_id"):
            count, matched = e.get("payment_count", 0), e.get("matched_count", 0)
            refund = (
                f", with {rupees(e['refund_paise'])} in refunds" if e.get("refund_paise") else ""
            )
            return (
                f"This {rupees(e.get('bank_paise'))} bank credit is a PayFast batch settlement "
                f"of {count} payments, net of {rupees(e.get('fee_paise'))} fees and "
                f"{rupees(e.get('gst_paise'))} GST{refund}. {matched} payments matched to "
                f"the ledger; {count - matched} did not. Payment {e.get('pg_payment_id')} for "
                f"{loan}, {amount}, paid on {day}, has no ledger receipt. "
                f"Action: verify the gateway payment and post the missing receipt to {loan}."
            )
        if category == "BANK_REVERSAL":
            return (
                f"The {amount} bank credit for {loan} was cancelled by an equal debit "
                f"with the same reference on {day}. {e.get('reason') or ''}. "
                "Both bank lines are excluded from automatic matching. "
                "Action: verify the cancelling debit and reverse any paid posting after approval."
            )
        if category == "NACH_BOUNCE_MISPOSTED":
            return (
                f"The ledger shows {amount} paid against {loan} on {day}, but the NACH "
                f"return says: {e.get('reason', 'return recorded')}. A returned debit is "
                "not money received. Action: verify the return, reverse the paid status "
                "after approval and notify the collections owner."
            )
        if category == "DUPLICATE_POSTING":
            return (
                f"Receipt {e.get('ledger_id')} repeats the reference, loan and {amount} "
                f"amount of an earlier receipt for {loan}. The bank credit cannot support "
                "two postings. Action: check the original receipt and reverse the extra "
                "posting after approval."
            )
        if category == "PARTIAL_PAYMENT":
            bank = int(e.get("bank_paise") or 0)
            return (
                f"The ledger expects {amount} for {loan}, but candidate bank credit "
                f"{e.get('bank_txn_id')} contains {rupees(bank)}. The shortfall is "
                f"{rupees(int(e['amount_paise']) - bank)}. The amount rule rejected a full "
                "match. Action: allocate the received amount and investigate the balance."
            )
        if category == "MISSING_IN_BANK":
            candidate = (
                (
                    f" Candidate {e['bank_txn_id']} contains {rupees(e.get('bank_paise'))} "
                    "and did not satisfy the matching rules."
                )
                if e.get("bank_txn_id")
                else " No bank credit satisfies the receipt's reference, amount and business-day checks."
            )
            return (
                f"Receipt {e.get('ledger_id')} shows {amount} paid for {loan} on {day}."
                f"{candidate} Action: verify the receipt with the bank before clearing "
                "the loan account; do not chase the customer solely on this exception."
            )
        if category == "NAME_MISMATCH":
            return (
                f"Receipt {e.get('ledger_id')} for {loan}, {amount}, has candidate bank "
                f"credit {e.get('bank_txn_id')} with the same amount and reference suffix. "
                "The name/reference similarity or uniqueness checks did not support an "
                "automatic match. Action: verify the payer and full payment reference "
                "before approving this relationship."
            )
        if category == "UNIDENTIFIED_CREDIT":
            return (
                f"Bank credit {e.get('bank_txn_id')} received {amount} on {day}. "
                "No unique ledger receipt passed the matching rules. Keep the amount "
                "in suspense until the payer and loan are verified. "
                "Action: request the payment reference and identify the correct loan."
            )
        return f"{category}: {amount} for {loan} on {day}. Action: review the source evidence before making an accounting decision."
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return "The recorded evidence is incomplete. Review the source records and request the missing information before making a decision."


def mask_pii(evidence: dict) -> dict:
    """Privacy helper for a future optional rewrite; no external service is called."""

    def mask(key, value):
        if isinstance(value, dict):
            return {k: mask(k, v) for k, v in value.items()}
        if isinstance(value, list):
            return [mask(key, item) for item in value]
        if isinstance(value, str):
            if "name" in key.lower():
                return " ".join(word[0] + "." for word in value.split() if word)
            if re.search(r"ref|utr|umrn|loan|txn|payment|ledger|batch", key, re.I):
                return "*" * max(0, len(value) - 4) + value[-4:]
        return value

    return {key: mask(key, value) for key, value in evidence.items()}


def generate_explanations() -> int:
    from milaan.db import connect

    with connect() as connection:
        connection.execute("TRUNCATE TABLE MILAAN_RES.EXPLANATION")
        result = connection.execute(
            'INSERT INTO MILAAN_RES.EXPLANATION SELECT exception_id,MILAAN_CORE.EXPLAIN(category,evidence) FROM MILAAN_RES."EXCEPTION"'
        )
        connection.commit()
        return result.rowcount()


if __name__ == "__main__":
    print(f"Generated {generate_explanations():,} explanations inside Exasol.")
