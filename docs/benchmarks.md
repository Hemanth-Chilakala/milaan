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

<!-- RECORDING_START -->
## Final recorded demonstration

Run `4a1ac89d-4de3-4e2d-a7fe-bdcb78cc28d5` reconciled **10,000,000 source records in 203.883s**. It measured **100.000% precision**, **99.959% recall** and **98.502% source membership**, with 0 false links, 1,779 missed links and 103,564 exceptions.

The earlier size-comparison table remains an observation from its original runs. This later run is the headline used by the README, deck and narration. The browser and recorder shared the measured host; no isolated-compute or cold-cache claim is made. Later classification groups low-confidence payer cases into one review item, so its exception count differs from the initial benchmark. The under-one-minute aspiration was not achieved.

| Pass | Receipt links | Recorded seconds |
|---|---:|---:|
| EXACT | 3,164,644 | 25.34s |
| PG_BATCH | 35,303 | 18.67s |
| FEE_AWARE | 1,079,439 | 17.20s |
| TOLERANT | 43,689 | 6.47s |
| FUZZY | 16,025 | 4.78s |
| SPLIT_MERGE | 44,100 | 31.60s |
| CLASSIFY | 0 | 39.61s |

The exact run, scores and native profiles are in [recording.json](video/recording.json). The video visibly compresses the reconciliation footage to fit the three-minute submission limit.
<!-- RECORDING_END -->
