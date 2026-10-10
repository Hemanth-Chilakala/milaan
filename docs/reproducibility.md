# Reproducibility review

## Fresh checkout and deployment

On 10 October 2026, a clean source checkout was created with `git clone
--no-hardlinks` from the local repository. It installed a new Python 3.12 virtual
environment from `requirements-dev.txt`, including the separate runtime lock.
A new Exasol Personal deployment directory and database port were used. Only
already downloaded container images were reused. The retained 10M deployment
was stopped during this test and its schemas and source data were preserved.

The README path was exercised:

```bash
ACCEPT_EXASOL_EULA=yes make bootstrap
make demo
```

For this isolated same-host test, `EXASOL_DEPLOYMENT_DIR` selected the new
scratch deployment, `EXASOL_PORT=8564` avoided the demo port and
`EXASOL_STORAGE_CONFIG` selected the existing native image store. The normal
quick start needs none of these overrides. Bootstrap installed and activated the
Python SLC, executed `SELECT 1` and the Python `PING()` UDF, pinned the local TLS
certificate, and created `.env` with mode `0600`. A second bootstrap preserved
both the environment file and the completed dataset/run. Without
`ACCEPT_EXASOL_EULA=yes`, bootstrap exited before installation and printed the
EULA link.

The fresh demo generated **1,000,000 source records**, bulk-imported all sources,
normalised in SQL, ran all seven passes, scored against ground truth, generated
explanations in Exasol and started the dashboard. Reconciliation took
**11.699 seconds**, with **100% precision**, **100% recall**, **zero false or
missed links**, and **10,171 exceptions**. This is the observed fresh-deployment
smoke test, distinct from the measured size benchmarks.

Every page passed browser checks at **1920×1080** and **1366×768**, including
visible evidence, local typography and the absence of layout overflow or
Streamlit chrome in presentation mode. Raw results and layout measurements are
in [reproduction_results.json](reproduction_results.json).

The initial fresh install exposed a port argument error: the launcher requires
`db:8564`, rather than a bare `8564`. The wrapper was corrected using the
[official local-port parser](https://github.com/exasol/exasol-personal/blob/main/internal/deploy/local_ports.go).
The incomplete test-only initialisation was preserved separately and the
successful run started with an empty deployment directory. Existing credentials
are never overwritten; install details stay in ignored private logs.

Lint, formatting, all **30 non-database tests** and all **10 database tests**
passed in the clean checkout. The database suite includes the sequential
daily/monthly comparison and Reset/replay checks.

## Container rebuild

The original parent Codespace had no selected devcontainer configuration; its
pre-existing `.devcontainer/devcontainer` file did not have the `.json` name.
A temporary parent `devcontainer.json` uses the project's image, privileged
setting, features, machine requirements and forwarding rules, and calls the
project's post-create script through its `milaan/` subfolder. It leaves the
pre-existing parent file untouched. This allows a rebuild to exercise the
project setup while development remains in its own folder.

The Codespace rebuild completed on **10 October 2026**. The persisted creation
log records the Python 3.12 image build finishing at 09:20:37 UTC, execution of
`bash milaan/.devcontainer/post-create.sh`, and dependency installation completing
at 09:21:59 UTC. The Codespaces post-create report marks every step succeeded.
Python 3.12.15, Podman, crun, the Exasol launcher and runtime/test imports were
verified in the rebuilt container. Lint, formatting and all 30 non-database tests
passed again (2.00 seconds for tests).

The original deployment had been intentionally stopped for the isolated test.
Its first launcher restart returned container exit status 126. Starting the
preserved Nano container directly with the same private storage/runtime
configuration, then retrying the launcher start, restored SQL availability.
The existing TLS-pinned Python connection and `MILAAN_CHECK.PING()` worked;
no credentials or source files were replaced. The retained monthly table still
contains **10,000,000 records** and the completed live snapshot is
`f61ed2ad-b502-4a53-9375-6c0b385421d8`, **81.830 seconds**. Streamlit was restarted
on port 8501. Browser binaries are disposable and were reinstalled after rebuild.

See [rebuild_results.json](rebuild_results.json) for the recovery observations.

## Other platforms

Ubuntu nested-container deployment has been exercised in this Codespace. A
fresh published Codespace, macOS and Windows/WSL installations have not been
independently verified. macOS uses the official launcher workflow rather than
the Linux sudo wrapper. The existing deployment fixes are documented in
[environment.md](environment.md) and README Troubleshooting.

Python packages and synthetic CSVs can be regenerated. Local history, source
changes and private demo preparation should be backed up with the project
folder, including `.git`.
