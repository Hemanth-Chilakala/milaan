CREATE OR REPLACE LUA SET SCRIPT MILAAN_CORE.SUBSET(ledger_key VARCHAR(40), bank_key VARCHAR(40), target DECIMAL(18,0), amount DECIMAL(18,0)) EMITS (ledger_id VARCHAR(40), bank_txn_id VARCHAR(40)) AS
function run(ctx)
 local ledger = ctx.ledger_key
 local target = ctx.target
 local payments, seen = {}, {}
 if target <= 0 then return end
 repeat
  local key = ctx.bank_key
  if seen[key] or #payments >= 12 then return end
  seen[key] = true
  payments[#payments+1] = {key=key, amount=ctx.amount}
 until not ctx.next()
 table.sort(payments, function(a,b) return a.key < b.key end)
 local solution, solutions = nil, 0
 for i=1,#payments-1 do
  for j=i+1,#payments do
   if payments[i].amount > 0 and payments[j].amount > 0 and payments[i].amount + payments[j].amount == target then
    solutions = solutions + 1
    if solutions > 1 then return end
    solution = {payments[i].key, payments[j].key}
   end
  end
 end
 for i=1,#payments-2 do
  for j=i+1,#payments-1 do
   for k=j+1,#payments do
    if payments[i].amount > 0 and payments[j].amount > 0 and payments[k].amount > 0 and payments[i].amount + payments[j].amount + payments[k].amount == target then
     solutions = solutions + 1
     if solutions > 1 then return end
     solution = {payments[i].key, payments[j].key, payments[k].key}
    end
   end
  end
 end
 if solution then
  for _,key in ipairs(solution) do ctx.emit(ledger,key) end
 end
end
/
