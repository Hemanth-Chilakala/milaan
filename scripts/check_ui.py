"""Browser review of every page at desktop, laptop, tablet and phone widths."""

import json

from playwright.sync_api import sync_playwright

from milaan.config import ROOT
from milaan.db import query

PAGES = [
    ("Today's close", "home", "Daily close"),
    ("Exceptions queue", "queue", "Exceptions queue"),
    ("Exception detail", "detail", "Exception detail"),
    ("Accuracy & performance", "accuracy", "Accuracy & performance"),
    ("How it works", "architecture", "How Milaan works"),
]


def settle(page):
    page.wait_for_timeout(250)
    page.wait_for_function("() => !document.querySelector('[data-stale=\"true\"]')", timeout=60000)
    page.get_by_test_id("stMain").evaluate("(e) => e.scrollTo(0, 0)")
    page.wait_for_timeout(400)


def main():
    folder = ROOT / "private/ui-review"
    folder.mkdir(parents=True, exist_ok=True)
    identifier = query(
        "SELECT exception_id FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' ORDER BY exception_id LIMIT 1"
    )[0]["EXCEPTION_ID"]
    report = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        for name, filename, title in PAGES:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.goto("http://127.0.0.1:8501")
            page.get_by_role("heading", name="Daily close", exact=True).wait_for(timeout=60000)
            page.get_by_test_id("stSidebar").get_by_text(name, exact=True).click()
            page.get_by_role("heading", name=title, exact=True).wait_for(timeout=60000)
            if filename == "detail":
                page.get_by_role("textbox", name="Exception ID", exact=True).fill(identifier)
                page.get_by_role("textbox", name="Exception ID", exact=True).press("Enter")
                page.get_by_role(
                    "heading", name="Gateway receipt missing from ledger", exact=True
                ).wait_for()
            settle(page)
            for width, height in ((1440, 1000), (1280, 900), (768, 1024), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                if width <= 768:
                    collapse = page.locator('[data-testid="stSidebarCollapseButton"] button')
                    if page.get_by_test_id("stSidebar").get_attribute("aria-expanded") == "true":
                        collapse.click()
                page.wait_for_timeout(900)
                settle(page)
                if page.get_by_text("This view could not load.", exact=False).count():
                    raise RuntimeError(f"{filename}: view error")
                layout = page.evaluate("""() => {
                    const main=document.querySelector('[data-testid="stMain"]');
                    const bad=[...document.querySelectorAll('.metric-value,.field-value,.explanation,.chip,.section-title')].filter(e=>{
                        const r=e.getBoundingClientRect();
                        return r.width>0&&r.height>0&&(e.scrollWidth>e.clientWidth+2||r.right>innerWidth+2||r.left<0);
                    }).map(e=>({text:e.innerText,width:e.clientWidth,scroll:e.scrollWidth}));
                    const h=document.querySelector('h1').getBoundingClientRect();
                    return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,mainWidth:main.clientWidth,mainScroll:main.scrollWidth,headingY:h.y,clipped:bad};
                }""")
                record = {"page": filename, "width": width, **layout}
                report.append(record)
                page.screenshot(path=str(folder / f"{filename}-{width}.png"), full_page=True)
                print(json.dumps(record), flush=True)
            page.close()
        browser.close()
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    failures = [
        r
        for r in report
        if r["clipped"]
        or r["documentWidth"] > r["viewport"] + 2
        or r["mainScroll"] > r["mainWidth"] + 2
        or r["headingY"] < 56
    ]
    if failures:
        raise RuntimeError(
            f"{len(failures)} layouts need review; see private/ui-review/report.json"
        )


if __name__ == "__main__":
    main()
