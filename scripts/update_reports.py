"""Publish current measured observations consistently across documentation and preparation."""

import json
import re
from datetime import datetime

from milaan.config import ROOT
from milaan.explain import rupees


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    bench = read("docs/benchmark_results.json")
    validation = read("docs/validation_results.json")
    daily = read("docs/daily_results.json")
    month = bench["results"][-1]
    measured_date = datetime.fromisoformat(bench["measured_at_utc"]).strftime(
        "%d %b %Y · %H:%M UTC"
    )
    day = daily["results"][-1]
    catchup = daily["results"][0]
    score = month["score"]
    reset_seconds = month.get("reset_before_run_seconds")
    replay = daily.get("replay_baseline")
    metrics = json.loads((ROOT.parent / "video_assets/metrics.json").read_text())
    showcase = metrics["showcase"]
    precision = score["PRECISION_VALUE"] * 100
    recall = score["RECALL_VALUE"] * 100
    rate = score["AUTO_MATCH_RATE"] * 100
    accuracy_table = [
        "| 1M dataset | Seed | Precision | Recall | False links | Missed links | Exceptions |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in validation["results"]:
        s = r["score"]
        accuracy_table.append(
            f"| {r['label']} | {r['seed']} | {s['PRECISION_VALUE'] * 100:.3f}% | {s['RECALL_VALUE'] * 100:.3f}% | {s['FALSE_POSITIVE']:,} | {s['FALSE_NEGATIVE']:,} | {r['exception_count']:,} |"
        )
    accuracy_text = "\n".join(accuracy_table)
    daily_text = (
        f"14 Oct 2026: **{day['core_matching_seconds']:.3f}s core matching**, "
        f"**{day['scoring_validation_seconds']:.3f}s scoring and validation**, "
        f"**{day['total_seconds']:.3f}s total**. The core includes preparation, active sets, all matching passes, result append and classification. "
        f"The 10-second core target {'was met' if day['core_matching_seconds'] <= 10 else 'was missed'}. "
        f"The separately labelled 13 Oct catch-up took {catchup['total_seconds']:.3f}s total."
    )
    summary = (
        f"**10,000,000 source records in {month['seconds']:.2f} seconds**, measured without a browser or recorder on **4 cores / 15.62 GiB RAM**. **{rate:.3f}%** of source records were grouped, with **{precision:.3f}% link precision**, **{recall:.3f}% recall**, **{score['FALSE_POSITIVE']:,} false links** and **{score['FALSE_NEGATIVE']:,} missed expected links**. Timings include preparation, results, conflict validation, commits and SQL scoring; explanations and native profiling flush follow the timer. Fresh recorded timings and overhead are pending the footage checkpoint.\n\n"
        + daily_text
        + " See [benchmarks](docs/benchmarks.md) for run IDs and measured stages."
    )
    if reset_seconds is not None:
        summary += f" The prepared-state month excludes the explicit {reset_seconds:.3f}s demo reset before the timer; the full rerun including open-item restoration took 207.039s. Both observations are preserved, and footage overhead will compare equivalent prepared starting states."
    p = ROOT / "README.md"
    text = p.read_text()
    text = re.sub(
        r"Milaan reconciles a month of 10 million source records inside Exasol Personal in a measured [0-9.]+ seconds\.",
        f"Milaan reconciles a month of 10 million source records inside Exasol Personal in a measured {month['seconds']:.2f} seconds.",
        text,
    )
    text = re.sub(
        r"<!-- MEASUREMENTS_START -->.*?<!-- MEASUREMENTS_END -->",
        "<!-- MEASUREMENTS_START -->\n" + summary + "\n<!-- MEASUREMENTS_END -->",
        text,
        flags=re.S,
    )
    a = text.index("## How we validated")
    b = text.index("## Architecture", a)
    text = (
        text[:a]
        + "## How we validated\n\nThe event oracle records the known links separately before source fields are corrupted. Matching never reads those labels. Normal and reused blind seed 20261025 are regression checks. The earlier hard seed 20261104 informed reversal handling, so it is labelled **hard (tuned)**. Seed 20261105 was unused before this measurement and is labelled **hard (blind)**. SQL/UDF hashes were frozen before all four current runs.\n\n"
        + accuracy_text
        + "\n\nBank debit/credit pairs with the same normalised reference and amount are excluded before matching. A late reversal reopens its previous daily match for review. Ambiguous reversal relationships are held for review rather than assigned an arbitrary pair. These controlled synthetic results do not establish production accuracy; an independently labelled NBFC partner dataset is needed. See [raw validation](docs/validation_results.json).\n\n"
        + text[b:]
    )
    text = re.sub(
        r"Normal and blind 1M validation measured.*?Ambiguous candidates stay unresolved;",
        "The four current accuracy measurements are listed above. Reversal checks now exclude cancelled credits and reopen affected daily groups. Ambiguous candidates stay unresolved;",
        text,
        flags=re.S,
    )
    p.write_text(text)
    lines = [
        "# Measured benchmarks",
        "",
        f"Measured UTC: {measured_date}. Host: {bench['logical_cpus']} cores, {bench['ram_bytes'] / 2**30:.2f} GiB RAM; {bench['database']}.",
        "",
        "All data is synthetic. No browser or recorder ran during these measurements. Source records combine ledger, bank, gateway and NACH files; ground truth is separate. Total month reconciliation includes preparation, matching, classification, result materialisation, SQL scoring, validation and commits. Explanations and profile flush follow the timer.",
        "",
        "| Source records | Import + normalise | Total reconciliation | Precision | Recall | Auto-matched records |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in bench["results"]:
        s = r["score"]
        loading = (
            f"{r['load_total_seconds']:.3f}s"
            if r.get("load_total_seconds") is not None
            else "Retained sources; not rerun"
        )
        lines.append(
            f"| {r['source_rows']:,} | {loading} | {r['seconds']:.3f}s | {s['PRECISION_VALUE'] * 100:.3f}% | {s['RECALL_VALUE'] * 100:.3f}% | {s['AUTO_MATCH_RATE'] * 100:.3f}% |"
        )
    lines += [
        "",
        "## Matching passes",
        "",
        "| Pass | 1M seconds | 10M seconds |",
        "|---|---:|---:|",
    ]
    for name in month["passes"]:
        lines.append(
            f"| {name} | {bench['results'][0]['passes'][name]:.3f} | {month['passes'][name]:.3f} |"
        )
    lines += [
        "",
        f"10M run: `{month['run_id']}`; 1M normal: `{bench['results'][0]['run_id']}`. Full native profiles, category scores, exceptions and stage times: [benchmark_results.json](benchmark_results.json).",
        "",
        "## Blind and hard validation",
        "",
        accuracy_text,
        "",
        "Hard (tuned) seed 20261104 had 3,220 false links before reversal handling. Hard (blind) seed 20261105 was first generated after the rules were frozen. Normal and seed 20261025 are reused regression sets. Complete hashes, manifests, timings and false-edge examples: [validation_results.json](validation_results.json). Matching does not read the oracle.",
        "",
        "## Daily close",
        "",
        daily_text,
        "",
        f"Daily run: `{day['run_id']}`. All seven link columns agree with the eligible monthly results (zero differences). The prior three-consecutive-day 10M replay also agreed; a full 30-day 10M replay is unmeasured. [Daily methodology](daily.md), [current raw daily measurements](daily_results.json), [prior three-day proof](daily_incremental_results.json).",
        "",
        "## Previous observations and recording",
        "",
        "The previous identifier scheme measured 76.144s unrecorded and 114.107s recorded (49.86% overhead). These are historical observations on different identifiers. The previous daily path measured 47.778s core, 5.669s scoring/validation and 53.447s total. After incremental preparation it measured 28.625s core, 9.759s scoring/validation and 38.390s total. Fresh capture timings and overhead remain pending; current footage has not been re-recorded.",
        "",
        "These are individual observations, with potentially warm caches and indexes. No fixed-latency or cold-cache claim is made. Precision/recall count links; auto-match rate counts source memberships and has a different denominator. Synthetic generator and matcher share assumptions. [Performance details](performance.md).",
    ]
    if reset_seconds is not None:
        lines += [
            "",
            "## Comparable starting states",
            "",
            f"The month benchmark starts after an explicit demo reset, like S02. Reset cost: {reset_seconds:.3f}s, outside the click-to-results timer. The full unprepared rerun measured 207.039s including 68.221s to restore open tables; [raw observation](unprepared_repeat.json). Both source files and normalization were already loaded. We do not attribute warm-state differences solely to capture configuration.",
        ]
    if replay:
        lines += [
            "",
            f"S03 comparison uses the same-day reset/replay baseline: {replay['core_matching_seconds']:.3f}s core, {replay['scoring_validation_seconds']:.3f}s scoring/validation, {replay['total_seconds']:.3f}s total, with {replay['reset_before_run_seconds']:.3f}s reset outside the timer. This is separate from the first incremental 14 Oct close above. Native audit run: `{replay['run_id']}`.",
        ]
    (ROOT / "docs/benchmarks.md").write_text("\n".join(lines) + "\n")
    timings = "\n".join(
        f"| {name} | {seconds:.3f}s |" for name, seconds in month["stage_times"].items()
    )
    (ROOT / "docs/performance.md").write_text(
        f"# Performance measurements\n\nCurrent unrecorded 10M month: **{month['seconds']:.3f}s**, run `{month['run_id']}`. The 60-second target {'was met' if month['seconds'] <= 60 else 'was missed'}. All measured stages and profiles are preserved in [benchmark_results.json](benchmark_results.json).\n\n{daily_text}\n\n| Other monthly stage | Seconds |\n|---|---:|\n{timings}\n\nDaily work keeps persistent open items, filters new arrivals, appends results and retains closed groups. Core timing includes preparation and classification. Oracle maintenance and full-history conflict validation are separately timed. Bank reversals add an evidence check before passes; a later debit reopens the affected daily group.\n\nCapture configuration uses core 3 for Xvfb, Chromium and ffmpeg, one browser tab, one-second dashboard polling, disabled GPU/smooth scrolling and 1080p24 live shots. Actual recorded overhead has not yet been measured. The below-20% target cannot be assessed until the footage run. Historical recorded overhead was 49.86%.\n\nThere are no production latency guarantees. CPU contention, automatic indexes, reference collision/skew, group size and cache state affect runtime. Full 30-day 10M replay, 100M records and concurrent workloads are unmeasured.\n"
    )
    with (ROOT / "docs/performance.md").open("a") as output:
        output.write(
            f"\nThe prepared month reset took {reset_seconds:.3f}s outside the Run button timer. The full unprepared rerun took 207.039s; its open-item restoration cost 68.221s. Both observations are retained. A recording comparison must start from the same prepared state.\n"
        )
    p = ROOT / "docs/daily.md"
    text = f"""# Daily close

{daily_text}

| 14 Oct 2026 observation | Core matching | Scoring / validation | Total |
|---|---:|---:|---:|
| Original cumulative implementation | 47.778s | 5.669s | 53.447s |
| Previous incremental measurement | 28.625s | 9.759s | 38.390s |
| Current first-arrival close | {day["core_matching_seconds"]:.3f}s | {day["scoring_validation_seconds"]:.3f}s | {day["total_seconds"]:.3f}s |

The current close processes {sum(day["daily"]["new_source_counts"].values()):,} new source records plus carried open items; {day["daily"]["cumulative_source_rows"]:,} source records have arrived. Core includes source preparation, reversal checks, active sets, all seven passes, result appends, classification, progress and commits. Oracle maintenance, SQL scoring and full-history conflict validation are separately timed. Namespace setup and profiling export are outside the stored total.

Daily results retain closed history and persistent open items. Only newly arriving rows enter the next close. Gateway reviews carry forward without re-aggregating closed batches. A later equal-reference/amount debit reopens the affected group; both cancelled bank lines are excluded. Ambiguous reversal pairs remain under review.

## Current correctness and starting state

All seven link columns for the first 14 Oct close matched eligible monthly links with zero differences. First-arrival run: `{day["run_id"]}`. Its source preparation took {day["daily"]["preparation_seconds"]:.3f}s. Native timings and profiles: [daily_results.json](daily_results.json).

The first 13 Oct catch-up took {catchup["core_matching_seconds"]:.3f}s core, {catchup["scoring_validation_seconds"]:.3f}s scoring/validation and {catchup["total_seconds"]:.3f}s total; it is not a new-arrivals close.

## Prior three-consecutive-day proof

| Close | Core | Scoring / validation | Total | Differences |
|---|---:|---:|---:|---:|
| 14 Oct 2026 | 28.625s | 9.759s | 38.390s | 0 |
| 15 Oct 2026 | 29.397s | 10.938s | 40.341s | 0 |
| 16 Oct 2026 | 28.755s | 10.752s | 39.513s | 0 |

These are preserved prior observations, before reversal handling. All edge keys and all seven link columns agreed with the eligible monthly results. [Raw proof](daily_incremental_results.json). The 22-business-day fixture also reproduced all 437 month links. The dedicated late-reversal test verifies reopening. Full 30-day 10M replay remains unmeasured.

## Limitations and reproduction

The 10-second core target remains missed. Index maintenance, result/membership materialisation and classification remain material costs; full-history scoring/validation is separately timed. Same-day replay and catch-up have different starting states from new-arrival processing. The prepared month benchmark and unprepared full rerun are separate observations; capture overhead must compare equivalent starting states.

Use `make recon-day DATE=2026-10-14` to close a date. Going back requires `--restart` through the daily Python module. `python -m scripts.refresh_measurements` refreshes the unrecorded month and first daily arrival measurements. `--prepared-repeat` separately measures the reset states used by S02 and S03. All measurements use synthetic data on this 4-core Codespace; there is no fixed-latency or cold-cache claim.

A prior native-volume enlargement failed while retaining filesystem reserve. Only obsolete derived comparison/close tables were released; source backup, installed database/runtime and audit decisions were preserved. Normalisation commits each replacement promptly. Workspace reserve remains at least 6 GB.
"""
    if replay:
        text += f"\n## S03 replay comparison baseline\n\nSame-day replay: {replay['core_matching_seconds']:.3f}s core, {replay['scoring_validation_seconds']:.3f}s scoring/validation and {replay['total_seconds']:.3f}s total; explicit reset cost {replay['reset_before_run_seconds']:.3f}s before the timer. Run `{replay['run_id']}`. This is separate from the first-arrival close above. Fresh footage and actual overhead remain pending.\n"
    p.write_text(text)
    prep = ROOT / "private/prep"
    prep.mkdir(parents=True, exist_ok=True)
    payment = showcase["missing_receipt"]
    showcase_text = f"# Showcase and measured results\n\nMonth: {month['seconds']:.3f}s; run `{month['run_id']}`; {precision:.3f}% precision, {recall:.3f}% recall, {rate:.3f}% source membership.\n\n{daily_text}\n\n{accuracy_text}\n\n## Exact 37-payment equation\n\nBatch `{showcase['batch_id']}`: gross {rupees(showcase['gross_paise'])} − fees {rupees(showcase['fee_paise'])} − GST {rupees(showcase['gst_paise'])} = bank credit {rupees(showcase['net_paise'])}. {showcase['matched_receipts']} of {showcase['payment_count']} receipts matched. Missing receipt: loan `{payment['loan_id']}`, {rupees(payment['amount_paise'])}.\n\n{showcase['explanation']}\n\nFresh footage and overhead are pending. Use current live timing rather than promising the benchmark runtime. Prior 10M replay agreed on three consecutive closes; full 30-day replay remains unmeasured. All datasets are synthetic; partner validation is required.\n"
    (prep / "SHOWCASE_AND_METRICS.md").write_text(showcase_text)
    p = prep / "QA_PREP.md"
    text = p.read_text().split("\n## Current measured evidence")[0].rstrip()
    replacements = {
        43: "Current limitations: controlled synthetic inputs, bounded two/three-way splits, fictional calendar, one worker, no ledger connector or reviewer authentication. Full 30-day 10M replay is unmeasured. Current measured accuracy and timings are in SHOWCASE_AND_METRICS.md.",
        45: "The oracle is written separately before source corruption; matching never reads it. The normal and reused blind sets are regression checks. Hard seed 20261104 informed reversal handling and is labelled tuned. New seed 20261105 was unseen before the frozen-rule run. Results are in SHOWCASE_AND_METRICS.md. Independent labelled partner validation is still required.",
        46: f"The current unrecorded month took {month['seconds']:.3f}s. Joins, batch aggregation, evidence, result materialisation, scoring and validation all run inside Exasol. Fresh recorded overhead is pending. Runtime varies with CPU contention, cache/index state and source distributions; we do not promise fixed latency.",
        49: "The fixture replay agrees with all 437 month links. Three consecutive closes at 10M scale matched eligible monthly links in every column. The latest 14 Oct close also agrees. A later reversal reopens its previous group; the dedicated database test verifies this. Full 30-day 10M replay remains unmeasured.",
        51: "Equal-reference/amount debit and earlier-credit pairs are excluded before matching and raised as BANK_REVERSAL. A late debit reopens a previous daily match. Ambiguous pairs remain under review. Longer delays, four/five-way splits and ambiguous references still reduce hard-mode recall. Tuned and newly blind hard results are reported separately.",
    }
    for number, answer in replacements.items():
        text = re.sub(rf"(?m)^{number}\. (.*)$", f"{number}. {answer}", text)
    text += "\n## Current measured evidence\n\n" + showcase_text.removeprefix(
        "# Showcase and measured results\n\n"
    )
    p.write_text(text)
    (prep / "DEMO_DAY_SCRIPT.md").write_text(
        f"# Demo-day script\n\nOpen Close overview with today's scope selected. Explain the analyst, four source formats, carried open items and the current daily close.\n\nClick Run today's close. Narrate the actual timer; never promise a fixed runtime. State the separately measured benchmark: {daily_text}\n\nSwitch to Full month close to demonstrate 10M scale. The unrecorded benchmark was {month['seconds']:.3f}s, including database results, scoring and validation. Any live or recorded runtime is its own observation.\n\nOpen the exception queue and the showcase. State the exact equation from SHOWCASE_AND_METRICS.md. Hold on the explanation; expand all 37 gateway payments and scroll slowly. Verify the missing receipt, then record an Accept/Reject/Assign review with a note. It records a decision; real posting still requires accounting approval.\n\nOpen Accuracy & performance. Distinguish source membership from link precision/recall. Show all four 1M sets. Explain that hard (tuned) informed reversal handling, while hard (blind) used newly unseen seed 20261105 with frozen rules. State the measured recall limits and the need for independent partner labels.\n\nShow architecture: bulk import, normalisation, matching, explanation, scoring and audit all run inside Exasol. Python queries aggregates and paginated results. No external API key is required.\n\nFinish with The Singleton, Hemanth Chilakala, and https://github.com/Hemanth-Chilakala/milaan.\n"
    )
    print(
        "Updated README, benchmark/daily/performance reports and private preparation from current runs."
    )


if __name__ == "__main__":
    main()
