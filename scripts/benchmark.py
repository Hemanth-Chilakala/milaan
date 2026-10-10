"""Measure generation, bulk import and reconciliation on the actual host."""

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from time import perf_counter

from generator.generate import generate
from milaan.config import ROOT
from milaan.db import connect, query
from milaan.explain import generate_explanations
from milaan.pipeline import load, recon, setup


def compare_baseline(size, result):
    """Compare all seven link columns and labelled exception amounts inside Exasol."""
    proof = {}
    with connect() as connection:
        for label, columns, current, saved in (
            ("links", "*", "MILAAN_RES.LINK", f"MILAAN_REFERENCE.LINK_{size}"),
            (
                "exceptions",
                "exception_id,category,amount_paise",
                'MILAAN_RES."EXCEPTION"',
                f"MILAAN_REFERENCE.EXCEPTION_{size}",
            ),
        ):
            difference = connection.execute(
                f"SELECT COUNT(*) N FROM ((SELECT {columns} FROM {current} MINUS SELECT * FROM {saved}) UNION ALL (SELECT * FROM {saved} MINUS SELECT {columns} FROM {current}))"
            ).fetchone()["N"]
            counts = connection.execute(
                f"SELECT (SELECT COUNT(*) FROM {current}) ACTUAL,(SELECT COUNT(*) FROM {saved}) EXPECTED"
            ).fetchone()
            proof[label] = {"differences": difference, **counts}
            if difference or counts["ACTUAL"] != counts["EXPECTED"]:
                raise RuntimeError(
                    f"{label} differ from the {size:,}-record baseline: {proof[label]}"
                )
    before = next(
        r
        for r in json.loads((ROOT / "docs/performance_baseline.json").read_text())["results"]
        if r["source_rows"] == size
    )

    def without_run_id(rows):
        return [{k: v for k, v in r.items() if k != "RUN_ID"} for r in rows]

    if without_run_id(before["scores"]) != without_run_id(result["scores"]):
        raise RuntimeError("Per-category accuracy changed during optimisation")
    proof["scores_identical"] = True
    return proof


