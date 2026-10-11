"""Export measured editor metadata, vectors and source excerpts beside the repo."""

import argparse
import html
import json
import os
import shutil
import struct
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from milaan.analytics import batch_evidence, detail, showcase_id, summary
from milaan.config import ROOT
from milaan.db import connect, query, scope
from milaan.explain import rupees
from milaan.live import snapshot


def read(path):
    return json.loads(path.read_text())


def run_metadata(scope_name):
    with scope(scope_name):
        data = summary()
        live = snapshot()
        score = query("SELECT * FROM MILAAN_RES.SCORE WHERE break_type='OVERALL'")[0]
        return {
            "run_id": live["RUN_ID"],
            "seconds": live["ELAPSED_SECONDS"],
            "source_rows": live["SOURCE_ROWS"],
            "score": score,
            "pass_timings": live["PASSES"],
            "matched_members": live["MEMBERS"],
            "matched_pct": 100 * live["MEMBERS"] / live["SOURCE_ROWS"],
            "unreconciled_before_paise": live["BEFORE_PAISE"],
            "unreconciled_after_paise": live["OPEN_PAISE"],
            "exceptions": data["EXCEPTIONS"],
            "daily": data["DAILY"],
        }


def vector(folder, batch, brand):
    ink = brand["colours"]["ink"]
    green = brand["colours"]["primary"]
    base = f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" viewBox="0 0 1440 900"><rect width="1440" height="900" fill="{brand["colours"]["background"]}"/><g font-family="Inter, sans-serif" fill="{ink}">'

    def text(x, y, value, size=26, colour=ink):
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{colour}">{html.escape(str(value))}</text>'

    def box(x, y, w, h, title, subtitle):
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="white" stroke="#e2e8e2"/>'
            + text(x + 25, y + 45, title, 28)
            + text(x + 25, y + 82, subtitle, 21)
        )

    s = base + text(65, 85, "Milaan: everything heavy runs inside Exasol", 40)
    sources = ["Loan receipts", "Bank statement", "Gateway settlement", "NACH returns"]
    for i, label in enumerate(sources):
        s += box(65 + 330 * i, 135, 305, 110, label, "Synthetic source file")
    s += text(535, 300, "↓  bulk IMPORT", 28, green)
    s += '<rect x="65" y="345" width="1290" height="270" rx="20" fill="#142d27"/>'
    s += text(100, 397, "EXASOL PERSONAL", 32, "#70d6af")
    for i, (label, sub) in enumerate(
        [
            ("Normalise", "REGEXP + calendar"),
            ("Match", "Joins + windows + UDFs"),
            ("Explain & score", "Evidence + answer sheet"),
        ]
    ):
        s += text(100 + 410 * i, 475, label, 32, "white") + text(
            100 + 410 * i, 525, sub, 23, "#b8d4c9"
        )
    s += text(500, 675, "↓  small result sets only", 28, green)
    s += box(65, 710, 610, 110, "Analyst dashboard", "Prioritise → inspect evidence → review")
    s += box(
        745, 710, 610, 110, "Decision audit in Exasol", "Run, analyst, timestamp, note and owner"
    )
    s += text(65, 867, "Ground truth enters scoring only. No external inference service.", 20)
    (folder / "architecture.svg").write_text(s + "</g></svg>")
    s = base + text(65, 85, "One bank credit = 37 gateway payments", 42)
    s += text(65, 118, f"Batch {batch['BATCH_ID']} · Bank reference {batch['SETTLEMENT_UTR']}", 22)
    for i, payment in enumerate(batch["PAYMENTS"]):
        x = 65 + (i % 8) * 158
        y = 150 + (i // 8) * 100
        missing = payment["RECEIPT_STATUS"] != "Matched"
        colour = "#fff1de" if missing else "#e2f5ed"
        s += f'<rect x="{x}" y="{y}" width="145" height="80" rx="12" fill="{colour}" stroke="{green}"/>'
        s += text(x + 12, y + 28, payment["PG_PAYMENT_ID"], 12) + text(
            x + 12, y + 59, rupees(payment["GROSS_PAISE"]), 18
        )
    s += text(
        65,
        700,
        f"Gross {rupees(batch['GROSS_PAISE'])} − fees {rupees(batch['FEE_PAISE'])} − GST {rupees(batch['GST_PAISE'])}",
        30,
    )
    s += text(65, 765, f"= bank credit {rupees(batch['BANK_CREDIT_PAISE'])}", 44, green)
    s += text(
        65,
        832,
        f"36 receipts present · one missing {rupees(next(p['GROSS_PAISE'] for p in batch['PAYMENTS'] if p['RECEIPT_STATUS'] != 'Matched'))} receipt on loan {next(p['LOAN_ID'] for p in batch['PAYMENTS'] if p['RECEIPT_STATUS'] != 'Matched')}",
        25,
    )
    (folder / "batch_37.svg").write_text(s + "</g></svg>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT.parent / "video_assets")
    parser.add_argument(
        "--unrecorded", action="store_true", help="Export fresh baselines before footage exists"
    )
    args = parser.parse_args()
    folder = args.out.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    bench = read(ROOT / "docs/benchmark_results.json")
    baseline = next(r for r in bench["results"] if r["source_rows"] == 10000000)
    month_shot = {} if args.unrecorded else read(folder / "S02_run_month_10M.events.json")
    day_shot = {} if args.unrecorded else read(folder / "S03_run_today.events.json")
    monthly = run_metadata("month")
    daily = run_metadata("day")
    if not args.unrecorded:
        assert monthly["run_id"] == month_shot["run_id"]
        assert daily["run_id"] == day_shot["run_id"]
    with scope("month"):
        manifest = json.loads(query("SELECT manifest FROM MILAAN_AUDIT.DATASET")[0]["MANIFEST"])
        totals = query(
            "SELECT (SELECT SUM(amount_paise) FROM MILAAN_CORE.LEDGER) ledger_paise,(SELECT SUM(credit_paise-debit_paise) FROM MILAAN_STG.BANK_STATEMENT) bank_paise,(SELECT SUM(gross_paise) FROM MILAAN_CORE.PG) gateway_gross_paise,(SELECT SUM(fee_paise) FROM MILAAN_CORE.PG) fee_paise,(SELECT SUM(gst_on_fee_paise) FROM MILAAN_CORE.PG) gst_paise"
        )[0]
        exception = detail(showcase_id())
        evidence = json.loads(exception["EVIDENCE"])
        batch = batch_evidence(evidence)
        categories = query(
            'SELECT category,COUNT(*) n,SUM(amount_paise) amount_paise FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
        )
        with connect() as connection:
            version = connection.login_info["releaseVersion"]
    assert all(
        int(totals[k.upper()]) == manifest["totals"][k]
        for k in manifest["totals"]
        if k.upper() in totals
    )
    attempts = (
        read(folder / "capture_attempts.json")
        if (folder / "capture_attempts.json").exists()
        else []
    )
    monthly["unrecorded_benchmark"] = {
        "run_id": baseline["run_id"],
        "seconds": baseline["seconds"],
        "pass_timings": [
            {k: r[k] for k in ("PASS_NAME", "SECONDS", "LINKS_ADDED")}
            for r in baseline["pass_details"]
        ],
    }
    daily_report = read(ROOT / "docs/daily_results.json")
    incremental = daily_report["results"][-1]
    daily_benchmark = daily_report.get("replay_baseline", incremental)
    daily["incremental_unrecorded_benchmark"] = {
        key: incremental[key]
        for key in (
            "run_id",
            "core_matching_seconds",
            "scoring_validation_seconds",
            "total_seconds",
        )
    }
    daily["recording_comparison_basis"] = "Same-day replay after demo reset, matching S03 workflow"
    monthly["unrecorded_benchmark"]["reset_before_run_seconds"] = baseline.get(
        "reset_before_run_seconds"
    )
    monthly["unrecorded_benchmark"]["starting_state"] = baseline.get("starting_state")
    daily["unrecorded_benchmark"] = {
        key: daily_benchmark[key]
        for key in (
            "run_id",
            "core_matching_seconds",
            "scoring_validation_seconds",
            "total_seconds",
        )
    }
    if args.unrecorded:
        monthly["recorded_s02_seconds"] = None
        monthly["recording_overhead_pct"] = None
        daily["recorded_s03"] = None
        daily["recording_overhead_pct"] = None
    else:
        monthly["recorded_s02_seconds"] = month_shot["run_snapshot"]["ELAPSED_SECONDS"]
        monthly["recording_overhead_pct"] = 100 * (
            monthly["recorded_s02_seconds"] / baseline["seconds"] - 1
        )
        monthly["recording_fps"] = month_shot["fps"]
        monthly["events_poll_interval_seconds"] = 1.0
        monthly["event_times_basis"] = (
            "Observed committed audit snapshots, relative to the measured sync marker; polling latency applies."
        )
        cumulative = 0
        for event in month_shot["events"]:
            if event["type"] == "pass_end":
                cumulative += event["links"]
                event["cumulative_links"] = cumulative
        monthly["recorded_pass_events"] = [
            e for e in month_shot["events"] if e["type"] == "pass_end"
        ]
        with scope("day"):
            timing = query(
                "SELECT * FROM MILAAN_AUDIT.DAILY_TIMING WHERE run_id={run!s}",
                {"run": daily["run_id"]},
            )[0]
        daily["recorded_s03"] = {
            "run_id": daily["run_id"],
            "core_matching_seconds": timing["CORE_SECONDS"],
            "scoring_validation_seconds": timing["SCORING_VALIDATION_SECONDS"],
            "total_seconds": timing["TOTAL_SECONDS"],
        }
        daily["recording_overhead_pct"] = 100 * (
            timing["TOTAL_SECONDS"] / daily_benchmark["total_seconds"] - 1
        )
    monthly["console_run"] = (
        read(folder / "console_run.json") if (folder / "console_run.json").exists() else None
    )
    validation = read(ROOT / "docs/validation_results.json")
    validation = [
        {
            "label": r["label"],
            "seed": r["seed"],
            "source_rows": r["source_rows"],
            "run_id": r["run_id"],
            "precision": r["score"]["PRECISION_VALUE"],
            "recall": r["score"]["RECALL_VALUE"],
            "false_links": r["score"]["FALSE_POSITIVE"],
            "missed_links": r["score"]["FALSE_NEGATIVE"],
            "exceptions": r["exception_count"],
        }
        for r in validation["results"]
    ]
    payments = [
        {
            "masked_payment_id": "…" + p["PG_PAYMENT_ID"][-4:],
            "loan_id": p["LOAN_ID"],
            "gross_paise": p["GROSS_PAISE"],
            "date": p["PAYMENT_DATE"],
            "receipt_status": p["RECEIPT_STATUS"],
        }
        for p in batch["PAYMENTS"]
    ]
    showcase = {
        "exception_id": exception["EXCEPTION_ID"],
        "bank": {
            "date": batch["VALUE_DATE"],
            "credit_paise": batch["BANK_CREDIT_PAISE"],
            "reference": batch["BANK_REF"],
        },
        "batch_id": batch["BATCH_ID"],
        "payment_count": batch["PAYMENT_COUNT"],
        "gross_paise": batch["GROSS_PAISE"],
        "fee_paise": batch["FEE_PAISE"],
        "gst_paise": batch["GST_PAISE"],
        "net_paise": batch["NET_PAISE"],
        "matched_receipts": batch["MATCHED_RECEIPTS"],
        "payments": payments,
        "missing_receipt": {
            "loan_id": evidence["loan_id"],
            "amount_paise": evidence["amount_paise"],
            "date": evidence["date"],
            "channel": evidence["channel"],
        },
        "explanation": exception["EXPLANATION"],
        "suggested_action": exception["SUGGESTED_ACTION"],
    }
    memory = int(Path("/proc/meminfo").read_text().split("MemTotal:")[1].split()[0]) * 1024
    calendar = manifest.get("calendar", {})
    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset": {
            "source_records": manifest["source_rows"],
            "source_file_counts": {
                k: manifest["source_counts"][k]
                for k in ("ledger", "bank_statement", "pg_settlement", "nach_returns")
            },
            "payment_events": manifest["payment_events"],
            "generation_days": manifest["days"],
            "start_date": manifest["start_date"],
            "as_of_date": manifest["as_of_date"],
            "date_range_basis": "30 generation days from start_date; settlement and ageing dates extend to as_of_date",
            "calendar": calendar,
            "seed": manifest["seed"],
            "totals_paise": manifest["totals"],
        },
        "machine": {"logical_cpus": os.cpu_count(), "ram_bytes": memory, "exasol_version": version},
        "month": monthly,
        "day": daily,
        "accuracy": validation,
        "exception_categories": categories,
        "showcase": showcase,
        "capture_attempts": attempts,
        "exasol_features": [
            "Bulk IMPORT",
            "REGEXP normalisation",
            "Hash joins",
            "Batch GROUP BY",
            "Window functions",
            "Python scalar similarity and explanation UDFs",
            "Lua SET bounded subset UDF",
            "SQL ground-truth scoring",
            "Native profiling",
        ],
        "sql_and_udf_nonblank_lines": sum(
            sum(bool(line.strip()) for line in p.read_text().splitlines())
            for directory in ("sql", "udf")
            for p in (ROOT / directory).glob("*.sql")
        ),
        "tests": 45,
        "commits": int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=ROOT)),
        "repository_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    (folder / "metrics.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    for name in ("brand", "diagrams", "sql_snippets", "deck_slides"):
        (folder / name).mkdir(exist_ok=True)
    shutil.copytree(ROOT / "docs/brand", folder / "brand", dirs_exist_ok=True)
    shutil.copy2(ROOT / "app/style.css", folder / "brand/style.css")
    for p in (ROOT / "docs/deck/cards").glob("*.png"):
        shutil.copy2(p, folder / "deck_slides" / f"slide_{int(p.stem):02d}.png")
    excerpts = [
        ("exact.sql", "sql/30_pass_exact.sql", 0, 25),
        ("pg_batch.sql", "sql/31_pass_pg_batch.sql", 0, 24),
        ("split_set_call.sql", "sql/35_pass_split_merge.sql", 0, 25),
        ("classification.sql", "sql/36_classify.sql", 17, 39),
        ("similarity.sql", "sql/34_pass_fuzzy.sql", 0, 25),
        ("subset_udf.sql", "udf/02_subset.sql", 0, 24),
    ]
    for target, source, start, end in excerpts:
        lines = (ROOT / source).read_text().splitlines()[start:end]
        lines = [
            f"-- Excerpt from {source}; source lines {start + 1}–{min(end, start + len(lines))}.",
            "-- Stored source evidence; executed inside Exasol Personal.",
        ] + lines
        if target == "exact.sql":
            lines.insert(2, "-- Unique references prevent ambiguous automatic links.")
        if target == "pg_batch.sql":
            del lines[1]
        assert 15 <= len(lines) <= 26
        (folder / "sql_snippets" / target).write_text("\n".join(lines[:25]) + "\n")
    vector(folder / "diagrams", batch, read(ROOT / "docs/brand/brand.json"))
    manifest_path = folder / "VIDEO_ASSETS.md"
    if manifest_path.exists():
        intro = manifest_path.read_text().split("## File inventory")[0].rstrip()
        rows = [
            intro,
            "",
            "## File inventory",
            "",
            "| File | Purpose / dimensions | Bytes |",
            "|---|---|---:|",
        ]
        purposes = {
            "footage": "Silent real-time shot; details above",
            "stills": "Dashboard state or named crop",
            "brand": "Brand asset / local Inter font and licence",
            "diagrams": "Editable measured diagram",
            "deck_slides": "Branded deck slide",
            "sql_snippets": "Database source excerpt",
        }
        for path in sorted(folder.rglob("*")):
            name = path.relative_to(folder)
            if (
                not path.is_file()
                or name.parts[0] in {"raw", "review", "retakes"}
                or path == manifest_path
            ):
                continue
            purpose = purposes.get(name.parts[0], "Measured metadata, audit or capture evidence")
            if path.suffix == ".png":
                width, height = struct.unpack(">II", path.read_bytes()[16:24])
                purpose += f"; {width}×{height}"
            rows.append(f"| `{name.as_posix()}` | {purpose} | {path.stat().st_size:,} |")
        manifest_path.write_text("\n".join(rows) + "\n")
    print("Exported measured editor metadata, vectors, brand, slide PNGs and SQL excerpts.")


if __name__ == "__main__":
    main()
