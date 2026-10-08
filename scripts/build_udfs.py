"""Embed tested pure Python functions into deployable Exasol CREATE SCRIPT files."""

import inspect
from pathlib import Path

from milaan.explain import explain, rupees
from milaan.matching import jaro_winkler, unique_subset

ROOT = Path(__file__).resolve().parents[1]


def build() -> None:
    folder = ROOT / "udf"
    folder.mkdir(exist_ok=True)
    (folder / "04_explain.sql").write_text(
        "CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MILAAN_CORE.EXPLAIN(category VARCHAR(40), evidence VARCHAR(10000)) RETURNS VARCHAR(10000) AS\n"
        + "import json\n"
        + inspect.getsource(rupees)
        + "\n"
        + inspect.getsource(explain)
        + "\ndef run(ctx):\n    return explain(ctx.category, ctx.evidence)\n/\n"
    )
    (folder / "01_similarity.sql").write_text(
        "CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MILAAN_CORE.SIMILARITY(a VARCHAR(200), b VARCHAR(200)) RETURNS DOUBLE AS\n"
        + inspect.getsource(jaro_winkler)
        + "\ndef run(ctx):\n    return jaro_winkler(ctx.a, ctx.b)\n/\n"
    )
    (folder / "02_subset.sql").write_text(
        "CREATE OR REPLACE PYTHON3 SET SCRIPT MILAAN_CORE.SUBSET(ledger_key VARCHAR(40), bank_key VARCHAR(40), target DECIMAL(18,0), amount DECIMAL(18,0)) EMITS (ledger_id VARCHAR(40), bank_txn_id VARCHAR(40)) AS\n"
        + "from itertools import combinations\n"
        + inspect.getsource(unique_subset)
        + "\ndef run(ctx):\n    ledger = ctx.ledger_key\n    target = int(ctx.target)\n    payments = []\n    while True:\n        payments.append((ctx.bank_key, int(ctx.amount)))\n        if len(payments) > 12:\n            return\n        if not ctx.next():\n            break\n    subset = unique_subset(target, payments)\n    if subset:\n        for bank in subset:\n            ctx.emit(ledger, bank)\n/\n"
    )


if __name__ == "__main__":
    build()