def write_report(payload):
    results = payload["results"]
    memory = payload["ram_bytes"]
    lines = [
        "# Measured benchmarks",
        "",
        f"Host: {payload['logical_cpus']} logical CPUs, {memory / 2**30:.2f} GiB RAM. Database: {payload['database']}.",
        f"Measured: {payload['measured_at_utc']}.",
        "",
        "Synthetic data, seed 42. Rows are the combined source-record count across the four files; ground truth is separate. No browser or recorder runs during these measurements. Loading includes normalisation. Total reconciliation includes open-item preparation and maintenance, result materialisation, validation, commits and SQL scoring. Native profiling flush and explanation generation follow the timed reconciliation.",
        "",
        "| Source records | Import + normalise | Reconciliation | Precision | Recall | Auto-matched records |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        s = r["score"]
        lines.append(
            f"| {r['source_rows']:,} | {r['load_total_seconds']:.3f}s | {r['seconds']:.3f}s | {s['PRECISION_VALUE'] * 100:.3f}% | {s['RECALL_VALUE'] * 100:.3f}% | {s['AUTO_MATCH_RATE'] * 100:.3f}% |"
        )
    lines.extend(
        ["", "## Matching passes", "", "| Pass | 1M seconds | 10M seconds |", "|---|---:|---:|"]
    )
    for name in results[0]["passes"]:
        values = [f"{r['passes'][name]:.3f}" for r in results]
        if len(values) == 1:
            values.append("pending")
        lines.append(f"| {name} | {' | '.join(values)} |")
    repeated_path = ROOT / "docs/performance_repeated.json"
    if repeated_path.exists():
        repeated = json.loads(repeated_path.read_text())
        lines.extend(
            [
                "",
                "## Repeated full-month close",
                "",
                f"Additional observation: run `{repeated['run_id']}` took **{repeated['seconds']:.3f}s**, including **{repeated['stage_times']['PREPARATION']:.3f}s** to restore the open-item tables without reloading. It preserved all links, labelled exceptions and category scores. Caches and automatic indexes were warm; unused development comparison tables had been removed. Details are in [performance_repeated.json](performance_repeated.json).",
            ]
        )
    lines.extend(
        [
            "",
            "## Other reconciliation stages",
            "",
            "| Stage | 1M seconds | 10M seconds |",
            "|---|---:|---:|",
        ]
    )
    for name in results[0]["stage_times"]:
        values = [f"{r['stage_times'][name]:.3f}" for r in results]
        if len(values) == 1:
            values.append("pending")
        lines.append(f"| {name} | {' | '.join(values)} |")
    lines.extend(
        [
            "",
            "## Previous measurements",
            "",
            "Preserved observations, before the performance changes:",
            "",
            "| Measurement | Source records | Reconciliation |",
            "|---|---:|---:|",
        ]
    )
    previous = payload["previous_measurements"]
    for r in previous["size_benchmarks"]["results"]:
        lines.append(f"| Original size benchmark | {r['source_rows']:,} | {r['seconds']:.3f}s |")
    recorded = previous["recorded_run"]
    lines.append(f"| Original recorded demonstration | 10,000,000 | {recorded['seconds']:.3f}s |")
    baseline = json.loads((ROOT / "docs/performance_baseline.json").read_text())
    for r in baseline["results"]:
        lines.append(
            f"| Isolated baseline, 9 October | {r['source_rows']:,} | {r['seconds']:.3f}s |"
        )
    lines.extend(
        [
            "",
            "Full original profiles and run IDs are retained in [performance_previous.json](performance_previous.json) and [performance_baseline.json](performance_baseline.json). The recorded observation shared CPU with the browser and recorder.",
            "",
            "[performance.md](performance.md) explains the changes, operator profiles and result comparisons. Current timings, per-category scores, exception counts and profiles are in [benchmark_results.json](benchmark_results.json).",
            "",
            "Precision and recall measure ledger–bank–gateway edges. Exceptions with no expected match do not contribute to recall. Auto-match rate measures source membership in groups and uses a different denominator. A gateway payment can belong to a valid bank batch while raising a missing-ledger exception.",
            "",
            "These are individual observations on this host. Caches and automatic indexes may be warm; no cold-cache claim is made. Profiles follow the [Exasol profiling documentation](https://docs.exasol.com/db/latest/database_concepts/profiling.htm).",
        ]
    )
    (ROOT / "docs/benchmarks.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare saved local MILAAN_REFERENCE tables; not required for a fresh deployment",
    )
    args = parser.parse_args()
    processes = subprocess.check_output(["ps", "-eo", "comm="], text=True).split()
    if any(name in {"ffmpeg", "chromium", "chrome", "Xvfb"} for name in processes):
        raise RuntimeError("Stop the browser and recorder before benchmarking")
    setup()
    with connect() as connection:
        database = "Exasol Personal " + connection.login_info["releaseVersion"]
    previous = json.loads((ROOT / "docs/performance_previous.json").read_text())
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    results = []
    for size in (1_000_000, 10_000_000):
        folder = ROOT / "data" / str(size)
        started = perf_counter()
        generation_reused = (folder / "manifest.json").exists()
        if not generation_reused:
            if shutil.disk_usage(ROOT).free < 6_000_000_000 + size * 250:
                raise RuntimeError(
                    "Insufficient space to generate data and retain the 6 GB reserve"
                )
            generate(folder, size)
        generation = None if generation_reused else perf_counter() - started
        started = perf_counter()
        imports = load(folder)
        load_total = perf_counter() - started
        started = perf_counter()
        result = recon()
        result["recon_call_seconds"] = perf_counter() - started
        started = perf_counter()
        generate_explanations()
        explanation_seconds = perf_counter() - started
        result.update(
            {
                "source_rows": size,
                "generation_seconds": generation,
                "generation_reused": generation_reused,
                "load_total_seconds": load_total,
                "imports": imports,
                "explanation_seconds": explanation_seconds,
                "exceptions": query(
                    'SELECT category,COUNT(*) N FROM MILAAN_RES."EXCEPTION" GROUP BY category ORDER BY category'
                ),
                "scores": query("SELECT * FROM MILAAN_RES.SCORE ORDER BY break_type"),
                "pass_details": query(
                    "SELECT * FROM MILAAN_AUDIT.PASS_TIMING WHERE run_id={id!s}",
                    {"id": result["run_id"]},
                ),
            }
        )
        if args.compare_baseline:
            result["baseline_comparison"] = compare_baseline(size, result)
            print(
                f"Baseline comparison at {size:,} records: identical links, exceptions and scores",
                flush=True,
            )
        results.append(result)
        payload = {
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "logical_cpus": len(os.sched_getaffinity(0)),
            "ram_bytes": memory,
            "database": database,
            "recording": False,
            "results": results,
            "previous_measurements": previous,
        }
        (ROOT / "docs/benchmark_results.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n"
        )
        write_report(payload)


if __name__ == "__main__":
    main()
