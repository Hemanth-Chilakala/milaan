CREATE OR REPLACE TABLE MILAAN_CORE.LEDGER AS
SELECT l.ledger_id,CAST(l.loan_id AS VARCHAR(500)) loan_id,l.customer_name,l.emi_due_date,l.amount_paise,l.channel,l.external_ref,l.posted_date,l.status, CAST(REGEXP_REPLACE(UPPER(external_ref),'[^A-Z0-9]','') AS VARCHAR(100)) ref_norm,
 CAST(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(UPPER(customer_name),'^(MR|MRS|MS|DR)[.]? +',''),' +',' ')) AS VARCHAR(500)) name_norm,
 c.business_day_index day_index,
 ROW_NUMBER() OVER (PARTITION BY external_ref,loan_id,amount_paise ORDER BY posted_date,ledger_id) duplicate_rank
FROM MILAAN_STG.LEDGER l JOIN MILAAN_CORE.CALENDAR c ON l.posted_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.BANK AS
SELECT b.*, CAST(credit_paise-debit_paise AS DECIMAL(18,0)) amount_paise,
 CAST(REGEXP_REPLACE(UPPER(bank_ref),'[^A-Z0-9]','') AS VARCHAR(100)) ref_norm,
 CAST(REGEXP_SUBSTR(narration,'SFL-(HL|PL|BL|GL)-[0-9]{7}') AS VARCHAR(500)) loan_id,
 CAST(REGEXP_SUBSTR(narration,'PF-B-[0-9]{8}-[0-9]+') AS VARCHAR(80)) batch_id,
 REGEXP_SUBSTR(narration,'BUBN[0-9]{11}') utr,
 REGEXP_SUBSTR(narration,'BUB7[0-9]{12}') umrn,
 CASE WHEN narration LIKE 'UPI/%' THEN 'UPI' WHEN narration LIKE 'NACH%' THEN 'NACH' WHEN narration LIKE '%PAYFAST%' THEN 'PG' ELSE 'NEFT' END channel,
 TRIM(REGEXP_REPLACE(REGEXP_REPLACE(UPPER(
 CASE WHEN narration LIKE 'UPI/CR/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'UPI/CR/[^/]+/[^/]+'),'UPI/CR/[^/]+/','')
 WHEN narration LIKE 'NEFT/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'NEFT/[^/]+/[^/]+'),'NEFT/[^/]+/','')
 WHEN narration LIKE 'PAYFAST/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'PAYFAST/[^/]+/[^/]+'),'PAYFAST/[^/]+/','') ELSE '' END
 ),'^(MR|MRS|MS|DR)[.]? +',''),' +',' ')) name_norm,
 c.business_day_index day_index
FROM MILAAN_STG.BANK_STATEMENT b JOIN MILAAN_CORE.CALENDAR c ON b.value_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.PG AS
SELECT p.*, CAST(CASE WHEN order_ref LIKE 'SFL-%' THEN order_ref END AS VARCHAR(500)) loan_id, CAST(pg_payment_id AS VARCHAR(100)) payment_ref,
 CAST(REGEXP_REPLACE(UPPER(pg_payment_id),'[^A-Z0-9]','') AS VARCHAR(100)) ref_norm,
 c.business_day_index day_index
FROM MILAAN_STG.PG_SETTLEMENT p JOIN MILAAN_CORE.CALENDAR c ON p.settlement_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.NACH AS
SELECT n.umrn,CAST(n.loan_id AS VARCHAR(500)) loan_id,n.amount_paise,n.presentation_date,n.return_date,n.return_reason,
 CAST(REGEXP_REPLACE(UPPER(umrn),'[^A-Z0-9]','') AS VARCHAR(100)) ref_norm,
 c.business_day_index day_index FROM MILAAN_STG.NACH_RETURNS n
JOIN MILAAN_CORE.CALENDAR c ON n.return_date=c.calendar_date;

ALTER TABLE MILAAN_CORE.LEDGER ADD COLUMN ref_suffix8 VARCHAR(8);
UPDATE MILAAN_CORE.LEDGER SET ref_suffix8=RIGHT(ref_norm,8);
ALTER TABLE MILAAN_CORE.BANK ADD COLUMN ref_suffix8 VARCHAR(8);
UPDATE MILAAN_CORE.BANK SET ref_suffix8=RIGHT(ref_norm,8);
CREATE OR REPLACE TABLE MILAAN_CORE.LEDGER_REFERENCE AS
SELECT external_ref FROM MILAAN_CORE.LEDGER GROUP BY external_ref;

CREATE OR REPLACE TABLE MILAAN_CORE.TXN AS
SELECT 'LEDGER' source_name, ledger_id txn_key, loan_id, ref_norm, amount_paise, posted_date txn_date, name_norm, channel, day_index FROM MILAAN_CORE.LEDGER
UNION ALL SELECT 'BANK',bank_txn_id,loan_id,ref_norm,amount_paise,value_date,name_norm,channel,day_index FROM MILAAN_CORE.BANK
UNION ALL SELECT 'PG',pg_payment_id,loan_id,ref_norm,net_paise,settlement_date,CAST(NULL AS VARCHAR(200)),'PG',day_index FROM MILAAN_CORE.PG
UNION ALL SELECT 'NACH',umrn,loan_id,ref_norm,amount_paise,return_date,CAST(NULL AS VARCHAR(200)),'NACH',day_index FROM MILAAN_CORE.NACH;

CREATE OR REPLACE TABLE MILAAN_CORE.SCORING_TRUTH AS
SELECT event_id,ledger_id,bank_txn_id,CAST(COALESCE(pg_payment_id,'NO_PG') AS VARCHAR(40)) pg_key,
 break_type,expected_match FROM MILAAN_STG.GROUND_TRUTH;

CREATE OR REPLACE TABLE MILAAN_CORE.OPEN_LEDGER AS
SELECT ledger_id,loan_id,amount_paise,channel,external_ref,posted_date,status,ref_norm,
 name_norm,day_index,duplicate_rank,ref_suffix8 FROM MILAAN_CORE.LEDGER;
CREATE OR REPLACE TABLE MILAAN_CORE.OPEN_BANK AS
SELECT bank_txn_id,value_date,bank_ref,amount_paise,ref_norm,loan_id,batch_id,channel,
 name_norm,day_index,ref_suffix8 FROM MILAAN_CORE.BANK;
CREATE OR REPLACE TABLE MILAAN_CORE.OPEN_PG AS
SELECT pg_payment_id,gross_paise,fee_paise,gst_on_fee_paise,net_paise,settlement_batch_id,
 settlement_date,settlement_utr,loan_id,payment_ref FROM MILAAN_CORE.PG;
