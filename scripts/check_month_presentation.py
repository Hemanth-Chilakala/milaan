"""Verify reset, live progress and final results of the real full-month UI."""

import json
from time import monotonic

from playwright.sync_api import expect, sync_playwright

from milaan import live
from milaan.config import ROOT
from milaan.db import query
from scripts.check_presentation_flow import layout
from scripts.check_ui import settle


def main():
    folder = ROOT / "private/ui-review"
    report = {"browser_run": True, "recorded_video": False, "layouts": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://127.0.0.1:8501/?present=1")
        page.get_by_role("heading", name="Full month close", exact=True).wait_for(timeout=60000)
        page.get_by_text("Priority reviews", exact=True).wait_for()
        settle(page)
        previous_id = live.snapshot()["RUN_ID"]
        page.get_by_role("button", name="Reset demo").click()
        deadline = monotonic() + 90
        while monotonic() < deadline:
            ready = live.snapshot()
            if ready.get("STATUS") == "READY" and ready["RUN_ID"] != previous_id:
                break
            page.wait_for_timeout(350)
        else:
            raise RuntimeError("Monthly reset did not finish")
        settle(page)
        report["reset_ready_snapshot"] = ready
        page.screenshot(path=str(folder / "month-before.png"))
        button = page.get_by_role("button", name="Run reconciliation (full month)")
        button.click()
        page.locator("#live-timer").wait_for(timeout=60000)
        expect(button).to_be_disabled(timeout=5000)
        page.locator(".live-pass.running").first.wait_for(timeout=60000)
        expect(page.get_by_text("Receipt links by matching pass", exact=True)).to_be_hidden()
        report["prior_panels_cleared"] = True
        report["run_button_locked"] = True
        for width, height in ((1920, 1080), (1366, 768)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(400)
            state = layout(page)
            report["layouts"].append(state)
            assert state["mainScroll"] <= state["mainWidth"] + 2 and not state["clipped"]
            assert not page.get_by_text("Receipt links by matching pass", exact=True).is_visible()
            page.screenshot(path=str(folder / f"month-live-{width}.png"))
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.get_by_text(
            "Results and evidence-backed explanations are ready.", exact=True
        ).wait_for(timeout=180000)
        settle(page)
        expect(page.get_by_text("Receipt links by matching pass", exact=True)).to_be_visible()
        page.screenshot(path=str(folder / "month-after.png"))
        result = live.snapshot()
        assert result["STATUS"] == "COMPLETE" and len(result["PASSES"]) == 7
        assert result["SOURCE_ROWS"] == 10000000 and result["MEMBERS"] == 9850231
        score = query(
            "SELECT * FROM MILAAN_RES.SCORE WHERE run_id={run!s} AND break_type='OVERALL'",
            {"run": result["RUN_ID"]},
        )[0]
        assert score["FALSE_POSITIVE"] == 0 and score["FALSE_NEGATIVE"] == 1779
        report["month_snapshot"] = result
        report["score"] = score
        report["completed_run_verified"] = True
        browser.close()
    (ROOT / "docs/presentation_month_verified.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
