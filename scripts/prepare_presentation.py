"""Build the branded deck from measured evidence, without creating a video."""

import base64
import json

from milaan.config import ROOT
from milaan.db import query
from milaan.explain import rupees


def main():
    payload = json.loads((ROOT / "docs/benchmark_results.json").read_text())
    measured = next(r for r in payload["results"] if r["source_rows"] == 10000000)
    score = measured["score"]
    validation = json.loads((ROOT / "docs/validation_results.json").read_text())
    batch = json.loads(
        query(
            "SELECT evidence FROM MILAAN_RES.\"EXCEPTION\" WHERE category='MISSING_IN_LEDGER' ORDER BY exception_id LIMIT 1"
        )[0]["EVIDENCE"]
    )
    problem = "\n".join(
        line
        for line in (ROOT / "PROBLEM_STATEMENT.md").read_text().splitlines()
        if not line.startswith("#")
    ).strip()
    brand = json.loads((ROOT / "docs/brand/brand.json").read_text())
    font = base64.b64encode((ROOT / "docs/brand/fonts/InterVariable.woff2").read_bytes()).decode()
    colours = brand["colours"]
    logo = "<img class='logo' src='../brand/logo.svg'>"
    pass_rows = []
    cumulative = 0
    for row in measured["pass_details"]:
        cumulative += row["LINKS_ADDED"]
        width = max(2, 100 * row["LINKS_ADDED"] / 3164644)
        pass_rows.append(
            f"<div class='pass'><span>{row['PASS_NAME']}</span><i style='width:{width:.2f}%'></i><b>{row['LINKS_ADDED']:,}</b><small>{cumulative:,} cumulative</small></div>"
        )
    checks = "\n".join(
        f"| {r['label']} | {r['score']['PRECISION_VALUE'] * 100:.3f}% | {r['score']['RECALL_VALUE'] * 100:.3f}% | {r['score']['FALSE_POSITIVE']:,} |"
        for r in validation["results"]
    )
    timing = " · ".join(f"{r['PASS_NAME']}: {r['SECONDS']:.2f}s" for r in measured["pass_details"])
    slides = [
        f"{logo}\n\n# Closing the books<br>before noon\n\n<div class='lead'>Payment reconciliation for the analyst who has four files and one close to finish.</div>\n\nThe Singleton · Hemanth Chilakala\n\nExaThon India 2026 · Track 1",
        f"# Meet the analyst\n\n> {problem}",
        f"# One credit. 37 payments.\n\n<div class='equation'><b>37 PayFast payments</b><span>Gross {rupees(batch['gross_total_paise'])}</span><span>− fees {rupees(batch['fee_paise'])} − GST {rupees(batch['gst_paise'])}</span><strong>Bank credit {rupees(batch['bank_paise'])}</strong></div>\n\n**36 ledger receipts present · 1 missing**\n\nLoan {batch['loan_id']} · missing receipt {rupees(batch['amount_paise'])}",
        "# Why spreadsheets fail\n\n<div class='cards'><div><b>References disagree</b><p>Truncated bank narrations and different receipt identifiers.</p></div><div><b>Amounts disagree</b><p>Gross EMIs, net settlements, fees and GST.</p></div><div><b>Dates disagree</b><p>Delayed credits, holidays and next-day NACH returns.</p></div></div>\n\nIllustrative consequences: suspense balances, wrong customer follow-ups and slower audit review.",
        "# Milaan in one picture\n\n<div class='flow'><b>Ledger · Bank · Gateway · NACH</b><br>↓ bulk IMPORT<br><strong>EXASOL PERSONAL</strong><br>SQL normalisation → seven passes + UDFs → ranked exceptions<br>↓ small result sets<br><b>Analyst review → decision audit in Exasol</b></div>\n\nSeparate ground truth → SQL scoring",
        "# Watch the close progress\n\n<img class='hero' src='../screenshots/home.png'>\n\nFull month for scale · Today's close for arriving records and carried open items",
        "# Seven passes. One shrinking queue.\n\n"
        + "\n".join(pass_rows)
        + "\n\n<div class='caption'>Measured 10M run · counts are receipt links · CLASSIFY labels remaining exceptions</div>",
        f"# Why Exasol\n\n<div class='big'>{measured['seconds']:.2f}<span> seconds</span></div>\n\n**10,000,000 source records · 4 cores · 15.62 GiB RAM**\n\nBulk IMPORT · hash joins · REGEXP · windows · Python scalar · Lua SET UDFs\n\n<div class='caption'>{timing}</div>\n\nDatabase-side results, validation and scoring included. Explanations and profiling flush follow the timer.",
        "# Review the money that matters\n\n<div class='screens'><img src='../screenshots/queue.png'><img src='../screenshots/detail.png'></div>\n\n**Prioritise → inspect evidence → accept, reject or assign**\n\nEvery review records the analyst, timestamp and reasoning in Exasol.",
        f"# Accuracy, tested three ways\n\n| 1M dataset | Precision | Recall | False links |\n|---|---:|---:|---:|\n{checks}\n\n**10M normal:** {score['PRECISION_VALUE'] * 100:.3f}% precision · {score['RECALL_VALUE'] * 100:.3f}% recall · {score['AUTO_MATCH_RATE'] * 100:.3f}% source membership\n\nBlind: unseen seed and break rates. Hard: collisions, reversals, longer delays and extra splits.",
        "# Trust comes from evidence\n\n<div class='cards'><div><b>Deterministic explanations</b><p>Amounts, dates and rules come from stored evidence. No external inference service.</p></div><div><b>Human review</b><p>The analyst accepts a recommendation, rejects it or assigns an owner.</p></div><div><b>Auditable decisions</b><p>Run-linked evidence and review history remain in Exasol.</p></div></div>\n\nA final membership check rejects conflicting match groups.",
        "# A practical path to impact\n\n**First:** independently labelled validation with an NBFC partner.\n\n**Next:** live feeds, real holiday calendars, authenticated review roles and approved ledger write-back.\n\n**Then:** measure larger datasets and concurrent operations.\n\nSimilar reconciliation workflows exist in banks, insurers, fintechs and gateway-based merchants.",
        f"{logo}\n\n# Close with confidence\n\nThe Singleton · Hemanth Chilakala\n\nhttps://github.com/Hemanth-Chilakala/milaan\n\nDemo video: docs/video/demo.mp4\n\nMIT · All data is synthetic",
        "# Appendix: limitations & methodology\n\n- Seeded, controlled data; production accuracy needs independent partner labels.\n- Frozen normal/blind/hard rules; bank reversals explain hard-mode false links.\n- Split search: at most 12 candidates, subsets of two or three.\n- Single node and one worker; no real ledger connector or review authentication.\n- Timing includes preparation, results, validation and scoring; browser/recording load changes it.\n- Daily/monthly equivalence tested on 1,000 records; full 10M daily replay remains unmeasured.\n- Codespace rebuild and clean checkout tested; macOS/WSL remain unverified.\n\nRun IDs, profiles and raw observations: docs/benchmarks.md",
    ]
    css = f"""/* @theme milaan */
@import 'default';
@font-face {{ font-family: Inter; src: url(data:font/woff2;base64,{font}) format('woff2'); font-weight: 100 900; }}
section {{ background:{colours["background"]}; color:{colours["ink"]}; font-family:Inter,sans-serif; font-size:26px; padding:58px 66px; }}
h1 {{ color:{colours["ink"]}; font-size:48px; font-weight:650; letter-spacing:-1.8px; margin:0 0 26px; }}
h2 {{ color:{colours["primary"]}; }}
strong,b {{ font-weight:650; }}
blockquote {{ border-left:6px solid {colours["primary"]}; padding:16px 26px; font-size:29px; line-height:1.5; color:{colours["ink"]}; }}
footer {{ color:{colours["muted"]}; font-size:13px; }}
section::after {{ color:{colours["muted"]}; font-size:14px; }}
.logo {{ width:220px; margin-bottom:28px; }}
.lead {{ font-size:28px; max-width:900px; margin:22px 0; color:{colours["muted"]}; }}
.big {{ font-size:108px; letter-spacing:-5px; color:{colours["primary"]}; font-weight:650; margin:8px 0 24px; }}
.big span {{ font-size:34px; letter-spacing:-1px; }}
.equation {{ border:1px solid {colours["line"]}; background:white; border-radius:18px; padding:28px; display:flex; flex-direction:column; gap:18px; }}
.equation strong {{ color:{colours["primary"]}; font-size:42px; }}
.cards {{ display:flex; gap:22px; margin:24px 0; }}
.cards div {{ flex:1; background:white; border:1px solid {colours["line"]}; border-radius:16px; padding:24px; }}
.cards p {{ font-size:22px; color:{colours["muted"]}; line-height:1.45; }}
.flow {{ text-align:center; background:white; border-radius:18px; line-height:1.7; padding:18px; }}
.flow strong {{ color:{colours["primary"]}; font-size:36px; }}
.hero {{ width:100%; height:408px; object-fit:contain; background:white; border-radius:12px; }}
.screens {{ display:flex; gap:20px; }}
.screens img {{ width:49%; height:340px; object-fit:contain; background:white; border:1px solid {colours["line"]}; border-radius:10px; }}
table {{ font-size:26px; width:100%; }}
th {{ background:{colours["primary"]}; color:white; }}
.caption {{ font-size:17px; color:{colours["muted"]}; line-height:1.5; }}
.pass {{ position:relative; display:flex; align-items:center; gap:16px; height:47px; margin:7px 0; background:white; border-radius:8px; overflow:hidden; padding:0 16px; font-size:21px; }}
.pass i {{ position:absolute; inset:0 auto 0 0; background:{colours["mint"]}; opacity:.25; }}
.pass span {{ width:200px; z-index:1; }}
.pass b {{ width:150px; z-index:1; }}
.pass small {{ color:{colours["muted"]}; z-index:1; margin-left:auto; }}
section:last-of-type {{ font-size:20px; }}
section:last-of-type li {{ margin:10px 0; }}
"""
    folder = ROOT / "docs/deck"
    (folder / "theme.css").write_text(css)
    header = "---\nmarp: true\ntheme: milaan\npaginate: true\nsize: 16:9\nfooter: 'Milaan · The Singleton · ExaThon India 2026'\n---\n\n"
    (folder / "milaan_deck.md").write_text(header + "\n\n---\n\n".join(slides) + "\n")
    (folder / "measurements.json").write_text(
        json.dumps(
            {
                "benchmark_run_id": measured["run_id"],
                "source_rows": measured["source_rows"],
                "seconds": measured["seconds"],
                "score": score,
                "passes": measured["pass_details"],
                "slide_count": len(slides),
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(f"Prepared {len(slides)} branded slides from run {measured['run_id']}")


if __name__ == "__main__":
    main()
