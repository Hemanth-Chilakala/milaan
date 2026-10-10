# Daily close

Daily matching uses persistent open items and new arrivals. Immutable monthly sources are exposed through arrival-filtered views; closed history is retained in append-only link, match and membership tables. Closed gateway batches are removed from matching, while their missing-receipt review items carry forward separately.

## Timings

All observations use the 4-core, 16 GB Codespace with no browser or recorder running. Core time includes arrival preparation, active work sets, all seven passes, open-item maintenance, appended results, progress snapshots and commits. Classification is included. Scoring-oracle maintenance, SQL scoring and full-history validation are separately timed. Total covers both. Namespace initialization, profiling export and connection cleanup follow the stored total; the raw report also records complete call time. Preparation profiling is included in core time.

| 14 Oct 2026 close | Core matching | Scoring and validation | Total |
|---|---:|---:|---:|
| Previous implementation | 47.778 s | 5.669 s | 53.447 s |
| Current implementation | 28.625 s | 9.759 s | 38.390 s |

The current close processes 499,644 new source records plus carried open items. 4,329,564 records have arrived through that date. The **10-second core target was missed**. Total time improved by 28.2%. The prior recorded daily observation was 62.775 s; it is not an unrecorded baseline.

## Consecutive-day replay

| Close | New records | Core | Scoring / validation | Total | Differences from eligible month links |
|---|---:|---:|---:|---:|---:|
| 13 Oct 2026 (catch-up) | 3,829,920 | 67.176 s | 18.990 s | 86.171 s | 0 |
| 14 Oct 2026 | 499,644 | 28.625 s | 9.759 s | 38.390 s | 0 |
| 15 Oct 2026 | 499,462 | 29.397 s | 10.938 s | 40.341 s | 0 |
| 16 Oct 2026 | 498,068 | 28.755 s | 10.752 s | 39.513 s | 0 |

The 13 Oct catch-up prepares prior open items and is not a new-arrivals close. The 14, 15 and 16 Oct results were compared with monthly links whose ledger, bank and optional gateway records had all arrived by each date. Both edge keys and all seven link columns have zero differences. Monthly reconciliation produced 4,384,979 correct links with zero false or missed links in 103.080 s on the new identifiers. This observation is slower than the previous 76.144 s month benchmark; it is not a claim that the month target was achieved.

## Remaining work and limitations

The core budget remains dominated by automatic index maintenance on open-item inserts/deletes, appended membership materialisation, and exception generation. On 14 Oct, source preparation took 7.187 s, active-set/progress setup 3.640 s, result appends 3.428 s, and classification 5.938 s. Six link-producing passes totalled 7.110 s. Full-history scoring and validation remain linear in closed history, but now run outside the timed matching core. A full 30-day 10M replay has not been measured. Later ambiguous or reversing evidence is not used to reopen already closed groups in this task.

Same-date replay removes only that close’s groups and restores opening items; restarting resets the derived daily workspace while retaining monthly sources and audit decisions. First catch-up, same-date replay and migration from old physical daily copies cost more than advancing a day.

An intermediate commit failed when the 5 GiB native storage volume could not enlarge by 4 GiB while retaining its configured filesystem headroom. Obsolete derived results and comparison tables were released; source CSVs, database volumes, installed runtimes and audit decisions were preserved. Loading now commits normalized replacements separately to reclaim old versions promptly. The workspace remained above 6 GB free.

Reproduce with `PYTHONPATH=. .venv/bin/python scripts/benchmark_incremental.py --data data/10000000`. `--reuse-month` replays against the verified retained monthly run. Use `make recon-day DATE=2026-10-14` for a normal close; use `--restart` through the Python module when going back to an earlier date.

All 10 database integration tests and 32 non-database tests passed. The isolated database checks retained the 10M monthly run unchanged; see [integration proof](incremental_database_checks.json).

[Raw current observations and operator profiles](daily_incremental_results.json), [prior profiles](daily_profiles_before.json), [identifier regression checks](identifiers.md).
