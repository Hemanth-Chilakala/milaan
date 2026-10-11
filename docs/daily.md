# Daily close

14 Oct 2026: **29.487s core matching**, **9.966s scoring and validation**, **39.459s total**. The core includes preparation, active sets, all matching passes, result append and classification. The 10-second core target was missed. The separately labelled 13 Oct catch-up took 88.387s total.

| 14 Oct 2026 observation | Core matching | Scoring / validation | Total |
|---|---:|---:|---:|
| Original cumulative implementation | 47.778s | 5.669s | 53.447s |
| Previous incremental measurement | 28.625s | 9.759s | 38.390s |
| Current first-arrival close | 29.487s | 9.966s | 39.459s |

The current close processes 499,644 new source records plus carried open items; 4,329,564 source records have arrived. Core includes source preparation, reversal checks, active sets, all seven passes, result appends, classification, progress and commits. Oracle maintenance, SQL scoring and full-history conflict validation are separately timed. Namespace setup and profiling export are outside the stored total.

Daily results retain closed history and persistent open items. Only newly arriving rows enter the next close. Gateway reviews carry forward without re-aggregating closed batches. A later equal-reference/amount debit reopens the affected group; both cancelled bank lines are excluded. Ambiguous reversal pairs remain under review.

## Current correctness and starting state

All seven link columns for the first 14 Oct close matched eligible monthly links with zero differences. First-arrival run: `72bebcf3-340b-401f-b8ad-b8401534b9f7`. Its source preparation took 6.051s. Native timings and profiles: [daily_results.json](daily_results.json).

The first 13 Oct catch-up took 69.319s core, 19.062s scoring/validation and 88.387s total; it is not a new-arrivals close.

## Prior three-consecutive-day proof

| Close | Core | Scoring / validation | Total | Differences |
|---|---:|---:|---:|---:|
| 14 Oct 2026 | 28.625s | 9.759s | 38.390s | 0 |
| 15 Oct 2026 | 29.397s | 10.938s | 40.341s | 0 |
| 16 Oct 2026 | 28.755s | 10.752s | 39.513s | 0 |

These are preserved prior observations, before reversal handling. All edge keys and all seven link columns agreed with the eligible monthly results. [Raw proof](daily_incremental_results.json). The 22-business-day fixture also reproduced all 437 month links. The dedicated late-reversal test verifies reopening. Full 30-day 10M replay remains unmeasured.

## Limitations and reproduction

The 10-second core target remains missed. Index maintenance, result/membership materialisation and classification remain material costs; full-history scoring/validation is separately timed. Same-day replay and catch-up have different starting states from new-arrival processing. The prepared month benchmark and unprepared full rerun are separate observations; capture overhead must compare equivalent starting states.

Use `make recon-day DATE=2026-10-14` to close a date. Going back requires `--restart` through the daily Python module. `python -m scripts.refresh_measurements` refreshes the unrecorded month and first daily arrival measurements. `--prepared-repeat` separately measures the reset states used by S02 and S03. All measurements use synthetic data on this 4-core Codespace; there is no fixed-latency or cold-cache claim.

A prior native-volume enlargement failed while retaining filesystem reserve. Only obsolete derived comparison/close tables were released; source backup, installed database/runtime and audit decisions were preserved. Normalisation commits each replacement promptly. Workspace reserve remains at least 6 GB.

## S03 replay comparison baseline

Same-day replay: 31.572s core, 8.666s scoring/validation and 40.244s total; explicit reset cost 8.115s before the timer. Run `7247c9be-693b-4e4f-a02c-6ff3ef9bb885`. This is separate from the first-arrival close above. Fresh footage and actual overhead remain pending.
