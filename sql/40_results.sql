INSERT INTO MILAAN_RES."MATCH"
SELECT match_id,'@RUN_ID@',MIN(pass_name),MIN(rule),MIN(confidence),
 LISTAGG(DISTINCT ledger_id,',') WITHIN GROUP (ORDER BY ledger_id),
 LISTAGG(DISTINCT bank_txn_id,',') WITHIN GROUP (ORDER BY bank_txn_id),
 '{"rule":"'||MIN(rule)||'","ledger_bank_edges":'||COUNT(*)||'}',CURRENT_TIMESTAMP
FROM MILAAN_RES.LINK GROUP BY match_id;

INSERT INTO MILAAN_RES.MATCH_MEMBER
SELECT DISTINCT match_id,'LEDGER',ledger_id FROM MILAAN_RES.LINK
UNION SELECT DISTINCT match_id,'BANK',bank_txn_id FROM MILAAN_RES.LINK
UNION SELECT DISTINCT match_id,'PG',pg_payment_id FROM MILAAN_RES.LINK WHERE pg_payment_id IS NOT NULL
UNION SELECT DISTINCT x.match_id,'PG',p.pg_payment_id FROM MILAAN_RES.LINK x
JOIN MILAAN_CORE.BANK b ON x.bank_txn_id=b.bank_txn_id
JOIN MILAAN_CORE.PG p ON p.settlement_batch_id=b.batch_id AND p.settlement_utr=b.bank_ref
WHERE x.pass_name='PG_BATCH';
