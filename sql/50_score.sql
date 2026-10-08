CREATE OR REPLACE TABLE MILAAN_CORE.SCORING_EDGE AS
SELECT g.break_type, g.expected_match, CASE WHEN x.match_id IS NOT NULL THEN 1 ELSE 0 END predicted_match,
 CASE WHEN g.expected_match=1 AND x.match_id IS NOT NULL THEN 1 ELSE 0 END tp,
 CASE WHEN g.expected_match=0 AND x.match_id IS NOT NULL THEN 1 ELSE 0 END fp,
 CASE WHEN g.expected_match=1 AND x.match_id IS NULL THEN 1 ELSE 0 END fn
FROM MILAAN_STG.GROUND_TRUTH g LEFT JOIN MILAAN_RES.LINK x
ON g.ledger_id=x.ledger_id AND g.bank_txn_id=x.bank_txn_id AND COALESCE(g.pg_payment_id,'NO_PG')=COALESCE(x.pg_payment_id,'NO_PG');

INSERT INTO MILAAN_RES.SCORE
WITH missing_truth AS (
 SELECT COUNT(*) n FROM MILAAN_RES.LINK x WHERE NOT EXISTS (
 SELECT 1 FROM MILAAN_STG.GROUND_TRUTH g WHERE g.expected_match=1 AND g.ledger_id=x.ledger_id AND g.bank_txn_id=x.bank_txn_id AND COALESCE(g.pg_payment_id,'NO_PG')=COALESCE(x.pg_payment_id,'NO_PG')
 )
), totals AS (
 SELECT 'OVERALL' break_type,SUM(tp) tp,(SELECT n FROM missing_truth) fp,SUM(fn) fn FROM MILAAN_CORE.SCORING_EDGE
 UNION ALL SELECT break_type,SUM(tp),SUM(fp),SUM(fn) FROM MILAAN_CORE.SCORING_EDGE GROUP BY break_type
)
SELECT '@RUN_ID@',break_type,tp,fp,fn,
 CASE WHEN tp+fp=0 THEN NULL ELSE tp*1.0/(tp+fp) END,
 CASE WHEN tp+fn=0 THEN NULL ELSE tp*1.0/(tp+fn) END,
 (SELECT COUNT(*) FROM MILAAN_RES.MATCH_MEMBER)*1.0/(SELECT source_rows FROM MILAAN_AUDIT.DATASET),
 CASE WHEN tp+fp=0 THEN NULL ELSE fp*1.0/(tp+fp) END
FROM totals;
