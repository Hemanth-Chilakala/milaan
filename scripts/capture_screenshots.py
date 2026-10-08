"""Capture every dashboard view using the current Exasol results."""

from playwright.sync_api import sync_playwright

from milaan.config import ROOT
from milaan.db import query
from scripts.check_ui import settle


def main():
    showcase = query(
        "SELECT exception_id FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' ORDER BY exception_id LIMIT 1"
    )[0]["EXCEPTION_ID"]
    folder = ROOT / "docs/screenshots"
    folder.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto("http://127.0.0.1:8501")
        page.get_by_role("heading", name="Daily close", exact=True).wait_for(timeout=60000)
        for label, filename, title in [
            ("Today's close", "home", "Daily close"),
            ("Exceptions queue", "queue", "Exceptions queue"),
            ("Exception detail", "detail", "Exception detail"),
            ("Accuracy & performance", "accuracy", "Accuracy & performance"),
            ("How it works", "architecture", "How Milaan works"),
        ]:
            page.get_by_test_id("stSidebar").get_by_text(label, exact=True).click()
            page.get_by_role("heading", name=title, exact=True).wait_for()
            if filename == "detail":
                page.get_by_role("textbox", name="Exception ID", exact=True).fill(showcase)
                page.get_by_role("textbox", name="Exception ID", exact=True).press("Enter")
                page.get_by_role(
                    "heading", name="Gateway receipt missing from ledger", exact=True
                ).wait_for()
            settle(page)
            if page.get_by_text("This view could not load.", exact=False).count():
                raise RuntimeError(page.locator("body").inner_text())
            page.screenshot(path=str(folder / f"{filename}.png"), full_page=True)
            print(f"Captured {filename}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
