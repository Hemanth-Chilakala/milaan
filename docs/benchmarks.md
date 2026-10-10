# Measured benchmarks

Host: 4 logical CPUs, 15.62 GiB RAM. Database: Exasol Personal 2026.2.0-nano.3.
Measured: 2026-10-10T06:48:42.176972+00:00.

Synthetic data, seed 42. Rows are the combined source-record count across the four files; ground truth is separate. No browser or recorder runs during these measurements. Loading includes normalisation. Total reconciliation includes open-item preparation and maintenance, result materialisation, validation, commits and SQL scoring. Native profiling flush and explanation generation follow the timed reconciliation.

| Source records | Import + normalise | Reconciliation | Precision | Recall | Auto-matched records |
|---:|---:|---:|---:|---:|---:|
| 1,000,000 | 19.820s | 13.707s | 100.000% | 100.000% | 98.540% |
| 10,000,000 | 105.458s | 76.144s | 100.000% | 99.959% | 98.502% |

## Matching passes

| Pass | 1M seconds | 10M seconds |
|---|---:|---:|
| EXACT | 3.056 | 19.274 |
| PG_BATCH | 1.159 | 6.040 |
| FEE_AWARE | 1.747 | 7.145 |
| TOLERANT | 0.368 | 1.559 |
| FUZZY | 0.390 | 1.128 |
| SPLIT_MERGE | 0.370 | 3.035 |
| CLASSIFY | 1.776 | 12.773 |

## Repeated full-month close

Additional observation: run `d3ede53f-f6a8-41e8-9b7e-c51509b603c9` took **78.861s**, including **11.406s** to restore the open-item tables without reloading. It preserved all links, labelled exceptions and category scores. Caches and automatic indexes were warm; unused development comparison tables had been removed. Details are in [performance_repeated.json](performance_repeated.json).

## Other reconciliation stages

| Stage | 1M seconds | 10M seconds |
|---|---:|---:|
| PREPARATION | 0.026 | 0.033 |
| RESULTS | 1.883 | 10.243 |
| SCORING | 1.599 | 9.668 |
| VALIDATION | 0.510 | 4.578 |

## Previous measurements

Preserved observations, before the performance changes:

| Measurement | Source records | Reconciliation |
|---|---:|---:|
| Original size benchmark | 1,000,000 | 16.546s |
| Original size benchmark | 10,000,000 | 114.486s |
| Original recorded demonstration | 10,000,000 | 203.883s |
| Isolated baseline, 9 October | 1,000,000 | 15.010s |
| Isolated baseline, 9 October | 10,000,000 | 96.550s |

Full original profiles and run IDs are retained in [performance_previous.json](performance_previous.json) and [performance_baseline.json](performance_baseline.json). The recorded observation shared CPU with the browser and recorder.

[performance.md](performance.md) explains the changes, operator profiles and result comparisons. Current timings, per-category scores, exception counts and profiles are in [benchmark_results.json](benchmark_results.json).

Precision and recall measure ledger–bank–gateway edges. Exceptions with no expected match do not contribute to recall. Auto-match rate measures source membership in groups and uses a different denominator. A gateway payment can belong to a valid bank batch while raising a missing-ledger exception.

These are individual observations on this host. Caches and automatic indexes may be warm; no cold-cache claim is made. Profiles follow the [Exasol profiling documentation](https://docs.exasol.com/db/latest/database_concepts/profiling.htm).

## Blind and hard validation

Each dataset contains 1,000,000 source records. Matching SQL and UDF hashes were frozen before the holdout and verified after every run. No rule was tuned against either result. Full manifests, category scores and false-edge examples are in [validation_results.json](validation_results.json).

| Dataset | Precision | Recall | False links | Missed links | Exceptions |
|---|---:|---:|---:|---:|---:|
| Normal | 100.000% | 100.000% | 0 | 0 | 10171 |
| Blind | 100.000% | 100.000% | 0 | 0 | 12071 |
| Hard | 99.154% | 85.872% | 3220 | 62121 | 104668 |

Blind seed: `20261025`, with independently randomised 0.5–1.5× break rates persisted in its manifest. Hard seed: `20261104`, with equal-amount/day collisions, combined two-character name errors and truncated references, T+4/T+5 delays, ±1-paise fee differences, four/five-way splits, and duplicated or reversed bank lines.

The event oracle writes original identifiers and expected links separately from degraded source fields. Matching never reads those labels; SQL scoring reads them afterward. The generator and matcher share synthetic assumptions, so this is a robustness check, not independent production validation. A labelled NBFC partner dataset and held-out institutions, dates and channels are needed next.

Ambiguous references, extra transfers and out-of-window delays usually remain open for human review. Bank reversals expose a specific limitation: the original credit can still be accepted even though a later debit cancels it. Hard-mode precision measures that failure honestly; reversal-aware matching is future work, and was not added after seeing this holdout.
