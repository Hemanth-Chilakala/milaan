CREATE OR REPLACE TABLE MILAAN_CORE.REMAINING_LEDGER AS
SELECT * FROM MILAAN_CORE.OPEN_LEDGER;

CREATE OR REPLACE TABLE MILAAN_CORE.REMAINING_CANDIDATE AS
SELECT DISTINCT ledger_id,bank_txn_id,amount_paise FROM (
SELECT l.ledger_id,b.bank_txn_id,b.amount_paise FROM MILAAN_CORE.REMAINING_LEDGER l
JOIN MILAAN_CORE.SAFE_BANK b ON l.ref_norm=b.ref_norm AND b.day_index-l.day_index BETWEEN 0 AND 3
UNION ALL
SELECT l.ledger_id,b.bank_txn_id,b.amount_paise FROM MILAAN_CORE.REMAINING_LEDGER l
JOIN MILAAN_CORE.SAFE_BANK b ON l.loan_id=b.loan_id AND b.day_index-l.day_index BETWEEN 0 AND 3
UNION ALL
SELECT l.ledger_id,b.bank_txn_id,b.amount_paise FROM MILAAN_CORE.REMAINING_LEDGER l
JOIN MILAAN_CORE.SAFE_BANK b ON l.ref_suffix8=b.ref_suffix8 AND l.amount_paise=b.amount_paise AND b.day_index-l.day_index BETWEEN 0 AND 3
);

CREATE OR REPLACE TABLE MILAAN_CORE.UNMATCHED_LEDGER AS
SELECT l.*,b.bank_txn_id,b.amount_paise bank_paise,n.return_reason,
 CASE WHEN r.ref_norm IS NOT NULL THEN 'BANK_REVERSAL'
 WHEN l.duplicate_rank>1 THEN 'DUPLICATE_POSTING'
 WHEN n.umrn IS NOT NULL THEN 'NACH_BOUNCE_MISPOSTED'
 WHEN b.amount_paise>0 AND b.amount_paise<l.amount_paise THEN 'PARTIAL_PAYMENT'
 WHEN b.amount_paise=l.amount_paise THEN 'NAME_MISMATCH'
 ELSE 'MISSING_IN_BANK' END category,
 GREATEST(0,c.business_day_index-l.day_index) age_business_days
FROM MILAAN_CORE.REMAINING_LEDGER l
CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date
LEFT JOIN MILAAN_CORE.REMAINING_CANDIDATE b ON l.ledger_id=b.ledger_id
LEFT JOIN (SELECT DISTINCT ref_norm,amount_paise FROM MILAAN_CORE.BANK_REVERSAL) r ON r.ref_norm=l.ref_norm AND r.amount_paise=l.amount_paise
LEFT JOIN MILAAN_CORE.NACH n ON l.ref_norm=n.ref_norm AND l.loan_id=n.loan_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY l.ledger_id ORDER BY ABS(l.amount_paise-COALESCE(b.amount_paise,0)),b.bank_txn_id)=1;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'L:'||ledger_id,'@RUN_ID@','LEDGER',ledger_id,category,loan_id,channel,amount_paise,age_business_days,
 CASE WHEN category IN ('NACH_BOUNCE_MISPOSTED','MISSING_IN_BANK','BANK_REVERSAL') THEN 5 ELSE 2 END,
 amount_paise/100.0*GREATEST(age_business_days,1)*CASE WHEN category IN ('NACH_BOUNCE_MISPOSTED','MISSING_IN_BANK','BANK_REVERSAL') THEN 5 ELSE 2 END,
 CASE WHEN category='BANK_REVERSAL' THEN 'Verify the cancelling bank debit and reverse the paid status after approval.'
 WHEN category='NACH_BOUNCE_MISPOSTED' THEN 'Reverse the paid status after verifying the NACH return; contact the collections owner.'
 WHEN category='DUPLICATE_POSTING' THEN 'Check the duplicate receipt and reverse the extra posting after approval.'
 WHEN category='PARTIAL_PAYMENT' THEN 'Allocate the received amount and investigate the unpaid balance.'
 WHEN category='NAME_MISMATCH' THEN 'Verify the candidate payer and payment reference before approving a match.'
 ELSE 'Verify the receipt with the bank before clearing the loan account.' END,
 MILAAN_CORE.EVIDENCE(ledger_id,bank_txn_id,NULL,loan_id,amount_paise,bank_paise,NULL,NULL,NULL,posted_date,CASE WHEN category='NAME_MISMATCH' THEN 'Candidate amount and reference suffix agree, but similarity or uniqueness checks failed' ELSE COALESCE(return_reason,category) END,channel,NULL,NULL,NULL,NULL,NULL)
