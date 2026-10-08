"""Build presentation source and narration from measured benchmark evidence."""

import json
import re

from milaan.config import ROOT
from milaan.db import query
from milaan.explain import rupees


def main():
    evidence = json.loads((ROOT / "docs/benchmark_results.json").read_text())
    measured = evidence["results"][-1]
    if measured["source_rows"] != 10000000:
        raise RuntimeError("The 10M benchmark must finish before presentation preparation")
    recording = ROOT / "docs/video/recording.json"
    live = json.loads(recording.read_text()) if recording.exists() else measured
    score = live["score"]
    seconds = live["seconds"]
    exception = query(
        "SELECT evidence FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' ORDER BY exception_id LIMIT 1"
    )[0]
    batch = json.loads(exception["EVIDENCE"])
    auto = score["AUTO_MATCH_RATE"] * 100
    rowcount = live.get("exception_count", sum(r["N"] for r in measured["exceptions"]))
    (ROOT / "docs/deck").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/video").mkdir(parents=True, exist_ok=True)
    problem = (ROOT / "PROBLEM_STATEMENT.md").read_text().strip()
    # The standalone problem file includes a heading.
    problem = "\n".join(line for line in problem.splitlines() if not line.startswith("#")).strip()
    pass_rows = "\n".join(
        f"| {r['PASS_NAME']} | {r['LINKS_ADDED']:,} | {r['SECONDS']:.2f}s |"
        for r in live.get("pass_details", measured["pass_details"])
    )
    slides = [
        "# Milaan\n## Closing the books before noon\n\nThe Singleton · Hemanth Chilakala\n\nExaThon India 2026 · Track 1: Money, Risk & Regulation\n\n**An accountable close, powered by Exasol Personal.**",
        f"# Meet the reconciliation analyst\n\n> {problem}\n\nThe person: a finance analyst at a mid-sized Indian NBFC.\nThe desired outcome: investigate meaningful exceptions instead of every receipt.",
        f"# One credit can represent 37 payments\n\n<div class='equation'><b>37 PayFast payments</b><span>gross {rupees(batch['gross_total_paise'])}</span><span>− fees {rupees(batch['fee_paise'])} − GST {rupees(batch['gst_paise'])}</span><strong>One bank credit: {rupees(batch['bank_paise'])}</strong></div>\n\nFour channels · different formats · T+1/T+2 timing · truncated references · NACH returns\n\nMeasured synthetic showcase; 36 receipts are present and one is missing.",
        "# The cost of an unresolved close\n\n**Money in suspense** delays explanation of the cash balance.\n\n**Misstated customer dues** can prompt a call to someone who already paid.\n\n**Unclear evidence** adds effort to accounting review and audit.\n\nIllustrative workflow consequences. No industry cost or productivity statistic is claimed.",
        "# Everything heavy runs inside Exasol\n\n<div class='flow'><b>Four source CSVs</b> → <b>Bulk IMPORT</b> → <b>SQL normalisation</b><br>↓<br><b>7 matching passes + UDFs</b> → <b>Ranked exceptions</b><br>↓<br><b>Streamlit analyst review</b> → <b>Exasol decision audit</b></div>\n\nGround truth enters only the SQL scoring path. Python orchestrates; the database reconciles.",
        f"# Seven passes, measured at 10M\n\n| Pass | Receipt links | Time |\n|---|---:|---:|\n{pass_rows}\n\nPasses use remaining keys only. One-to-many and many-to-one relationships share a single group ID.",
        f"# Why Exasol Personal\n\n<div class='big'>{seconds:.2f} seconds</div>\n\n**10,000,000 source records** across four files.\n\nSQL joins, aggregation and windows · bulk IMPORT · Python scalar and SET UDFs\n\nMeasured on {evidence['logical_cpus']} cores / {evidence['ram_bytes'] / 2**30:.2f} GiB RAM.\nTiming includes results, conflict validation and SQL scoring; explanations and profiling flush are separate. Live-recorded run when available; timings vary between runs.",
        "# Review the money that needs attention\n\n<div class='screens'><img src='../screenshots/queue.png'><img src='../screenshots/detail.png'></div>\n\nRank by amount × business-day age × risk. Inspect source evidence. Accept a recommendation, reject it or assign an owner.",
        f"# Accuracy against known answers\n\n<div class='metrics'><div><strong>{score['PRECISION_VALUE'] * 100:.3f}%</strong><br>precision</div><div><strong>{score['RECALL_VALUE'] * 100:.3f}%</strong><br>recall</div><div><strong>{auto:.3f}%</strong><br>source records grouped</div></div>\n\n{score['FALSE_POSITIVE']:,} false links · {score['FALSE_NEGATIVE']:,} missed expected links · {rowcount:,} exceptions\n\nConflict validation rejects records assigned to multiple groups. These seeded results do not establish real-world accuracy; corruption patterns and distinct loans are deliberately constrained.",
        "# Trust comes from evidence\n\n**Deterministic explanations:** amounts, dates and rules come from stored evidence.\n\n**Human review:** decisions are recorded, not silently posted to a real ledger.\n\n**Run-linked audit:** analyst, timestamp, assignment and note stay in Exasol.\n\nNo external inference API. PII masking is tested for a future optional rewrite; that integration is not shipped.",
        "# A practical path to operational impact\n\n**First:** validate with an NBFC partner using independently labelled, anonymised cases.\n\n**Next:** live SFTP/API feeds, real business calendars, review roles and approved ledger write-back.\n\n**Then:** measure larger datasets and distributed coordination.\n\nThe same pattern may help banks, insurers, fintechs and gateway-based merchants. Applicability is a hypothesis to test.",
        "# Close the books with confidence\n\n**Milaan · The Singleton · Hemanth Chilakala**\n\nRepository destination:\nhttps://github.com/Hemanth-Chilakala/milaan\n\nDemo: `docs/video/demo.mp4`\n\nMIT · synthetic data only · Exasol Personal\n\nThank you.",
    ]
    header = """---
marp: true
theme: default
paginate: true
size: 16:9
footer: 'Milaan · The Singleton · ExaThon India 2026'
style: |
  section { background: #f7fafb; color: #172b3a; font-family: 'DejaVu Sans', sans-serif; font-size: 27px; padding: 52px 64px; }
  h1 { color: #0f766e; font-size: 46px; letter-spacing: -1.2px; }
  h2 { color: #334155; font-size: 34px; }
  blockquote { border-left: 7px solid #14b8a6; padding: 12px 24px; color: #172b3a; font-size: 29px; }
  footer { color: #64748b; font-size: 14px; }
  table { font-size: 22px; }
  .big { font-size: 82px; color: #0f766e; font-weight: bold; }
  .equation { background: white; border: 2px solid #d7e7e5; border-radius: 18px; padding: 24px; display: flex; flex-direction: column; gap: 12px; }
  .equation strong { color: #0f766e; font-size: 38px; }
  .flow { text-align: center; line-height: 2.2; background: white; border-radius: 16px; padding: 22px; }
  .screens { display:flex; gap:18px; }
  .screens img { width:48%; height:300px; object-fit:contain; background:white; border:1px solid #d7e7e5; }
  .metrics { display:flex; gap:24px; padding:20px 0; }
  .metrics div { flex:1; background:white; padding:22px; border-radius:16px; }
  .metrics strong { font-size:46px; color:#0f766e; }
---

"""
    (ROOT / "docs/deck/milaan_deck.md").write_text(header + "\n\n---\n\n".join(slides) + "\n")
    segments = [
        (
            20,
            "Milaan means matching. Meet a reconciliation analyst at a mid-sized Indian non-banking finance company. Each morning, the ledger says which loan instalments were paid. The bank, gateway and auto-debit return files tell different parts of the story. The analyst has to explain the differences before closing the books.",
        ),
        (
            20,
            "A spreadsheet join is not enough. One bank credit can cover thirty-seven gateway payments, after fees and tax. References can be shortened, settlement can arrive later, and a returned auto-debit can still look paid in the ledger. Milaan brings these records into one evidence-based workflow.",
        ),
        (
            45,
            f"Here are ten million source records across four files. Reconciliation runs inside Exasol Personal. The timer shows the real elapsed time as each pass completes. Exact reference matching comes first, followed by gateway batches, fee-aware matching, business-day tolerance, name similarity and bounded split payments. The recorded run took {seconds:.2f} seconds, including result validation and SQL accuracy scoring. {auto:.2f} percent of source records belong to matched groups. Every record is checked for conflicting group membership. The dashboard retrieves small result sets rather than moving millions of records into Python.",
        ),
        (
            40,
            "The analyst now works from a queue ranked by rupee impact, business-day age and risk. Open this missing-ledger exception. The bank credit agrees with a batch of thirty-seven gateway payments, but only thirty-six ledger receipts are present. The explanation identifies the missing payment and loan, with the actual amount, fees and tax. These words are generated from stored evidence inside Exasol, without an outside service. The analyst can accept the recommendation, reject it, or assign an owner. The decision, analyst and timestamp are written back to the audit trail.",
        ),
        (
            20,
            f"The accuracy panel compares predicted links with separate synthetic ground truth. This run measured {score['PRECISION_VALUE'] * 100:.3f} percent precision and {score['RECALL_VALUE'] * 100:.3f} percent recall. These are seeded demonstration results, not a claim about real customer data. The panel also exposes pass timings and Exasol execution profiles.",
        ),
        (
            15,
            "Milaan keeps the heavy work in Exasol: bulk imports, SQL joins, window functions, matching scripts, explanations and scoring. Python manages the workflow. The next step is validation with an NBFC partner and independently labelled cases.",
        ),
        (
            5,
            "Milaan. The Singleton. Hemanth Chilakala. Synthetic data, an MIT licence, and an accountable daily close.",
        ),
    ]
    (ROOT / "docs/video/narration.json").write_text(
        json.dumps([{"seconds": d, "text": t} for d, t in segments], indent=2) + "\n"
    )
    (ROOT / "docs/video/script.md").write_text(
        "# Demo narration\n\n" + "\n\n".join(t for _, t in segments) + "\n"
    )
    labels = [
        "Problem and analyst",
        "Batch settlement diagram",
        "Live reconciliation",
        "Exception evidence and audited review",
        "Accuracy and execution profiles",
        "Architecture",
        "Team and repository",
    ]
    clock = 0
    storyboard = [
        "# Storyboard",
        "",
        "Target duration: 2:45. All footage comes from the working dashboard and all figures from measured runs. AI voice-over is generated locally; captions carry the same narration. If reconciliation exceeds the allocated segment, speed up that footage and visibly label the time compression.",
        "",
        "| Seconds | Visual |",
        "|---|---|",
    ]
    for (duration, _), label in zip(segments, labels, strict=True):
        storyboard.append(f"| {clock}–{clock + duration} | {label} |")
        clock += duration
    (ROOT / "docs/video/storyboard.md").write_text("\n".join(storyboard) + "\n")
    readme = ROOT / "README.md"
    text = readme.read_text()
    summary = f"10,000,000 source records reconciled in **{seconds:.2f}s** on **{evidence['logical_cpus']} cores / {evidence['ram_bytes'] / 2**30:.2f} GiB RAM**. **{auto:.3f}%** of source records were grouped; seeded link precision and recall were **{score['PRECISION_VALUE'] * 100:.3f}% / {score['RECALL_VALUE'] * 100:.3f}%**, with **{score['FALSE_POSITIVE']:,} false links**. The headline uses the live-recorded run when available. See [all measured benchmarks](docs/benchmarks.md) for separate import, pass and explanation timings."
    text = re.sub(
        r"<!-- MEASUREMENTS_START -->.*?<!-- MEASUREMENTS_END -->",
        "<!-- MEASUREMENTS_START -->\n" + summary + "\n<!-- MEASUREMENTS_END -->",
        text,
        flags=re.S,
    )
    readme.write_text(text)
    print(
        f"Prepared deck and {sum(len(t.split()) for _, t in segments)} narration words from measured evidence"
    )


if __name__ == "__main__":
    main()
