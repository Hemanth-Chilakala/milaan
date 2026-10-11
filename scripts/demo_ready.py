"""Check retained demo state and warm dashboard pages without changing results."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from urllib.error import URLError
from urllib.request import urlopen

from milaan.analytics import batch_evidence, detail, showcase_id, summary
from milaan.config import ROOT
from milaan.db import query, scope
from milaan.demo import is_running
from milaan.live import snapshot


def check(url="http://127.0.0.1:8501"):
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "checks": [], "errors": []}

    def passed(message):
        report["checks"].append(message)
        print("OK: " + message, flush=True)

    if is_running():
        report["errors"].append("A reconciliation is running; wait for it to finish.")
        return report
    try:
        if query("SELECT MILAAN_CHECK.PING() AS PING")[0]["PING"] != "pong":
            raise RuntimeError("Python UDF did not return pong")
        passed("Database connection and Python UDF")
        with scope("month"):
            data = summary()
            live = snapshot()
            if not data or data["SOURCE_ROWS"] != 10000000:
                raise RuntimeError("Load the retained 10M demonstration dataset first.")
            if not live or live["STATUS"] != "COMPLETE":
                raise RuntimeError("Complete a monthly reconciliation before the demo-ready check.")
            run = data["RUN"]
            age = query(
                "SELECT SECONDS_BETWEEN(CURRENT_TIMESTAMP,finished_at) AGE FROM MILAAN_AUDIT.RUN WHERE run_id={id!s}",
                {"id": run["RUN_ID"]},
            )[0]["AGE"]
            if age is None or float(age) < 0 or float(age) > timedelta(days=1).total_seconds():
                raise RuntimeError(
                    "The completed month run is older than 24 hours; rerun reconciliation."
                )
            if len(live["PASSES"]) != 7:
                raise RuntimeError("The completed run does not have all seven pass timings.")
            row = detail(showcase_id())
            if not row or not row["EXPLANATION"]:
                raise RuntimeError("Generate the showcase explanation with make explain.")
            batch = batch_evidence(json.loads(row["EVIDENCE"]))
            if batch.get("PAYMENT_COUNT") != 37 or batch.get("MATCHED_RECEIPTS") != 36:
                raise RuntimeError(
                    "The showcase batch does not contain 37 payments and 36 receipts."
                )
            report["month_run_id"] = live["RUN_ID"]
            report["month_seconds"] = live["ELAPSED_SECONDS"]
            passed("10M dataset, recent completed month run and 37-payment showcase")
        with scope("day"):
            daily = snapshot()
            if not daily or daily["STATUS"] != "COMPLETE":
                raise RuntimeError(
                    "Prepare today's close with make recon-day DATE=2026-10-14, then make explain in daily scope."
                )
            report["day_run_id"] = daily["RUN_ID"]
            passed("Completed daily close retained alongside monthly results")
    except Exception as error:
        # Database exceptions can contain connection settings; do not print them.
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else "Database checks failed; verify Exasol is running and the retained schemas are available."
        )
        report["errors"].append(message)
        return report
    try:
        with urlopen(url.rstrip("/") + "/_stcore/health", timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Dashboard health check failed.")
        passed("Dashboard HTTP health")
    except (URLError, TimeoutError, RuntimeError):
        report["errors"].append("Start make app on port 8501 before checking readiness.")
        return report
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto(url.rstrip("/") + "/?present=1")
            page.get_by_role("heading", name="Full month close", exact=True).wait_for(timeout=60000)
            for name, title in (
                ("Exceptions queue", "Exceptions queue"),
                ("Exception detail", "Exception detail"),
                ("Accuracy & performance", "Accuracy & performance"),
                ("How it works", "How Milaan works"),
                ("Close overview", "Full month close"),
            ):
                page.get_by_test_id("stSidebar").get_by_role("button", name=name).click()
                page.get_by_role("heading", name=title, exact=True).wait_for(timeout=60000)
                page.wait_for_function(
                    "() => !document.querySelector('[data-stale=\"true\"]')", timeout=60000
                )
                if page.get_by_text("Let’s reconnect your workspace", exact=False).count():
                    raise RuntimeError("A dashboard page could not query its evidence.")
            browser.close()
        passed("Every dashboard page responds; read caches warmed")
    except Exception:
        report["errors"].append(
            "Browser warm-up failed. Check dashboard output and install the dev browser: .venv/bin/python -m playwright install --with-deps chromium"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()
    report = check(args.url)
    folder = ROOT / "private/prep"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "demo-ready.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["errors"]:
        for error in report["errors"]:
            print("NOT READY: " + error, file=sys.stderr)
        raise SystemExit(1)
    print("\033[32mREADY\033[0m — database, data, evidence and dashboard verified.")


if __name__ == "__main__":
    main()
