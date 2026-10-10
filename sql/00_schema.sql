CREATE SCHEMA IF NOT EXISTS MILAAN_STG;
CREATE SCHEMA IF NOT EXISTS MILAAN_CORE;
CREATE SCHEMA IF NOT EXISTS MILAAN_RES;
CREATE SCHEMA IF NOT EXISTS MILAAN_AUDIT;

CREATE TABLE IF NOT EXISTS MILAAN_STG.LEDGER (
 ledger_id VARCHAR(40), loan_id VARCHAR(40), customer_name VARCHAR(200), emi_due_date DATE,
 amount_paise DECIMAL(18,0), channel VARCHAR(10), external_ref VARCHAR(100), posted_date DATE, status VARCHAR(20)
);
CREATE TABLE IF NOT EXISTS MILAAN_STG.BANK_STATEMENT (
 bank_txn_id VARCHAR(40), value_date DATE, narration VARCHAR(500), credit_paise DECIMAL(18,0), debit_paise DECIMAL(18,0), bank_ref VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS MILAAN_STG.PG_SETTLEMENT (
 pg_payment_id VARCHAR(40), order_ref VARCHAR(100), gross_paise DECIMAL(18,0), fee_paise DECIMAL(18,0), gst_on_fee_paise DECIMAL(18,0), net_paise DECIMAL(18,0), payment_date DATE, settlement_batch_id VARCHAR(80), settlement_date DATE, settlement_utr VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS MILAAN_STG.NACH_RETURNS (
 umrn VARCHAR(100), loan_id VARCHAR(40), amount_paise DECIMAL(18,0), presentation_date DATE, return_date DATE, return_reason VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS MILAAN_STG.GROUND_TRUTH (
 event_id VARCHAR(40), ledger_id VARCHAR(40), bank_txn_id VARCHAR(40), pg_payment_id VARCHAR(40), break_type VARCHAR(40), expected_match DECIMAL(1,0), expected_category VARCHAR(40), ledger_paise DECIMAL(18,0), bank_paise DECIMAL(18,0), fee_paise DECIMAL(18,0), gst_paise DECIMAL(18,0), refund_paise DECIMAL(18,0)
);
CREATE TABLE IF NOT EXISTS MILAAN_CORE.CALENDAR (
 calendar_date DATE, business_day_index DECIMAL(10,0), is_business_day DECIMAL(1,0)
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.DATASET (
 dataset_id VARCHAR(36), label VARCHAR(200), source_rows DECIMAL(18,0), as_of_date DATE, manifest VARCHAR(2000000), loaded_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.RUN_LOG (
 run_id VARCHAR(36), operation VARCHAR(50), source_file VARCHAR(100), row_count DECIMAL(18,0), seconds DOUBLE, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.RUN (
 run_id VARCHAR(36), dataset_id VARCHAR(36), status VARCHAR(20), started_at TIMESTAMP, finished_at TIMESTAMP, seconds DOUBLE, message VARCHAR(2000)
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.PASS_TIMING (
 run_id VARCHAR(36), pass_name VARCHAR(40), seconds DOUBLE, links_added DECIMAL(18,0), profile_json VARCHAR(2000000)
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.RUN_LIVE (
 run_id VARCHAR(36),status VARCHAR(20),current_pass VARCHAR(40),started_epoch_ms DECIMAL(18,0),
 elapsed_seconds DOUBLE,links_found DECIMAL(18,0),members DECIMAL(18,0),source_rows DECIMAL(18,0),
 open_paise DECIMAL(18,0),before_paise DECIMAL(18,0),updated_epoch_ms DECIMAL(18,0)
);
CREATE TABLE IF NOT EXISTS MILAAN_AUDIT.DECISION (
 decision_id VARCHAR(36), run_id VARCHAR(36), exception_id VARCHAR(100), decision_action VARCHAR(20), analyst VARCHAR(100), assignee VARCHAR(100), note VARCHAR(2000), created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS MILAAN_RES.LINK (
 match_id VARCHAR(100), ledger_id VARCHAR(40), bank_txn_id VARCHAR(40), pg_payment_id VARCHAR(40), pass_name VARCHAR(40), confidence DOUBLE, rule VARCHAR(500)
);
CREATE TABLE IF NOT EXISTS MILAAN_RES."MATCH" (
 match_id VARCHAR(100), run_id VARCHAR(36), pass_name VARCHAR(40), rule VARCHAR(500), confidence DOUBLE, left_keys VARCHAR(10000), right_keys VARCHAR(10000), evidence VARCHAR(10000), created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS MILAAN_RES.MATCH_MEMBER (
 match_id VARCHAR(100), source_name VARCHAR(20), txn_key VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS MILAAN_RES."EXCEPTION" (
 exception_id VARCHAR(100), run_id VARCHAR(36), source_name VARCHAR(20), txn_key VARCHAR(100), category VARCHAR(40), loan_id VARCHAR(40), channel VARCHAR(10), amount_paise DECIMAL(18,0), age_business_days DECIMAL(10,0), risk_weight DECIMAL(3,0), priority_score DOUBLE, suggested_action VARCHAR(500), evidence VARCHAR(10000)
);
CREATE TABLE IF NOT EXISTS MILAAN_RES.EXPLANATION (
 exception_id VARCHAR(100), explanation VARCHAR(10000)
);
CREATE TABLE IF NOT EXISTS MILAAN_RES.SCORE (
 run_id VARCHAR(36), break_type VARCHAR(40), true_positive DECIMAL(18,0), false_positive DECIMAL(18,0), false_negative DECIMAL(18,0), precision_value DOUBLE, recall_value DOUBLE, auto_match_rate DOUBLE, false_match_rate DOUBLE
);
