CREATE OR REPLACE LUA SCALAR SCRIPT MILAAN_CORE.EVIDENCE(
 ledger_key VARCHAR(40), bank_key VARCHAR(40), pg_key VARCHAR(40), loan VARCHAR(40),
 amount DECIMAL(18,0), bank_amount DECIMAL(18,0), fee DECIMAL(18,0), gst DECIMAL(18,0), refund DECIMAL(18,0),
 txn_day VARCHAR(10), reason VARCHAR(100), channel_name VARCHAR(10), batch VARCHAR(80),
 total_count DECIMAL(10,0), matched_count DECIMAL(10,0), gross_total DECIMAL(18,0), net_total DECIMAL(18,0)
) RETURNS VARCHAR(10000) AS
local json = require("cjson")
local fields = {
 {"amount_paise", "amount", true}, {"bank_paise", "bank_amount", true},
 {"bank_txn_id", "bank_key"}, {"batch_id", "batch"}, {"channel", "channel_name"},
 {"date", "txn_day"}, {"fee_paise", "fee", true}, {"gross_total_paise", "gross_total", true},
 {"gst_paise", "gst", true}, {"ledger_id", "ledger_key"}, {"loan_id", "loan"},
 {"matched_count", "matched_count", true}, {"net_total_paise", "net_total", true},
 {"payment_count", "total_count", true}, {"pg_payment_id", "pg_key"},
 {"reason", "reason"}, {"refund_paise", "refund", true}
}
function run(ctx)
 local parts = {}
 for _, field in ipairs(fields) do
  local value = ctx[field[2]]
  local encoded
  if value == NULL then
   encoded = field[1] == "date" and '"None"' or "null"
  elseif field[3] then
   -- Native decimal text keeps every paise exact, including values above 2^53.
   encoded = tostring(value)
  else
   encoded = json.encode(value)
  end
  parts[#parts+1] = json.encode(field[1]) .. ": " .. encoded
 end
 return "{" .. table.concat(parts, ", ") .. "}"
end
/
