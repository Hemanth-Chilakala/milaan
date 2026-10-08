"""Measure generation, bulk import and reconciliation on the actual host."""

import json
import os
from datetime import UTC, datetime
from time import perf_counter

from generator.generate import generate
from milaan.config import ROOT
from milaan.db import query
from milaan.explain import generate_explanations
from milaan.pipeline import load, recon, setup


def main():
    setup()
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    results = []
    for size in (1_000_000, 10_000_000):
        folder = ROOT / "data" / str(size)
        started = perf_counter()
        if not (folder / "manifest.json").exists():
            generate(folder, size)
        generation = perf_counter() - started
        started = perf_counter()
        imports = load(folder)
        load_total = perf_counter() - started
        result = recon()
        started = perf_counter()
        generate_explanations()
        explanation_seconds = perf_counter() - started
        result.update(
            {
                "source_rows": size,
                "generation_seconds": generation,
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
        results.append(result)
        payload = {
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "logical_cpus": len(os.sched_getaffinity(0)),
            "ram_bytes": memory,
            "database": "Exasol Personal 2026.2.0-nano.3",
            "results": results,
        }
        (ROOT / "docs/benchmark_results.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n"
        )
        lines = [
            "# Measured benchmarks",
            "",
            f"Host: {payload['logical_cpus']} logical CPUs, {memory / 2**30:.2f} GiB RAM. Database: {payload['database']}.",
            f"Measured: {payload['measured_at_utc']}.",
            "",
            "Synthetic data, seed 42. Rows are the combined source-record count across the four files. Ground truth is separate. Single run per size; these are observations, not a throughput guarantee. Loading includes normalisation. Total reconciliation includes result materialisation, validation and SQL scoring; native profiling flush and explanation generation are separately timed.",
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
            lines.append(
                f"| {name} | {' | '.join(values)}" + (" | pending |" if len(values) == 1 else " |")
            )
        lines.extend(
            [
                "",
                "Native Exasol execution profiles, per-category scores and exact run IDs are stored in [benchmark_results.json](benchmark_results.json). Query caches and automatically created indexes may be warm; no cold-cache claim is made. Python UDF startup varies between runs.",
                "",
                "Precision and recall measure correct ledger–bank–gateway edges. Exceptions with no expected match do not contribute to recall. The auto-match rate measures source membership in groups, so it has a different denominator. A gateway payment can belong to a valid bank batch while still raising a missing-ledger exception.",
                "",
                "Profiles follow the [Exasol profiling documentation](https://docs.exasol.com/db/latest/database_concepts/profiling.htm).",
            ]
        )
        (ROOT / "docs/benchmarks.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
