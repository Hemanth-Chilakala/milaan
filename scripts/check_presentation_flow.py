"""Exercise the real analyst review, reset and daily-run controls in the browser."""

import json
from time import monotonic

from playwright.sync_api import sync_playwright

from milaan import live
from milaan.analytics import showcase_id
from milaan.config import ROOT
from milaan.db import query, scope
from milaan.explain import rupees
from scripts.check_ui import settle


def layout(page):
    return page.evaluate("""() => {
        const main=document.querySelector('[data-testid="stMain"]');
        const clipped=[...document.querySelectorAll('.live-panel,.live-timer,.live-pass strong,.metric-value')].filter(e=>e.scrollWidth>e.clientWidth+2).map(e=>e.innerText);
        return {width:innerWidth,mainWidth:main.clientWidth,mainScroll:main.scrollWidth,clipped};
    }""")


def main():
    folder = (ROOT / "private/ui-review").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    identifier = showcase_id()
    monthly_run = query("SELECT run_id FROM MILAAN_AUDIT.RUN ORDER BY started_at DESC LIMIT 1")[0][
        "RUN_ID"
    ]
    report = {"monthly_run_id": monthly_run, "layouts": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://127.0.0.1:8501/?present=1")
        page.get_by_role("heading", name="Full month close", exact=True).wait_for(timeout=60000)
        page.get_by_role("button", name="Review the 37-payment batch").click()
        page.get_by_role("heading", name="Gateway receipt missing from ledger").wait_for()
        settle(page)
        evidence = json.loads(
            query(
                'SELECT evidence FROM MILAAN_RES."EXCEPTION" WHERE exception_id={id!s}',
                {"id": identifier},
            )[0]["EVIDENCE"]
        )
        assert (
            evidence["gross_total_paise"] - evidence["fee_paise"] - evidence["gst_paise"]
            == evidence["bank_paise"]
        )
        for value in (
            rupees(evidence[k])
            for k in ("gross_total_paise", "fee_paise", "gst_paise", "bank_paise")
        ):
            assert value in page.locator("#settlement-equation").inner_text()
        before = query(
            "SELECT COUNT(*) N FROM MILAAN_AUDIT.DECISION WHERE exception_id={id!s} AND run_id={run!s}",
            {"id": identifier, "run": monthly_run},
        )[0]["N"]
        page.get_by_role("textbox", name="Decision note").fill(
            "Reviewed the 37-payment batch against the bank credit; verify the missing ledger receipt."
        )
        page.get_by_role("button", name="Accept", exact=False).click()
        page.get_by_text("Decision saved to the Exasol audit trail.", exact=True).wait_for()
        after = query(
            "SELECT COUNT(*) N FROM MILAAN_AUDIT.DECISION WHERE exception_id={id!s} AND run_id={run!s}",
            {"id": identifier, "run": monthly_run},
        )[0]["N"]
        assert after == before + 1
        report["audit_write_verified"] = True
        page.screenshot(path=str(folder / "decision.png"))
        page.get_by_test_id("stSidebar").get_by_role("button", name="Close overview").click()
        page.get_by_test_id("stRadio").get_by_text("Today's close", exact=True).click()
        page.get_by_text("New records today", exact=True).wait_for()
        settle(page)
        page.get_by_role("button", name="Reset demo").click()
        with scope("day"):
            previous = live.snapshot()["RUN_ID"]
        deadline = monotonic() + 90
        while monotonic() < deadline:
            with scope("day"):
                ready = live.snapshot()
            if ready.get("STATUS") == "READY" and ready["RUN_ID"] != previous:
                break
            page.wait_for_timeout(300)
        else:
            raise RuntimeError("Daily reset did not complete")
        page.get_by_role("button", name="Run today's close").wait_for()
        settle(page)
        page.screenshot(path=str(folder / "daily-before.png"))
        page.get_by_role("button", name="Run today's close").click()
        page.locator("#live-timer").wait_for(timeout=60000)
        assert not page.get_by_role("button", name="Run today's close").is_enabled()
        report["run_button_locked"] = True
        page.locator(".live-pass.running").first.wait_for(timeout=90000)
        assert not page.get_by_text("Receipt links by matching pass", exact=True).is_visible()
        for width, height in ((1920, 1080), (1366, 768)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            state = layout(page)
            report["layouts"].append(state)
            assert state["mainScroll"] <= state["mainWidth"] + 2 and not state["clipped"]
            page.screenshot(path=str(folder / f"live-{width}.png"))
        page.set_viewport_size({"width": 1920, "height": 1080})
        deadline = monotonic() + 180
        while monotonic() < deadline:
            if page.get_by_text(
                "Results and evidence-backed explanations are ready.", exact=True
            ).count():
                break
            if page.get_by_text("Let’s reconnect your workspace", exact=True).count():
                raise RuntimeError("The live run view failed")
            page.wait_for_timeout(500)
        else:
            raise RuntimeError("Daily run did not finish in the browser")
        settle(page)
        page.screenshot(path=str(folder / "daily-after.png"))
        with scope("day"):
            result = live.snapshot()
            assert result["STATUS"] == "COMPLETE"
            assert len(result["PASSES"]) == 7
            assert (
                result["MEMBERS"] == query("SELECT COUNT(*) N FROM MILAAN_RES.MATCH_MEMBER")[0]["N"]
            )
            report["daily_snapshot"] = result
        report["completed_run_verified"] = True
        browser.close()
    (folder / "flow.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
