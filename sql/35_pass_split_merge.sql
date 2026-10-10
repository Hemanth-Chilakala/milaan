CREATE OR REPLACE TABLE MILAAN_CORE.SPLIT_CANDIDATE AS
SELECT l.ledger_id,b.bank_txn_id,l.amount_paise target_paise,b.amount_paise
FROM MILAAN_CORE.OPEN_LEDGER l JOIN MILAAN_CORE.OPEN_BANK b
ON l.loan_id=b.loan_id AND l.name_norm=b.name_norm AND l.channel='UPI' AND b.channel='UPI'
AND b.day_index-l.day_index BETWEEN 0 AND 3 AND b.amount_paise>0 AND b.amount_paise<l.amount_paise
WHERE l.duplicate_rank=1;

CREATE OR REPLACE TABLE MILAAN_CORE.SPLIT_PROPOSAL AS
SELECT MILAAN_CORE.SUBSET(c.ledger_id,c.bank_txn_id,c.target_paise,c.amount_paise)
FROM MILAAN_CORE.SPLIT_CANDIDATE c
JOIN (SELECT ledger_id FROM MILAAN_CORE.SPLIT_CANDIDATE
 GROUP BY ledger_id HAVING COUNT(*) BETWEEN 2 AND 12 AND SUM(amount_paise)>=MAX(target_paise)) eligible
ON c.ledger_id=eligible.ledger_id
GROUP BY c.ledger_id;

INSERT INTO MILAAN_RES.LINK
SELECT 'S:'||s.ledger_id,s.ledger_id,s.bank_txn_id,CAST(NULL AS VARCHAR(40)),'SPLIT_MERGE',1.0,'Only bounded 2-3 credit subset equals the EMI; payer, loan and business-day window agree'
FROM MILAAN_CORE.SPLIT_PROPOSAL s
WHERE NOT EXISTS (
 SELECT 1 FROM MILAAN_CORE.SPLIT_PROPOSAL a JOIN MILAAN_CORE.SPLIT_PROPOSAL b ON a.bank_txn_id=b.bank_txn_id AND a.ledger_id<>b.ledger_id
 WHERE a.ledger_id=s.ledger_id
);
