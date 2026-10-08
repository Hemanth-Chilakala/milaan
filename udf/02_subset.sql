CREATE OR REPLACE PYTHON3 SET SCRIPT MILAAN_CORE.SUBSET(ledger_key VARCHAR(40), bank_key VARCHAR(40), target DECIMAL(18,0), amount DECIMAL(18,0)) EMITS (ledger_id VARCHAR(40), bank_txn_id VARCHAR(40)) AS
from itertools import combinations
def unique_subset(target: int, payments: list[tuple[str, int]], cap: int = 12):
    """Return the only 2–3-credit solution; leave large or ambiguous groups for review."""
    if len(payments) > cap or target <= 0 or len({key for key, _ in payments}) != len(payments):
        return None
    solutions = []
    for size in (2, 3):
        for group in combinations(sorted(payments), size):
            if sum(amount for _, amount in group) == target and all(
                amount > 0 for _, amount in group
            ):
                solutions.append(tuple(key for key, _ in group))
                if len(solutions) > 1:
                    return None
    return solutions[0] if solutions else None

def run(ctx):
    ledger = ctx.ledger_key
    target = int(ctx.target)
    payments = []
    while True:
        payments.append((ctx.bank_key, int(ctx.amount)))
        if len(payments) > 12:
            return
        if not ctx.next():
            break
    subset = unique_subset(target, payments)
    if subset:
        for bank in subset:
            ctx.emit(ledger, bank)
/
