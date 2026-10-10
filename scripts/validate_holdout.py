"""Measure unseen and difficult synthetic inputs without changing matching rules."""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from generator.generate import generate
from milaan.config import ROOT
from milaan.db import query
from milaan.explain import generate_explanations
from milaan.pipeline import load, recon


def fingerprints():
    files = sorted((ROOT / "sql").glob("3*.sql")) + sorted((ROOT / "udf").glob("*.sql"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def comparison_rows(payload):
    return [
        {
            "Dataset": r["label"],
            "Records": r["source_rows"],
            "Precision": f"{r['score']['PRECISION_VALUE'] * 100:.3f}%",
            "Recall": f"{r['score']['RECALL_VALUE'] * 100:.3f}%",
            "False links": r["score"]["FALSE_POSITIVE"],
            "Missed links": r["score"]["FALSE_NEGATIVE"],
            "Exceptions": r["exception_count"],
        }
        for r in payload["results"]
    ]


def write_report(payload):
    lines = [
        "## Blind and hard validation",
        "",
        "Each dataset contains 1,000,000 source records. Matching SQL and UDF hashes were frozen before the holdout and verified after every run. No rule was tuned against either result. Full manifests, category scores and false-edge examples are in [validation_results.json](validation_results.json).",
        "",
        "| Dataset | Precision | Recall | False links | Missed links | Exceptions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparison_rows(payload):
        lines.append(
            "| "
            + " | ".join(
                str(row[k])
                for k in (
                    "Dataset",
                    "Precision",
                    "Recall",
                    "False links",
                    "Missed links",
                    "Exceptions",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Blind seed: `20261025`, with independently randomised 0.5–1.5× break rates persisted in its manifest. Hard seed: `20261104`, with equal-amount/day collisions, combined two-character name errors and truncated references, T+4/T+5 delays, ±1-paise fee differences, four/five-way splits, and duplicated or reversed bank lines.",
            "",
            "The event oracle writes original identifiers and expected links separately from degraded source fields. Matching never reads those labels; SQL scoring reads them afterward. The generator and matcher share synthetic assumptions, so this is a robustness check, not independent production validation. A labelled NBFC partner dataset and held-out institutions, dates and channels are needed next.",
            "",
            "Ambiguous references, extra transfers and out-of-window delays usually remain open for human review. Bank reversals expose a specific limitation: the original credit can still be accepted even though a later debit cancels it. Hard-mode precision measures that failure honestly; reversal-aware matching is future work, and was not added after seeing this holdout.",
            "",
        ]
    )
    path = ROOT / "docs/benchmarks.md"
    text = path.read_text().split("## Blind and hard validation")[0].rstrip()
    path.write_text(text + "\n\n" + "\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/milaan-validation"))
    parser.add_argument("--restore", type=Path, default=ROOT / "data/10000000")
    args = parser.parse_args()
    if shutil.disk_usage(ROOT).free < 6_000_000_000:
        raise RuntimeError("Restore the 6 GB workspace reserve before validation")
    if shutil.disk_usage(args.workdir.parent).free < 7_000_000_000:
        raise RuntimeError("Insufficient temporary storage for validation")
    normal = json.loads((ROOT / "docs/benchmark_results.json").read_text())["results"][0]
    payload = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "matching_fingerprints": fingerprints(),
        "rules_changed": False,
        "results": [
            {
                "label": "Normal",
                "seed": 42,
                "source_rows": normal["source_rows"],
                "run_id": normal["run_id"],
                "seconds": normal["seconds"],
                "score": normal["score"],
                "scores": normal["scores"],
                "exception_count": sum(r["N"] for r in normal["exceptions"]),
            }
        ],
    }
    path = ROOT / "docs/validation_results.json"
    folders = []
    try:
        for label, seed, options in (
            ("Blind", 20261025, {"randomise_rates": True}),
            ("Hard", 20261104, {"difficulty": "hard"}),
        ):
            folder = args.workdir / label.lower()
            if folder.exists():
                raise FileExistsError(f"Refusing to overwrite {folder}")
            folders.append(folder)
            manifest = generate(folder, 1_000_000, seed=seed, **options)
            tick = perf_counter()
            load(folder)
            load_seconds = perf_counter() - tick
            result = recon()
            if fingerprints() != payload["matching_fingerprints"]:
                raise RuntimeError("Matching rules changed during validation")
            result.pop("stage_profiles", None)
            result.update(
                {
                    "label": label,
                    "seed": seed,
                    "source_rows": manifest["source_rows"],
                    "manifest": manifest,
                    "load_seconds": load_seconds,
                    "scores": query("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type"),
                    "exception_count": query('SELECT COUNT(*) N FROM MILAAN_RES."EXCEPTION"')[0][
                        "N"
                    ],
                    "exception_categories": query(
                        'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
                    ),
                    "false_link_examples": query(
                        "SELECT * FROM MILAAN_CORE.FALSE_EDGE ORDER BY ledger_id,bank_txn_id LIMIT 12"
                    ),
                }
            )
            payload["results"].append(result)
            path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
            print(json.dumps(comparison_rows(payload), indent=2), flush=True)
            # Only these script-owned synthetic CSV folders are removed.
            shutil.rmtree(folder)
        write_report(payload)
    finally:
        for folder in folders:
            if folder.exists():
                shutil.rmtree(folder)
        print("Restoring retained 10M demonstration dataset", flush=True)
        load(args.restore)
        restored = recon()
        generate_explanations()
        payload["restored_demo"] = {
            "run_id": restored["run_id"],
            "source_rows": query("SELECT source_rows FROM MILAAN_AUDIT.DATASET")[0]["SOURCE_ROWS"],
            "score": restored["score"],
            "seconds": restored["seconds"],
        }
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
