# Reconciliation performance

Measured on 4 logical CPUs and 15.62 GiB RAM, Exasol Personal 2026.2.0-nano.3. Synthetic seed 42, one month of collections. Both the baseline and current runs were measured without a browser or recorder.

The current 10M reconciliation takes **76.144 seconds**, compared with **96.550 seconds** before optimisation. The reduction is 21.1%. The under-90-second minimum is met; the 60-second target is not met.

## Before and after

| Pass or stage | 1M before | 1M after | 10M before | 10M after |
|---|---:|---:|---:|---:|
| EXACT | 2.083s | 3.056s | 12.385s | 19.274s |
| PG_BATCH | 1.694s | 1.159s | 10.938s | 6.040s |
| FEE_AWARE | 1.395s | 1.747s | 8.605s | 7.145s |
| TOLERANT | 0.455s | 0.368s | 2.546s | 1.559s |
| FUZZY | 0.495s | 0.390s | 2.213s | 1.128s |
| SPLIT_MERGE | 1.680s | 0.370s | 15.389s | 3.035s |
| CLASSIFY | 2.922s | 1.776s | 19.527s | 12.773s |
| PREPARATION | 0.000s | 0.026s | 0.000s | 0.033s |
| RESULTS | 1.873s | 1.883s | 10.208s | 10.243s |
| SCORING | 1.199s | 1.599s | 10.162s | 9.668s |
| VALIDATION | 0.502s | 0.510s | 3.840s | 4.578s |
| **Total reconciliation** | **15.010s** | **13.707s** | **96.550s** | **76.144s** |

Totals include preparation, per-pass open-item maintenance, result materialisation, SQL scoring, validation, commits and audit writes. Native profiling collection and explanation generation follow the measured close. The complete Python call also includes final run metadata, profiling collection and graceful connection cleanup; those wall-clock observations are reported below. Operator durations can overlap, so they must not be summed to infer wall-clock time.

## Load and reset costs

Open-item payloads and typed scoring keys are materialised during loading, which is included in the load measurements. A fresh load prepares the full open sets. A rerun restores removed rows before matching; its restoration is inside the reconciliation timer. This is a full-month rerun, not daily carry-forward processing.

| Source records | Load before | Load after | Profile collection after | Complete recon call after |
|---|---:|---:|---:|---:|
| 1,000,000 | 13.761s | 19.820s | 0.895s | 15.894s |
| 10,000,000 | 74.856s | 105.458s | 0.869s | 88.219s |

A repeat of the 10M run, without reloading, took **78.861s**, including **11.406s** to restore the open tables. Its SQL comparison also found zero differences in links and labelled exception amounts, and all category scores remained identical. Run `d3ede53f-f6a8-41e8-9b7e-c51509b603c9` is retained in [performance_repeated.json](performance_repeated.json).

## Changes retained

1. `sql/20_normalise.sql` materialises `ref_suffix8` and aligns reference, loan, name and amount types. Later joins compare columns rather than calculating suffixes repeatedly. Typed ground-truth keys are used only by scoring; no matching pass reads them.
2. `OPEN_LEDGER`, `OPEN_BANK` and `OPEN_PG` contain the narrow matching payloads. Each pass removes consumed keys using a small, three-column `PASS_LINK` table containing only that pass’s edges. Later passes join the physically smaller sets. Reruns restore each open table from immutable normalised sources when its count has shrunk.
3. `sql/35_pass_split_merge.sql` rejects groups outside 2–12 credits or whose sum cannot reach the target before invoking the SET UDF. The native Lua implementation keeps the same unique two-or-three-credit subset rule, rejects duplicate keys and ambiguous solutions, and uses exact Exasol decimals. Python remains the independent test oracle and the language for similarity and explanations.
4. `sql/36_classify.sql` uses `UNION ALL` with one de-duplication, materialised ledger-reference existence and one bank-link aggregation restricted to the relevant missing gateway receipts. Candidate evidence still searches the full bank table so duplicate postings can refer to an already matched credit.
5. `udf/03_evidence.sql` writes the same JSON fields through native Lua, preserving integer decimal text and JSON escaping. Tests cover Unicode, quotes, newlines and paise values above 2^53.
6. `sql/50_score.sql` uses typed edge keys and labels only false candidates, avoiding a full-ledger label aggregation when there are no false edges. The final conflict check still rejects membership in multiple groups.

The optional single-call Lua orchestrator was not added. Python triggers and times the SQL passes; all matching, scoring and explanation computation stays inside Exasol.

## Measured alternatives

On the same 10M inputs, exact-match window checks took 9.164s, versus 10.675s for materialised candidates and `GROUP BY ... HAVING COUNT(*)=1`. Their complete links were identical; the window version was retained.

