CREATE OR REPLACE TABLE MILAAN_CORE.LEDGER AS
SELECT l.*, REGEXP_REPLACE(UPPER(external_ref),'[^A-Z0-9]','') ref_norm,
 TRIM(REGEXP_REPLACE(REGEXP_REPLACE(UPPER(customer_name),'^(MR|MRS|MS|DR)[.]? +',''),' +',' ')) name_norm,
 c.business_day_index day_index,
 ROW_NUMBER() OVER (PARTITION BY external_ref,loan_id,amount_paise ORDER BY posted_date,ledger_id) duplicate_rank
FROM MILAAN_STG.LEDGER l JOIN MILAAN_CORE.CALENDAR c ON l.posted_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.BANK AS
SELECT b.*, credit_paise-debit_paise amount_paise,
 REGEXP_REPLACE(UPPER(bank_ref),'[^A-Z0-9]','') ref_norm,
 REGEXP_SUBSTR(narration,'LN-[0-9]+(-[0-9]+)?') loan_id,
 REGEXP_SUBSTR(narration,'B-[0-9]{8}-[0-9]+') batch_id,
 REGEXP_SUBSTR(narration,'SAHY[0-9]+') utr,
 REGEXP_SUBSTR(narration,'BUB[0-9]+') umrn,
 CASE WHEN narration LIKE 'UPI/%' THEN 'UPI' WHEN narration LIKE 'NACH%' THEN 'NACH' WHEN narration LIKE '%PAYFAST%' THEN 'PG' ELSE 'NEFT' END channel,
 TRIM(REGEXP_REPLACE(REGEXP_REPLACE(UPPER(
 CASE WHEN narration LIKE 'UPI/CR/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'UPI/CR/[^/]+/[^/]+'),'UPI/CR/[^/]+/','')
 WHEN narration LIKE 'NEFT/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'NEFT/[^/]+/[^/]+'),'NEFT/[^/]+/','')
 WHEN narration LIKE 'PAYFAST/%' THEN REGEXP_REPLACE(REGEXP_SUBSTR(narration,'PAYFAST/[^/]+/[^/]+'),'PAYFAST/[^/]+/','') ELSE '' END
 ),'^(MR|MRS|MS|DR)[.]? +',''),' +',' ')) name_norm,
 c.business_day_index day_index
FROM MILAAN_STG.BANK_STATEMENT b JOIN MILAAN_CORE.CALENDAR c ON b.value_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.PG AS
SELECT p.*, CASE WHEN order_ref LIKE 'LN-%' THEN order_ref END loan_id,
 REGEXP_REPLACE(UPPER(pg_payment_id),'[^A-Z0-9]','') ref_norm,
 c.business_day_index day_index
FROM MILAAN_STG.PG_SETTLEMENT p JOIN MILAAN_CORE.CALENDAR c ON p.settlement_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.NACH AS
SELECT n.*, REGEXP_REPLACE(UPPER(umrn),'[^A-Z0-9]','') ref_norm,
 c.business_day_index day_index FROM MILAAN_STG.NACH_RETURNS n
JOIN MILAAN_CORE.CALENDAR c ON n.return_date=c.calendar_date;

CREATE OR REPLACE TABLE MILAAN_CORE.TXN AS
SELECT 'LEDGER' source_name, ledger_id txn_key, loan_id, ref_norm, amount_paise, posted_date txn_date, name_norm, channel, day_index FROM MILAAN_CORE.LEDGER
UNION ALL SELECT 'BANK',bank_txn_id,loan_id,ref_norm,amount_paise,value_date,name_norm,channel,day_index FROM MILAAN_CORE.BANK
UNION ALL SELECT 'PG',pg_payment_id,loan_id,ref_norm,net_paise,settlement_date,CAST(NULL AS VARCHAR(200)),'PG',day_index FROM MILAAN_CORE.PG
UNION ALL SELECT 'NACH',umrn,loan_id,ref_norm,amount_paise,return_date,CAST(NULL AS VARCHAR(200)),'NACH',day_index FROM MILAAN_CORE.NACH;
