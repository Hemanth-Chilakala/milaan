"""Embed tested pure Python functions into deployable Exasol CREATE SCRIPT files."""

import inspect
from pathlib import Path

from milaan.explain import explain, rupees
from milaan.matching import jaro_winkler

ROOT = Path(__file__).resolve().parents[1]


def build() -> None:
    folder = ROOT / "udf"
    folder.mkdir(exist_ok=True)
    (folder / "04_explain.sql").write_text(
        "CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MILAAN_CORE.EXPLAIN(category VARCHAR(40), evidence VARCHAR(10000)) RETURNS VARCHAR(10000) AS\n"
        + "import json\nfrom datetime import date\n"
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
    # The bounded SET script is maintained directly in udf/02_subset.sql (Lua).


if __name__ == "__main__":
    build()
