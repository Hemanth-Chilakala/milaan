# Performance measurements

Current unrecorded 10M month: **88.229s**, run `9298a547-5446-4cce-bbb4-902fdfeef3b8`. The 60-second target was missed. All measured stages and profiles are preserved in [benchmark_results.json](benchmark_results.json).

14 Oct 2026: **29.487s core matching**, **9.966s scoring and validation**, **39.459s total**. The core includes preparation, active sets, all matching passes, result append and classification. The 10-second core target was missed. The separately labelled 13 Oct catch-up took 88.387s total.

| Other monthly stage | Seconds |
|---|---:|
| PREPARATION | 0.404s |
| RESULTS | 10.666s |
| SCORING | 8.841s |
| VALIDATION | 5.168s |

Daily work keeps persistent open items, filters new arrivals, appends results and retains closed groups. Core timing includes preparation and classification. Oracle maintenance and full-history conflict validation are separately timed. Bank reversals add an evidence check before passes; a later debit reopens the affected daily group.

Capture configuration uses core 3 for Xvfb, Chromium and ffmpeg, one browser tab, one-second dashboard polling, disabled GPU/smooth scrolling and 1080p24 live shots. Actual recorded overhead has not yet been measured. The below-20% target cannot be assessed until the footage run. Historical recorded overhead was 49.86%.

There are no production latency guarantees. CPU contention, automatic indexes, reference collision/skew, group size and cache state affect runtime. Full 30-day 10M replay, 100M records and concurrent workloads are unmeasured.

The prepared month reset took 27.011s outside the Run button timer. The full unprepared rerun took 207.039s; its open-item restoration cost 68.221s. Both observations are retained. A recording comparison must start from the same prepared state.


## Selected footage measurements

Selected recorded S02: **111.801s**, **26.72%** above the equivalent prepared 88.229s month baseline. Selected S03: **37.280s core**, **11.325s scoring/validation**, **48.611s total**, **20.79%** above the 40.244s same-day reset/replay baseline. These recorded observations are separate from the first-arrival daily close. Reset preparation and explanation generation remain outside the reconciliation timer.

Month run `8d48b1e4-dfbe-4c82-997f-481640891c11`; day run `9eebea6f-2492-4b51-a911-2c92721c58e6`. Both live shots are 1080p/24 fps. Idle clips are 1440p/30 fps after a 4K test missed sampling intervals; native 4K page states and evidence crops are supplied separately. No recording is sped up or replayed. Every selected clip was decoded end to end, with synchronization markers, frame counts and visual frame sequences checked. Frame-count deficits and retakes are disclosed in the editor manifest and event logs.
