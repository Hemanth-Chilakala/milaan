INSERT INTO MILAAN_RES."MATCH"
SELECT match_id,'@RUN_ID@',pass_name,rule,confidence,ledger_id,bank_txn_id,
 '{"rule":"'||rule||'","ledger_bank_edges":1}',CURRENT_TIMESTAMP
FROM MILAAN_RES.LINK WHERE pass_name NOT IN ('PG_BATCH','SPLIT_MERGE');

INSERT INTO MILAAN_RES."MATCH"
SELECT match_id,'@RUN_ID@',MIN(pass_name),MIN(rule),MIN(confidence),
 LISTAGG(DISTINCT ledger_id,',') WITHIN GROUP (ORDER BY ledger_id),
 LISTAGG(DISTINCT bank_txn_id,',') WITHIN GROUP (ORDER BY bank_txn_id),
 '{"rule":"'||MIN(rule)||'","ledger_bank_edges":'||COUNT(*)||'}',CURRENT_TIMESTAMP
FROM MILAAN_RES.LINK WHERE pass_name IN ('PG_BATCH','SPLIT_MERGE') GROUP BY match_id;

INSERT INTO MILAAN_RES.MATCH_MEMBER
SELECT match_id,'LEDGER',ledger_id FROM MILAAN_RES.LINK WHERE pass_name<>'SPLIT_MERGE'
UNION ALL SELECT DISTINCT match_id,'LEDGER',ledger_id FROM MILAAN_RES.LINK WHERE pass_name='SPLIT_MERGE'
UNION ALL SELECT match_id,'BANK',bank_txn_id FROM MILAAN_RES.LINK WHERE pass_name<>'PG_BATCH'
UNION ALL SELECT DISTINCT match_id,'BANK',bank_txn_id FROM MILAAN_RES.LINK WHERE pass_name='PG_BATCH'
UNION ALL SELECT match_id,'PG',pg_payment_id FROM MILAAN_RES.LINK WHERE pg_payment_id IS NOT NULL AND pass_name<>'PG_BATCH'
UNION ALL SELECT DISTINCT x.match_id,'PG',p.pg_payment_id FROM (SELECT DISTINCT match_id,bank_txn_id FROM MILAAN_RES.LINK WHERE pass_name='PG_BATCH') x
JOIN MILAAN_CORE.BANK b ON x.bank_txn_id=b.bank_txn_id
JOIN MILAAN_CORE.PG p ON p.settlement_batch_id=b.batch_id AND p.settlement_utr=b.bank_ref
;
