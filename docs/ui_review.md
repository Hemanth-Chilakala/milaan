# Interface review

The dashboard was redesigned around the analyst's daily close and exception review. The current source dataset contains 10,000,000 synthetic records. All figures are read from Exasol.

Changes include a consistent navigation rail, compact Indian currency totals with exact values available on hover, readable source cards, highlighted differences, direct queue-row navigation, filtered pagination and a validated decision form. Review status is read from the latest run-linked audit decision. Audit timestamps are converted from the database clock to IST.

Browser visual checks cover all five pages at 1440, 1280, 768 and 390 pixels. The checks reject horizontal page overflow, clipped metric/evidence values and headings beneath the fixed header. The rendered screenshots were inspected visually, including mobile navigation and long source references. The collapsed sidebar no longer reserves an empty column on narrow screens. Wide data tables scroll inside their own container on phones.

The working browser workflow was exercised: select a queue row, return to the queue without reopening the previous selection, filter by category, reject an assignment with no assignee, save an assignment and verify its Exasol audit row, then navigate with the mobile menu.

Repeat the layout checks and refresh screenshots with the dashboard running:

```bash
.venv/bin/python -m scripts.check_ui
.venv/bin/python -m scripts.capture_screenshots
```

Detailed review captures and layout measurements are kept in ignored `private/ui-review/`. Submission screenshots are in `docs/screenshots/`.
