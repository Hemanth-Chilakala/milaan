INSERT INTO MILAAN_RES.LINK
WITH candidates AS (
 SELECT l.ledger_id,b.bank_txn_id,p.pg_payment_id,
 COUNT(*) OVER (PARTITION BY l.ledger_id) lc,
 COUNT(*) OVER (PARTITION BY b.bank_txn_id) bc,
 COUNT(*) OVER (PARTITION BY p.pg_payment_id) pc
 FROM MILAAN_CORE.OPEN_LEDGER l JOIN MILAAN_CORE.OPEN_PG p
 ON l.external_ref=p.payment_ref AND l.amount_paise=p.gross_paise AND l.loan_id=p.loan_id
 JOIN MILAAN_CORE.OPEN_BANK b ON b.bank_ref=p.settlement_utr AND b.amount_paise=p.net_paise AND b.value_date=p.settlement_date
 WHERE l.duplicate_rank=1 AND p.gross_paise>0
 AND p.net_paise=p.gross_paise-p.fee_paise-p.gst_on_fee_paise
)
SELECT 'F:'||bank_txn_id,ledger_id,bank_txn_id,pg_payment_id,'FEE_AWARE',1.0,'Gross minus fee and GST equals the unique bank settlement'
FROM candidates WHERE lc=1 AND bc=1 AND pc=1;
