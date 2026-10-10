INSERT INTO MILAAN_RES.LINK
WITH candidates AS (
 SELECT l.ledger_id,b.bank_txn_id,
 COUNT(*) OVER (PARTITION BY l.ledger_id) lc,
 COUNT(*) OVER (PARTITION BY b.bank_txn_id) bc
 FROM MILAAN_CORE.OPEN_LEDGER l JOIN MILAAN_CORE.OPEN_BANK b
 ON l.ref_norm=b.ref_norm AND l.amount_paise=b.amount_paise AND l.posted_date=b.value_date
 WHERE l.duplicate_rank=1 AND l.status='PAID'
 AND NOT EXISTS (SELECT 1 FROM MILAAN_CORE.NACH n WHERE n.ref_norm=l.ref_norm AND n.loan_id=l.loan_id)
)
SELECT 'D:'||bank_txn_id,ledger_id,bank_txn_id,CAST(NULL AS VARCHAR(40)),'EXACT',1.0,'Unique reference, amount and value date agree'
FROM candidates WHERE lc=1 AND bc=1;
