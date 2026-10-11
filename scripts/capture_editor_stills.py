"""Capture native 4K editor stills after the real-time recordings have finished."""

from playwright.sync_api import sync_playwright

from milaan.analytics import showcase_id
from milaan.config import ROOT
from milaan.demo import is_running
from scripts.record_demo import navigate, settle


def main():
    if is_running():
        raise RuntimeError("Wait for reconciliation before capturing native 4K stills.")
    folder = (ROOT.parent / "video_assets/stills").resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        page.goto("http://127.0.0.1:8501/?present=1")
        page.get_by_role("heading", name="Full month close", exact=True).wait_for(timeout=90000)
        settle(page)
        page.screenshot(path=str(folder / "S02_month_completed_native_4k.png"))
        page.locator(".metric-grid").screenshot(path=str(folder / "S04_kpi_tiles_native_4k.png"))
        page.get_by_test_id("stRadio").get_by_text("Today's close", exact=True).click()
        page.get_by_role("heading", name="Today's close", exact=True).wait_for(timeout=90000)
        settle(page)
        page.screenshot(path=str(folder / "S03_day_completed_native_4k.png"))
        page.get_by_test_id("stRadio").get_by_text("Full month (10M)", exact=True).click()
        settle(page)
        navigate(page, "Exceptions queue", "Exceptions queue")
        page.get_by_role("combobox", name="Category", exact=True).click()
        page.get_by_role("option", name="Gateway receipt missing from ledger", exact=True).click()
        settle(page)
        page.screenshot(path=str(folder / "S05_filtered_queue_native_4k.png"))
        navigate(page, "Exception detail", "Exception detail")
        entry = page.get_by_role("textbox", name="Exception ID", exact=True)
        entry.fill(showcase_id())
        entry.press("Enter")
        page.get_by_role(
            "heading", name="Gateway receipt missing from ledger", exact=True
        ).wait_for(timeout=90000)
        settle(page)
        page.screenshot(path=str(folder / "S06_sources_native_4k.png"))
        for name, selector in (
            ("source_comparison", ".batch-comparison"),
            ("equation", "#settlement-equation"),
            ("explanation", "#explanation-callout"),
            ("decision", ".st-key-panel_decision"),
        ):
            page.locator(selector).screenshot(path=str(folder / f"S06_{name}_native_4k.png"))
        page.get_by_text("Inspect all 37 gateway payments", exact=True).click()
        settle(page)
        page.get_by_test_id("stDataFrame").first.screenshot(
            path=str(folder / "S06_gateway_payments_native_4k.png")
        )
        navigate(page, "Accuracy & performance", "Accuracy & performance")
        page.screenshot(path=str(folder / "S08_accuracy_native_4k.png"), full_page=True)
        navigate(page, "How it works", "How Milaan works")
        page.screenshot(path=str(folder / "S09_architecture_native_4k.png"), full_page=True)
        browser.close()
    print("Native 4K editor page states and evidence crops captured.")


if __name__ == "__main__":
    main()
