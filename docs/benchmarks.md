# Measured benchmarks

Host: 4 logical CPUs, 15.62 GiB RAM. Database: Exasol Personal 2026.2.0-nano.3.
Measured: 2026-10-08T16:40:54.569455+00:00.

Synthetic data, seed 42. Rows are the combined source-record count across the four files. Ground truth is separate. Single run per size; these are observations, not a throughput guarantee. Loading includes normalisation. Total reconciliation includes result materialisation, validation and SQL scoring; native profiling flush and explanation generation are separately timed.

| Source records | Import + normalise | Reconciliation | Precision | Recall | Auto-matched records |
|---:|---:|---:|---:|---:|---:|
| 1,000,000 | 16.421s | 16.546s | 100.000% | 100.000% | 98.540% |
| 10,000,000 | 82.418s | 114.486s | 100.000% | 99.959% | 98.502% |

## Matching passes

| Pass | 1M seconds | 10M seconds |
|---|---:|---:|
| EXACT | 2.049 | 13.155 |
| PG_BATCH | 1.663 | 11.417 |
| FEE_AWARE | 1.390 | 8.879 |
| TOLERANT | 0.372 | 2.749 |
| FUZZY | 0.512 | 2.265 |
| SPLIT_MERGE | 1.920 | 16.950 |
| CLASSIFY | 2.935 | 22.267 |

Native Exasol execution profiles, per-category scores and exact run IDs are stored in [benchmark_results.json](benchmark_results.json). Query caches and automatically created indexes may be warm; no cold-cache claim is made. Python UDF startup varies between runs.

Precision and recall measure correct ledger–bank–gateway edges. Exceptions with no expected match do not contribute to recall. The auto-match rate measures source membership in groups, so it has a different denominator. A gateway payment can belong to a valid bank batch while still raising a missing-ledger exception.

Profiles follow the [Exasol profiling documentation](https://docs.exasol.com/db/latest/database_concepts/profiling.htm).