FROM MILAAN_CORE.UNMATCHED_LEDGER;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'B:'||b.bank_txn_id,'@RUN_ID@','BANK',b.bank_txn_id,'UNIDENTIFIED_CREDIT',b.loan_id,b.channel,ABS(b.amount_paise),
 GREATEST(0,c.business_day_index-b.day_index),2,ABS(b.amount_paise)/100.0*GREATEST(c.business_day_index-b.day_index,1)*2,
 'Identify the payer and loan before releasing this credit from suspense.',
 MILAAN_CORE.EVIDENCE(NULL,b.bank_txn_id,NULL,b.loan_id,ABS(b.amount_paise),b.amount_paise,NULL,NULL,NULL,b.value_date,'No unique receipt was found',b.channel,b.batch_id,NULL,NULL,NULL,NULL)
FROM MILAAN_CORE.OPEN_BANK b CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date
WHERE NOT EXISTS (SELECT 1 FROM MILAAN_CORE.UNMATCHED_LEDGER l WHERE l.bank_txn_id=b.bank_txn_id);

CREATE OR REPLACE TABLE MILAAN_CORE.MISSING_PG AS
SELECT p.* FROM MILAAN_CORE.PG p
LEFT JOIN MILAAN_CORE.LEDGER_REFERENCE lr ON lr.external_ref=p.payment_ref
WHERE p.gross_paise>0 AND lr.external_ref IS NULL;

CREATE OR REPLACE TABLE MILAAN_CORE.BANK_LINK_COUNT AS
SELECT x.bank_txn_id,COUNT(*) matched_count FROM MILAAN_RES.LINK x
JOIN (SELECT DISTINCT b.bank_txn_id FROM MILAAN_CORE.SAFE_BANK b
 JOIN MILAAN_CORE.MISSING_PG p ON b.batch_id=p.settlement_batch_id AND b.bank_ref=p.settlement_utr) eligible
ON x.bank_txn_id=eligible.bank_txn_id GROUP BY x.bank_txn_id;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'PG:'||p.pg_payment_id,'@RUN_ID@','PG',p.pg_payment_id,'MISSING_IN_LEDGER',p.loan_id,'PG',p.gross_paise,
 GREATEST(0,c.business_day_index-p.day_index),3,p.gross_paise/100.0*GREATEST(c.business_day_index-p.day_index,1)*3,
 'Verify the gateway payment and post the missing receipt to the correct loan.',
 MILAAN_CORE.EVIDENCE(NULL,b.bank_txn_id,p.pg_payment_id,p.loan_id,p.gross_paise,b.amount_paise,g.fee_paise,g.gst_paise,g.refund_paise,p.payment_date,'Gateway payment has no ledger receipt','PG',p.settlement_batch_id,g.payment_count,
 COALESCE(lc.matched_count,0),g.gross_paise,g.net_paise)
FROM MILAAN_CORE.MISSING_PG p JOIN MILAAN_CORE.BATCH g ON p.settlement_batch_id=g.batch_id AND p.settlement_utr=g.settlement_utr
LEFT JOIN MILAAN_CORE.SAFE_BANK b ON b.batch_id=p.settlement_batch_id AND b.bank_ref=p.settlement_utr
LEFT JOIN MILAAN_CORE.BANK_LINK_COUNT lc ON b.bank_txn_id=lc.bank_txn_id
CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'RV:'||r.credit_id||':'||r.debit_id,'@RUN_ID@','BANK',r.credit_id,'BANK_REVERSAL',r.loan_id,r.channel,r.amount_paise,
 GREATEST(0,c.business_day_index-r.day_index),5,r.amount_paise/100.0*GREATEST(c.business_day_index-r.day_index,1)*5,
 'Verify the cancelling bank debit and reverse any paid posting after approval.',
 MILAAN_CORE.EVIDENCE(NULL,r.credit_id,NULL,r.loan_id,r.amount_paise,r.amount_paise,NULL,NULL,NULL,r.reversal_date,
 'Cancelled by debit '||r.debit_id||'; same reference and amount','UPI',NULL,NULL,NULL,NULL,NULL)
FROM MILAAN_CORE.BANK_REVERSAL r CROSS JOIN MILAAN_AUDIT.DATASET d
JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date;
