"""Capture every dashboard view using the current Exasol results."""

from playwright.sync_api import sync_playwright

from milaan.config import ROOT
from milaan.db import query


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
        page.get_by_text("Close the books with confidence").wait_for(timeout=60000)
        for label, filename, title in [
            ("Today's close", "home", "Close the books with confidence"),
            ("Exceptions queue", "queue", "Focus on the breaks that matter"),
            ("Exception detail", "detail", "Understand the difference"),
            ("Accuracy & performance", "accuracy", "Accuracy you can inspect"),
            ("How it works", "architecture", "Four files. One accountable close."),
        ]:
            page.get_by_text(label, exact=True).click()
            page.get_by_text(title, exact=True).wait_for()
            if filename == "detail":
                page.get_by_role("textbox", name="Exception ID", exact=True).fill(showcase)
                page.get_by_role("textbox", name="Exception ID", exact=True).press("Enter")
                page.get_by_text("Missing In Ledger", exact=True).wait_for()
            page.wait_for_timeout(1500)
            if page.get_by_text("The database operation could not complete.", exact=False).count():
                raise RuntimeError(page.locator("body").inner_text())
            page.screenshot(path=str(folder / f"{filename}.png"), full_page=True)
            print(f"Captured {filename}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
