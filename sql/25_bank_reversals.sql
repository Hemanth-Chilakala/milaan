CREATE OR REPLACE TABLE MILAAN_CORE.BANK_REVERSAL AS
SELECT c.bank_txn_id credit_id,d.bank_txn_id debit_id,c.loan_id,c.channel,c.amount_paise,
 c.value_date credit_date,d.value_date reversal_date,d.day_index,c.ref_norm
FROM MILAAN_CORE.BANK d JOIN MILAAN_CORE.BANK c
ON d.ref_norm=c.ref_norm AND d.amount_paise=-c.amount_paise
AND c.value_date<=d.value_date
WHERE d.amount_paise<0 AND c.amount_paise>0 AND d.ref_norm IS NOT NULL;

CREATE OR REPLACE VIEW MILAAN_CORE.SAFE_BANK AS
SELECT b.* FROM MILAAN_CORE.BANK b WHERE NOT EXISTS
(SELECT 1 FROM MILAAN_CORE.BANK_REVERSAL r WHERE r.credit_id=b.bank_txn_id OR r.debit_id=b.bank_txn_id);

DELETE FROM MILAAN_CORE.OPEN_BANK b WHERE EXISTS
(SELECT 1 FROM MILAAN_CORE.BANK_REVERSAL r WHERE r.credit_id=b.bank_txn_id OR r.debit_id=b.bank_txn_id);
