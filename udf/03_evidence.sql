CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MILAAN_CORE.EVIDENCE(
 ledger_key VARCHAR(40), bank_key VARCHAR(40), pg_key VARCHAR(40), loan VARCHAR(40),
 amount DECIMAL(18,0), bank_amount DECIMAL(18,0), fee DECIMAL(18,0), gst DECIMAL(18,0), refund DECIMAL(18,0),
 txn_day DATE, reason VARCHAR(100), channel_name VARCHAR(10), batch VARCHAR(80),
 total_count DECIMAL(10,0), matched_count DECIMAL(10,0), gross_total DECIMAL(18,0), net_total DECIMAL(18,0)
) RETURNS VARCHAR(10000) AS
import json

def run(ctx):
    def integer(value):
        return int(value) if value is not None else None
    return json.dumps({
        'ledger_id': ctx.ledger_key, 'bank_txn_id': ctx.bank_key,
        'pg_payment_id': ctx.pg_key, 'loan_id': ctx.loan,
        'amount_paise': integer(ctx.amount), 'bank_paise': integer(ctx.bank_amount),
        'fee_paise': integer(ctx.fee), 'gst_paise': integer(ctx.gst),
        'refund_paise': integer(ctx.refund), 'date': str(ctx.txn_day),
        'reason': ctx.reason, 'channel': ctx.channel_name, 'batch_id': ctx.batch,
        'payment_count': integer(ctx.total_count), 'matched_count': integer(ctx.matched_count),
        'gross_total_paise': integer(ctx.gross_total), 'net_total_paise': integer(ctx.net_total)
    }, sort_keys=True)
/
