CREATE OR REPLACE TABLE MILAAN_CORE.BATCH AS
SELECT settlement_batch_id batch_id,settlement_utr,SUM(net_paise) net_paise,
 SUM(gross_paise) gross_paise,SUM(fee_paise) fee_paise,SUM(gst_on_fee_paise) gst_paise,
 -SUM(CASE WHEN gross_paise<0 THEN gross_paise ELSE 0 END) refund_paise,
 SUM(CASE WHEN gross_paise>0 THEN 1 ELSE 0 END) payment_count,
 MIN(settlement_date) settlement_date
FROM MILAAN_CORE.PG GROUP BY settlement_batch_id,settlement_utr;

INSERT INTO MILAAN_RES.LINK
WITH bank_candidates AS (
 SELECT b.bank_txn_id,b.batch_id,b.ref_norm,
 COUNT(*) OVER (PARTITION BY b.batch_id) candidate_count
 FROM MILAAN_CORE.OPEN_BANK b JOIN MILAAN_CORE.BATCH g
 ON b.batch_id=g.batch_id AND b.bank_ref=g.settlement_utr AND b.amount_paise=g.net_paise AND b.value_date=g.settlement_date

), receipts AS (
 SELECT l.ledger_id,b.bank_txn_id,p.pg_payment_id,
 COUNT(*) OVER (PARTITION BY p.pg_payment_id) ledger_count
 FROM bank_candidates b JOIN MILAAN_CORE.OPEN_PG p ON p.settlement_batch_id=b.batch_id
 JOIN MILAAN_CORE.OPEN_LEDGER l ON l.external_ref=p.payment_ref AND l.amount_paise=p.gross_paise AND l.loan_id=p.loan_id
 WHERE b.candidate_count=1 AND p.gross_paise>0 AND l.duplicate_rank=1
)
SELECT 'PG:'||bank_txn_id,ledger_id,bank_txn_id,pg_payment_id,'PG_BATCH',1.0,'Gateway batch net equals bank credit; receipt equals gateway gross'
FROM receipts WHERE ledger_count=1;
