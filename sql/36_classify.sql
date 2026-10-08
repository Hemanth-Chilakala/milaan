CREATE OR REPLACE TABLE MILAAN_CORE.REMAINING_LEDGER AS
SELECT l.* FROM MILAAN_CORE.LEDGER l
WHERE NOT EXISTS (SELECT 1 FROM MILAAN_RES.LINK x WHERE x.ledger_id=l.ledger_id);

CREATE OR REPLACE TABLE MILAAN_CORE.REMAINING_CANDIDATE AS
SELECT l.ledger_id,b.bank_txn_id,b.amount_paise FROM MILAAN_CORE.REMAINING_LEDGER l
JOIN MILAAN_CORE.BANK b ON l.ref_norm=b.ref_norm AND b.day_index-l.day_index BETWEEN 0 AND 3
UNION
SELECT l.ledger_id,b.bank_txn_id,b.amount_paise FROM MILAAN_CORE.REMAINING_LEDGER l
JOIN MILAAN_CORE.BANK b ON l.loan_id=b.loan_id AND b.day_index-l.day_index BETWEEN 0 AND 3;

CREATE OR REPLACE TABLE MILAAN_CORE.UNMATCHED_LEDGER AS
SELECT l.*,b.bank_txn_id,b.amount_paise bank_paise,n.return_reason,
 CASE WHEN l.duplicate_rank>1 THEN 'DUPLICATE_POSTING'
 WHEN n.umrn IS NOT NULL THEN 'NACH_BOUNCE_MISPOSTED'
 WHEN b.amount_paise>0 AND b.amount_paise<l.amount_paise THEN 'PARTIAL_PAYMENT'
 ELSE 'MISSING_IN_BANK' END category,
 GREATEST(0,c.business_day_index-l.day_index) age_business_days
FROM MILAAN_CORE.REMAINING_LEDGER l
CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date
LEFT JOIN MILAAN_CORE.REMAINING_CANDIDATE b ON l.ledger_id=b.ledger_id
LEFT JOIN MILAAN_CORE.NACH n ON l.ref_norm=n.ref_norm AND l.loan_id=n.loan_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY l.ledger_id ORDER BY ABS(l.amount_paise-COALESCE(b.amount_paise,0)),b.bank_txn_id)=1;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'L:'||ledger_id,'@RUN_ID@','LEDGER',ledger_id,category,loan_id,channel,amount_paise,age_business_days,
 CASE WHEN category IN ('NACH_BOUNCE_MISPOSTED','MISSING_IN_BANK') THEN 5 ELSE 2 END,
 amount_paise/100.0*GREATEST(age_business_days,1)*CASE WHEN category IN ('NACH_BOUNCE_MISPOSTED','MISSING_IN_BANK') THEN 5 ELSE 2 END,
 CASE WHEN category='NACH_BOUNCE_MISPOSTED' THEN 'Reverse the paid status after verifying the NACH return; contact the collections owner.'
 WHEN category='DUPLICATE_POSTING' THEN 'Check the duplicate receipt and reverse the extra posting after approval.'
 WHEN category='PARTIAL_PAYMENT' THEN 'Allocate the received amount and investigate the unpaid balance.'
 ELSE 'Verify the receipt with the bank before clearing the loan account.' END,
 MILAAN_CORE.EVIDENCE(ledger_id,bank_txn_id,NULL,loan_id,amount_paise,bank_paise,NULL,NULL,NULL,posted_date,COALESCE(return_reason,category),channel,NULL,NULL,NULL,NULL,NULL)
FROM MILAAN_CORE.UNMATCHED_LEDGER;

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'B:'||b.bank_txn_id,'@RUN_ID@','BANK',b.bank_txn_id,'UNIDENTIFIED_CREDIT',b.loan_id,b.channel,ABS(b.amount_paise),
 GREATEST(0,c.business_day_index-b.day_index),2,ABS(b.amount_paise)/100.0*GREATEST(c.business_day_index-b.day_index,1)*2,
 'Identify the payer and loan before releasing this credit from suspense.',
 MILAAN_CORE.EVIDENCE(NULL,b.bank_txn_id,NULL,b.loan_id,ABS(b.amount_paise),b.amount_paise,NULL,NULL,NULL,b.value_date,'No unique receipt was found',b.channel,b.batch_id,NULL,NULL,NULL,NULL)
FROM MILAAN_CORE.BANK b CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date
WHERE NOT EXISTS (SELECT 1 FROM MILAAN_RES.LINK x WHERE x.bank_txn_id=b.bank_txn_id)
AND NOT EXISTS (SELECT 1 FROM MILAAN_CORE.UNMATCHED_LEDGER l WHERE l.bank_txn_id=b.bank_txn_id);

INSERT INTO MILAAN_RES."EXCEPTION"
SELECT 'PG:'||p.pg_payment_id,'@RUN_ID@','PG',p.pg_payment_id,'MISSING_IN_LEDGER',p.loan_id,'PG',p.gross_paise,
 GREATEST(0,c.business_day_index-p.day_index),3,p.gross_paise/100.0*GREATEST(c.business_day_index-p.day_index,1)*3,
 'Verify the gateway payment and post the missing receipt to the correct loan.',
 MILAAN_CORE.EVIDENCE(NULL,b.bank_txn_id,p.pg_payment_id,p.loan_id,p.gross_paise,b.amount_paise,g.fee_paise,g.gst_paise,g.refund_paise,p.payment_date,'Gateway payment has no ledger receipt','PG',p.settlement_batch_id,g.payment_count,
 (SELECT COUNT(*) FROM MILAAN_RES.LINK x WHERE x.bank_txn_id=b.bank_txn_id),g.gross_paise,g.net_paise)
FROM MILAAN_CORE.PG p JOIN MILAAN_CORE.BATCH g ON p.settlement_batch_id=g.batch_id AND p.settlement_utr=g.settlement_utr
LEFT JOIN MILAAN_CORE.BANK b ON b.batch_id=p.settlement_batch_id AND b.bank_ref=p.settlement_utr
CROSS JOIN MILAAN_AUDIT.DATASET d JOIN MILAAN_CORE.CALENDAR c ON c.calendar_date=d.as_of_date
WHERE p.gross_paise>0 AND NOT EXISTS (SELECT 1 FROM MILAAN_CORE.LEDGER l WHERE l.external_ref=p.pg_payment_id);
