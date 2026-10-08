# Reproduction review

A new local clone of the committed repository was created with `git clone --no-hardlinks`. The four `MILAAN_*` schemas were rebuilt from scratch. Source CSVs and measured benchmark reports in the original checkout were retained.

The clean checkout ran these documented targets successfully:

```bash
make setup data load recon explain lint test
```

The seeded generator created 1,000,000 source records. Bulk imports, all seven matching passes, SQL scoring and database-generated explanations completed. The fresh-schema run took 16.083 seconds for reconciliation and measured 100% precision and 100% recall against its synthetic ground truth. These are observations from that run, not a performance guarantee.

The dashboard from that checkout was started on a separate local port. Browser verification confirmed that the daily close displayed the reconciled million-record dataset without a view error. Ruff passed and all 24 non-database tests passed. Separately, all five database integration tests passed, including conflict detection, run-linked decision auditing, batch evidence, repeatability and false-link scoring.

This was a clean source checkout and a fresh-schema test on the existing Exasol Personal deployment. It reused the installed, pinned Python environment to keep the 32 GB Codespace disk above Exasol's free-space threshold. It does not constitute a new-container dependency installation test. A fresh Codespace, hosted GitHub Actions, macOS and WSL installation remain to be checked after publication. The Linux environment and nested-container deployment details are recorded in [environment.md](environment.md).

The attempted backup of earlier synthetic audit rows exported field names instead of values, so those earlier rows were not recoverable. The export procedure was corrected. A new audit history is generated and verified by subsequent test and demonstration runs. The existing 10-million-record source dataset was reloaded for the submission recording.
