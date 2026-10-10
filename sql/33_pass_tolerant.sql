INSERT INTO MILAAN_RES.LINK
WITH candidates AS (
 SELECT l.ledger_id,b.bank_txn_id,
 COUNT(*) OVER (PARTITION BY l.ledger_id) lc,
 COUNT(*) OVER (PARTITION BY b.bank_txn_id) bc,
 ROW_NUMBER() OVER (PARTITION BY l.ledger_id ORDER BY b.day_index-l.day_index,b.bank_txn_id) choice_rank
 FROM MILAAN_CORE.OPEN_LEDGER l JOIN MILAAN_CORE.OPEN_BANK b
 ON l.loan_id=b.loan_id AND l.amount_paise=b.amount_paise AND b.day_index-l.day_index BETWEEN 0 AND 3
 AND l.ref_suffix8=b.ref_suffix8
 WHERE l.duplicate_rank=1 AND l.status='PAID'
 AND NOT EXISTS (SELECT 1 FROM MILAAN_CORE.NACH n WHERE n.ref_norm=l.ref_norm AND n.loan_id=l.loan_id)
)
SELECT 'T:'||bank_txn_id,ledger_id,bank_txn_id,CAST(NULL AS VARCHAR(40)),'TOLERANT',0.995,'Unique loan, amount, reference suffix and 0-3 business-day window agree'
FROM candidates WHERE lc=1 AND bc=1 AND choice_rank=1;
