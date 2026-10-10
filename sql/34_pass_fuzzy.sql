INSERT INTO MILAAN_RES.LINK
WITH blocked_candidates AS (
 SELECT l.ledger_id,b.bank_txn_id,l.name_norm left_name,b.name_norm right_name,l.ref_norm left_ref,b.ref_norm right_ref,b.day_index-l.day_index date_distance
 FROM MILAAN_CORE.OPEN_LEDGER l JOIN MILAAN_CORE.OPEN_BANK b
 ON l.amount_paise=b.amount_paise AND l.ref_suffix8=b.ref_suffix8 AND b.day_index-l.day_index BETWEEN 0 AND 3
 WHERE l.duplicate_rank=1 AND l.channel='UPI' AND b.channel='UPI' AND b.loan_id IS NULL
), similarities AS (
 SELECT blocked_candidates.*,MILAAN_CORE.SIMILARITY(left_name,right_name) name_score,CASE WHEN LENGTH(left_ref)=12 AND LENGTH(right_ref)=12 AND EDIT_DISTANCE(left_ref,right_ref)=1 THEN 11.0/12 ELSE MILAAN_CORE.SIMILARITY(left_ref,right_ref) END ref_score FROM blocked_candidates
), scored AS (
 SELECT similarities.*,0.55*name_score+0.30*ref_score+0.15*(1-date_distance/4.0) similarity_score FROM similarities
 WHERE name_score>=0.93 AND ref_score>=0.90
), candidates AS (
 SELECT scored.*,COUNT(*) OVER (PARTITION BY ledger_id) lc,COUNT(*) OVER (PARTITION BY bank_txn_id) bc
 FROM scored WHERE similarity_score>=0.94
)
SELECT 'N:'||bank_txn_id,ledger_id,bank_txn_id,CAST(NULL AS VARCHAR(40)),'FUZZY',similarity_score,'Unique reference-suffix block; Jaro-Winkler name and reference thresholds passed'
FROM candidates WHERE lc=1 AND bc=1;
