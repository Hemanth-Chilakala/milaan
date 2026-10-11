# Measured benchmarks

Measured UTC: 11 Oct 2026 · 06:16 UTC. Host: 4 cores, 15.62 GiB RAM; Exasol Personal 2026.2.0-nano.3.

All data is synthetic. No browser or recorder ran during these measurements. Source records combine ledger, bank, gateway and NACH files; ground truth is separate. Total month reconciliation includes preparation, matching, classification, result materialisation, SQL scoring, validation and commits. Explanations and profile flush follow the timer.

| Source records | Import + normalise | Total reconciliation | Precision | Recall | Auto-matched records |
|---:|---:|---:|---:|---:|---:|
| 1,000,000 | 31.560s | 22.675s | 100.000% | 100.000% | 98.540% |
| 10,000,000 | Retained sources; not rerun | 88.229s | 100.000% | 100.000% | 98.538% |

## Matching passes

| Pass | 1M seconds | 10M seconds |
|---|---:|---:|
| EXACT | 3.994 | 22.152 |
| PG_BATCH | 1.425 | 7.629 |
| FEE_AWARE | 2.329 | 9.148 |
| TOLERANT | 0.422 | 1.795 |
| FUZZY | 0.384 | 0.911 |
| SPLIT_MERGE | 0.520 | 3.110 |
| CLASSIFY | 2.463 | 9.880 |

10M run: `9298a547-5446-4cce-bbb4-902fdfeef3b8`; 1M normal: `46ed7be5-6ddc-40c9-b470-a6b99d26bef6`. Full native profiles, category scores, exceptions and stage times: [benchmark_results.json](benchmark_results.json).

## Blind and hard validation

| 1M dataset | Seed | Precision | Recall | False links | Missed links | Exceptions |
|---|---:|---:|---:|---:|---:|---:|
| Normal | 42 | 100.000% | 100.000% | 0 | 0 | 10,171 |
| Blind | 20261025 | 100.000% | 100.000% | 0 | 0 | 12,071 |
| Hard (tuned) | 20261104 | 100.000% | 85.872% | 0 | 62,123 | 107,891 |
| Hard (blind) | 20261105 | 100.000% | 85.867% | 0 | 62,132 | 108,103 |

Hard (tuned) seed 20261104 had 3,220 false links before reversal handling. Hard (blind) seed 20261105 was first generated after the rules were frozen. Normal and seed 20261025 are reused regression sets. Complete hashes, manifests, timings and false-edge examples: [validation_results.json](validation_results.json). Matching does not read the oracle.

## Daily close

14 Oct 2026: **29.487s core matching**, **9.966s scoring and validation**, **39.459s total**. The core includes preparation, active sets, all matching passes, result append and classification. The 10-second core target was missed. The separately labelled 13 Oct catch-up took 88.387s total.

Daily run: `72bebcf3-340b-401f-b8ad-b8401534b9f7`. All seven link columns agree with the eligible monthly results (zero differences). The prior three-consecutive-day 10M replay also agreed; a full 30-day 10M replay is unmeasured. [Daily methodology](daily.md), [current raw daily measurements](daily_results.json), [prior three-day proof](daily_incremental_results.json).

## Previous observations and recording

The previous identifier scheme measured 76.144s unrecorded and 114.107s recorded (49.86% overhead). These are historical observations on different identifiers. The previous daily path measured 47.778s core, 5.669s scoring/validation and 53.447s total. After incremental preparation it measured 28.625s core, 9.759s scoring/validation and 38.390s total. Current recorded observations are listed below; historical clips were replaced.

These are individual observations, with potentially warm caches and indexes. No fixed-latency or cold-cache claim is made. Precision/recall count links; auto-match rate counts source memberships and has a different denominator. Synthetic generator and matcher share assumptions. [Performance details](performance.md).

## Comparable starting states

The month benchmark starts after an explicit demo reset, like S02. Reset cost: 27.011s, outside the click-to-results timer. The full unprepared rerun measured 207.039s including 68.221s to restore open tables; [raw observation](unprepared_repeat.json). Both source files and normalization were already loaded. We do not attribute warm-state differences solely to capture configuration.

S03 comparison uses the same-day reset/replay baseline: 31.572s core, 8.666s scoring/validation, 40.244s total, with 8.115s reset outside the timer. This is separate from the first incremental 14 Oct close above. Native audit run: `7247c9be-693b-4e4f-a02c-6ff3ef9bb885`.


## Selected footage measurements

Selected recorded S02: **111.801s**, **26.72%** above the equivalent prepared 88.229s month baseline. Selected S03: **37.280s core**, **11.325s scoring/validation**, **48.611s total**, **20.79%** above the 40.244s same-day reset/replay baseline. These recorded observations are separate from the first-arrival daily close. Reset preparation and explanation generation remain outside the reconciliation timer.

Month run `8d48b1e4-dfbe-4c82-997f-481640891c11`; day run `9eebea6f-2492-4b51-a911-2c92721c58e6`. Both live shots are 1080p/24 fps. Idle clips are 1440p/30 fps after a 4K test missed sampling intervals; native 4K page states and evidence crops are supplied separately. No recording is sped up or replayed. Every selected clip was decoded end to end, with synchronization markers, frame counts and visual frame sequences checked. Frame-count deficits and retakes are disclosed in the editor manifest and event logs.
