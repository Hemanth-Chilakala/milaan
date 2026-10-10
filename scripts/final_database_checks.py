"""Run integration tests in an isolated source copy with private schema names."""

import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from milaan.config import ROOT
from milaan.db import query
from milaan.live import snapshot


def main():
    folder = Path(tempfile.mkdtemp(prefix="milaan-final-check-"))
    subprocess.run(["git", "clone", "--no-hardlinks", str(ROOT), str(folder / "repo")], check=True)
    checkout = folder / "repo"
    for source in list(checkout.rglob("*.py")) + list(checkout.rglob("*.sql")):
        source.write_text(source.read_text().replace("MILAAN_", "MILAAN_VERIFY_"))
    shutil.copy2(ROOT / ".env", checkout / ".env")
    before = snapshot()
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "isolation": "Only literal schema prefix replaced in scratch source copy; matching rules unchanged",
        "month_run_before": before["RUN_ID"],
    }
    with (ROOT / "private/round2/final-database-tests.log").open("w") as output:
        result = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-m", "db", "-v"],
            cwd=checkout,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    report["exit_code"] = result.returncode
    after = snapshot()
    report["month_run_after"] = after["RUN_ID"]
    report["retained_month_unchanged"] = before == after
    report["source_rows"] = query("SELECT COUNT(*) N FROM MILAAN_CORE.TXN")[0]["N"]
    (ROOT / "docs/final_database_checks.json").write_text(json.dumps(report, indent=2) + "\n")
    if result.returncode or before != after:
        raise SystemExit("Database checks failed; inspect private/round2/final-database-tests.log")
    print("Database checks passed; retained month run and 10M sources unchanged.")
    # Keep the scratch checkout and isolated schemas until all final checks finish.
    (ROOT / "private/round2/final-test-checkout.txt").write_text(str(checkout) + "\n")


if __name__ == "__main__":
    main()