For the saved split candidates, the eligible-group filter reduced 39,965 groups to 17,673. Python took 10.491s; Lua took 1.269s. Both emitted 44,100 proposed links, with zero differences. These are isolated proposal-stage measurements, not the full pass times above.

Three two-row calls measured the small-call overhead: Python 0.0817s, 0.0722s, 0.0794s; Lua 0.0070s, 0.0059s, 0.0061s. These include SQL compilation, transport and execution and therefore bound small-call overhead; they do not isolate VM launch time. The baseline split GROUP BY used 29.4 CPU-seconds over 10.763 elapsed seconds, so startup alone did not explain the cost.

The Lua runtime and exact decimal type follow [Exasol’s Lua UDF documentation](https://docs.exasol.com/db/latest/database_concepts/udf_scripts/lua.htm) and [decimal type documentation](https://docs.exasol.com/db/latest/database_concepts/scripting/general_script_language.htm). Comparison profiles are in [performance_comparisons.json](performance_comparisons.json).

## Discarded implementations

| Trial | 1M seconds | 10M seconds |
|---|---:|---:|
| Repeated wide copies | 27.677 | 134.597 |
| Narrow copies and deletion | 17.673 | 100.575 |
| Key tables with joins | 16.263 | 116.390 |
| Delayed open-table creation | 15.657 | 84.801 |
| Persistent open flags | 14.683 | 88.805 |
| Physical pruning before conformed NACH keys | 13.929 | 79.900 |

Wide copying, extra key-table joins and retained closed-row flags increased overhead. The final implementation keeps narrow payload tables prepared by loading and physically removes consumed rows. These exploratory observations are preserved in [performance_trials.json](performance_trials.json); they are not used as the final headline.

## Native operator evidence

| Stage | Slowest baseline operator | Baseline duration | Slowest current operator | Current duration |
|---|---|---:|---|---:|
| EXACT | INSERT / LINK | 2.597s | INSERT / LINK | 2.452s |
| PG_BATCH | INDEX CREATE / LEDGER | 1.200s | SCAN / PG | 0.896s |
| FEE_AWARE | INDEX CREATE / BANK | 1.088s | INSERT / PASS_LINK | 0.953s |
| TOLERANT | INDEX CREATE / BANK | 1.069s | INSERT / PASS_LINK | 0.293s |
| FUZZY | INDEX CREATE / BANK | 0.904s | INSERT / tmp_subselect0 | 0.627s |
| SPLIT_MERGE | GROUP BY / SPLIT_PROPOSAL | 10.763s | GROUP BY / SPLIT_PROPOSAL | 1.190s |
| CLASSIFY | INSERT / EXCEPTION | 6.853s | INSERT / EXCEPTION | 1.368s |
| RESULTS | INSERT / MATCH_MEMBER | 4.158s | INSERT / MATCH_MEMBER | 4.215s |
| SCORING | OUTER JOIN / LINK | 2.151s | INSERT / SCORING_LINK | 3.344s |

Profiles retain statement/part IDs, object and output row counts, CPU, peak temporary RAM, disk and network activity. Query tags identify every pass and result/scoring stage. Durations are native operator observations rather than end-to-end pass timings.

## Result preservation

| Source records | Links compared | Link differences | Exceptions compared | Exception differences | All category scores identical |
|---:|---:|---:|---:|---:|---|
| 1,000,000 | 438,576 | 0 | 10,171 | 0 | True |
| 10,000,000 | 4,383,200 | 0 | 103,564 | 0 | True |

The 10M run retains 100.000% precision, 99.959% recall, 0 false links and 1,779 missed links. Auto-matched source membership is 98.502%. These describe the seeded synthetic corpus; holdout and ambiguity validation are separate work.

The SQL proof compares all seven link columns in both directions and checks cardinality, not just totals. Exception IDs, categories and paise amounts are compared in both directions. Every per-category score is compared after excluding the new run ID. The fixture test additionally checks stored pre-optimisation output; rerun tests compare all link columns. Native subset tests compare 47 bounded, ambiguous, duplicate-key, capped and large-amount cases with the Python oracle.

The original observations are preserved in [performance_previous.json](performance_previous.json), the isolated baseline in [performance_baseline.json](performance_baseline.json), and current raw results in [benchmark_results.json](benchmark_results.json). Benchmark with `make bench`; `make bench BENCH_ARGS=--compare-baseline` additionally checks the saved local reference tables. The reference schema is a development validation aid and is not required on a fresh deployment.

Individual runs vary with caches, automatically created indexes, UDF startup and host contention. No cold-cache or guaranteed-latency claim is made.
