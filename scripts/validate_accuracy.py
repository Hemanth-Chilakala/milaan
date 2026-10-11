"""Measure four seeded accuracy sets in isolated schemas without replacing demo data."""

import argparse
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from generator.generate import generate
from milaan import db, pipeline
from milaan.config import ROOT

SETS = {
    "normal": ("Normal", 42, {}),
    "blind": ("Blind", 20261025, {"randomise_rates": True}),
    "hard_tuned": ("Hard (tuned)", 20261104, {"difficulty": "hard"}),
    "hard_blind": ("Hard (blind)", 20261105, {"difficulty": "hard"}),
}


def fingerprints():
    files = sorted((ROOT / "sql").glob("*.sql")) + sorted((ROOT / "udf").glob("*.sql"))
    files += [ROOT / "milaan/reversals.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", nargs="+", choices=SETS, default=list(SETS))
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--prefix", default="MILAAN_VERIFY")
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/milaan-accuracy"))
    parser.add_argument("--output", type=Path, default=ROOT / "docs/accuracy_results.json")
    args = parser.parse_args()
    if not re.fullmatch(r"MILAAN_[A-Z]+", args.prefix) or args.prefix == "MILAAN_DAY":
        raise ValueError("Choose an isolated uppercase schema prefix")
    if shutil.disk_usage(ROOT).free < 6_000_000_000:
        raise RuntimeError("Workspace free space is below the required 6 GB")
    with db.connect() as connection:
        retained = connection.execute(
            "SELECT dataset_id,source_rows FROM MILAAN_AUDIT.DATASET"
        ).fetchone()
    original_scoped_sql = db.scoped_sql
    original_sources = pipeline.SOURCES.copy()
    db.scoped_sql = lambda sql, name: re.sub(
        r"MILAAN_(?!" + re.escape(args.prefix.removeprefix("MILAAN_")) + r"_)",
        args.prefix + "_",
        original_scoped_sql(sql, name),
    )
    pipeline.SOURCES = {
        name: table.replace("MILAAN_", args.prefix + "_")
        for name, table in original_sources.items()
    }
    payload = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "matching_fingerprints": fingerprints(),
        "rules_frozen_before_runs": True,
        "schema_prefix": args.prefix,
        "results": [],
    }
    try:
        pipeline.setup()
        for name in args.sets:
            label, seed, options = SETS[name]
            folder = args.workdir / name
            if folder.exists():
                raise FileExistsError(f"Refusing to overwrite {folder}")
            try:
                manifest = generate(folder, args.rows, seed=seed, **options)
                tick = perf_counter()
                loading = pipeline.load(folder)
                load_seconds = perf_counter() - tick
                result = pipeline.recon()
                if fingerprints() != payload["matching_fingerprints"]:
                    raise RuntimeError("Matching rules changed during validation")
                result.pop("stage_profiles", None)
                result.update(
                    label=label,
                    seed=seed,
                    source_rows=manifest["source_rows"],
                    manifest=manifest,
                    load_seconds=load_seconds,
                    load_timings=loading,
                    load_total_seconds=load_seconds,
                    pass_details=db.query(
                        "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={run!s}",
                        {"run": result["run_id"]},
                    ),
                    exceptions=db.query(
                        'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
                    ),
                    scores=db.query("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type"),
                    exception_count=db.query('SELECT COUNT(*) N FROM MILAAN_RES."EXCEPTION"')[0][
                        "N"
                    ],
                    exception_categories=db.query(
                        'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
                    ),
                    false_link_examples=db.query(
                        "SELECT * FROM MILAAN_CORE.FALSE_EDGE ORDER BY ledger_id,bank_txn_id LIMIT 12"
                    ),
                )
                payload["results"].append(result)
                args.output.write_text(json.dumps(payload, indent=2, default=str) + "\n")
                print(
                    json.dumps(
                        {
                            "label": label,
                            "run_id": result["run_id"],
                            "seconds": result["seconds"],
                            "score": result["score"],
                        },
                        default=str,
                    ),
                    flush=True,
                )
            finally:
                if folder.exists():
                    shutil.rmtree(folder)
    finally:
        # Only this explicitly isolated measurement namespace is dropped.
        with db.connect() as connection:
            for suffix in ("DAY_RES", "DAY_CORE", "DAY_AUDIT", "RES", "CORE", "STG", "AUDIT"):
                connection.execute(f"DROP SCHEMA IF EXISTS {args.prefix}_{suffix} CASCADE")
            connection.commit()
        db.scoped_sql = original_scoped_sql
        pipeline.SOURCES = original_sources
        with db.connect() as connection:
            after = connection.execute(
                "SELECT dataset_id,source_rows FROM MILAAN_AUDIT.DATASET"
            ).fetchone()
        if after != retained:
            raise RuntimeError("The retained demo dataset changed during isolated validation")
        payload["retained_demo_unchanged"] = True
        args.output.write_text(json.dumps(payload, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
