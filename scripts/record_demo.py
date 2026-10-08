"""Record a real dashboard reconciliation and the analyst workflow."""

import json
from time import perf_counter

from playwright.sync_api import sync_playwright

from milaan.config import ROOT
from milaan.db import connect, query


def main():
    if query("SELECT source_rows FROM MILAAN_AUDIT.DATASET")[0]["SOURCE_ROWS"] != 10000000:
        raise RuntimeError("Preload the 10M dataset before recording")
    folder = ROOT / "private/recording"
    folder.mkdir(parents=True, exist_ok=True)
    # Reset derived results only; all source files and audit decisions are retained.
    with connect() as connection:
        for table in ("LINK", "MATCH", "MATCH_MEMBER", "EXCEPTION", "EXPLANATION", "SCORE"):
            connection.execute(f'TRUNCATE TABLE MILAAN_RES."{table}"')
        connection.commit()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(folder),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        zero = perf_counter()
        shots = {}
        page.goto("http://127.0.0.1:8501")
        page.get_by_role("heading", name="Daily close", exact=True).wait_for(timeout=60000)
        page.wait_for_timeout(2000)
        shots["reconciliation"] = {"start": perf_counter() - zero}
        page.get_by_text("Run reconciliation", exact=True).click()
        page.get_by_text(
            "Results and evidence-backed explanations are ready.", exact=False
        ).wait_for(timeout=600000)
        page.wait_for_timeout(3000)
        shots["reconciliation"]["end"] = perf_counter() - zero
        live = query(
            "SELECT * FROM MILAAN_AUDIT.RUN WHERE status='COMPLETE' ORDER BY started_at DESC LIMIT 1"
        )[0]
        score = query(
            "SELECT * FROM MILAAN_RES.SCORE WHERE run_id={id!s} AND break_type='OVERALL'",
            {"id": live["RUN_ID"]},
        )[0]
        (ROOT / "docs/video/recording.json").write_text(
            json.dumps(
                {
                    "run_id": live["RUN_ID"],
                    "seconds": live["SECONDS"],
                    "score": score,
                    "source_rows": 10000000,
                    "exception_count": query('SELECT COUNT(*) N FROM MILAAN_RES."EXCEPTION"')[0][
                        "N"
                    ],
                    "pass_details": query(
                        "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={id!s}",
                        {"id": live["RUN_ID"]},
                    ),
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        shots["review"] = {"start": perf_counter() - zero}
        page.get_by_text("Exceptions queue", exact=True).click()
        page.get_by_role("heading", name="Exceptions queue", exact=True).wait_for()
        page.wait_for_timeout(5000)
        showcase = query(
            "SELECT exception_id FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' ORDER BY exception_id LIMIT 1"
        )[0]["EXCEPTION_ID"]
        page.get_by_text("Exception detail", exact=True).click()
        page.get_by_role("textbox", name="Exception ID", exact=True).fill(showcase)
        page.get_by_role("textbox", name="Exception ID", exact=True).press("Enter")
        page.get_by_role(
            "heading", name="Gateway receipt missing from ledger", exact=True
        ).wait_for()
        page.wait_for_timeout(10000)
        page.get_by_text("Record a decision", exact=True).scroll_into_view_if_needed()
        page.get_by_role("textbox", name="Decision note", exact=True).fill(
            "Reviewed gateway evidence; missing receipt requires posting approval."
        )
        page.get_by_text("Accept recommendation", exact=True).click()
        page.get_by_text("Decision saved to the Exasol audit trail.", exact=True).wait_for()
        page.wait_for_timeout(5000)
        shots["review"]["end"] = perf_counter() - zero
        shots["accuracy"] = {"start": perf_counter() - zero}
        page.get_by_text("Accuracy & performance", exact=True).click()
        page.get_by_role("heading", name="Accuracy & performance", exact=True).wait_for()
        page.wait_for_timeout(7000)
        page.get_by_text("Exasol's execution profiling", exact=True).click()
        page.wait_for_timeout(5000)
        shots["accuracy"]["end"] = perf_counter() - zero
        shots["architecture"] = {"start": perf_counter() - zero}
        page.get_by_text("How it works", exact=True).click()
        page.get_by_role("heading", name="How Milaan works", exact=True).wait_for()
        page.wait_for_timeout(10000)
        shots["architecture"]["end"] = perf_counter() - zero
        video = page.video
        context.close()
        path = video.path()
        (folder / "shots.json").write_text(
            json.dumps({"video": str(path), "shots": shots}, indent=2) + "\n"
        )
        browser.close()
    print(f"Recorded live run {live['RUN_ID']}: {live['SECONDS']:.2f}s", flush=True)


if __name__ == "__main__":
    main()
