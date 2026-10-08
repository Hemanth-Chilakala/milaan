# Environment feasibility

Verification date: 8 October 2026. Phase 0 passed.

Observed resources: 4 CPU cores, 16,770,494,464 bytes host RAM, 32 GB workspace
filesystem. The requested 8-core/32-GB environment is not reflected in the
running host. Benchmark reports will use measured specifications.

Installed: Exasol Launcher 2.3.0 and Podman 4.9.3 on Ubuntu 24.04, x86-64.
Python 3.12 is available; the shell's default Python is 3.14, so the project
explicitly uses a Python 3.12 virtual environment.

The restricted command sandbox prevents nested-container operations. Host-side
commands require approved execution outside that sandbox. Rootless `podman info`
succeeded there, with a warning that the root mount is not shared.

| Check | Measured result |
| --- | --- |
| Exasol database | 2026.2.0-nano.3 |
| SQL connection | `SELECT 1` returned `1` |
| Python scalar UDF | `MILAAN_CHECK.PING()` returned `pong` |
| Python client | pyexasol 1.3.0 connected and repeated both checks |
| Transport | TLS with verified SHA-256 certificate fingerprint |
| Local configuration | `.env` created with owner-only permissions; ignored by git |

Reconciliation measurements are recorded separately in [benchmarks.md](benchmarks.md).

## Container failures and fixes

1. Rootless Podman with runc 1.5.1 started Nano with a one-process cgroup limit,
   despite the launcher's `--pids-limit=-1` setting. Startup failed with
   `std::system_error: Resource temporarily unavailable`; client connections
   were reset. An isolated check confirmed `pids.max = 1`.
2. Installing crun 1.14.1 and migrating existing containers with
   `podman system migrate --new-runtime crun` produced `pids.max = max`.
   Exasol then accepted SQL connections.
3. Python SLC activation failed with `Invalid argument` while mounting its
   writable image layer. Both rootless runtimes and rootful Podman failed when
   their storage used the Codespace's overlay root filesystem.
4. The workspace itself uses ext4. `scripts/exasol-local.sh` now selects
   project-local Podman storage in `private/podman-storage`, together with crun
   and netavark. Its backing filesystem is reported as `extfs`. The database
   started, Python UDF execution passed and pyexasol connected on this
   configuration. No launcher or database source changes were required.

The original test deployment directories remain intact. Nothing was destroyed.
The existing Codespace was provisioned directly; a devcontainer rebuild was not
performed. A fresh devcontainer reproducibility test is still required later.

## Working commands

After accepting the EULA, from the project root:

```bash
bash .devcontainer/post-create.sh
bash scripts/exasol-local.sh install local --auto-approve
bash scripts/exasol-local.sh slc install python3 --auto-approve
bash scripts/exasol-local.sh connect -f sql/00_feasibility.sql
sudo .venv/bin/python scripts/check_environment.py --write-env
```

The launcher wrapper uses rootful Podman, crun, netavark and project-local
storage. It does not select the earlier rootless test deployment. The Python
check only bootstraps the certificate over loopback and pins that certificate
for its actual database connection. The password is read from `secrets.json`
and written only to the ignored `.env`; it is never printed.

Stop and restart the verified database with:

```bash
bash scripts/exasol-local.sh stop --auto-approve
bash scripts/exasol-local.sh start --auto-approve
```

## Sources checked

- [Exasol local deployment](https://github.com/exasol/exasol-personal/blob/main/user-docs/content/local-deployment.md)
- [Exasol system requirements](https://github.com/exasol/exasol-personal/blob/main/user-docs/content/system-requirements.md)
- [UDF and script-language installation](https://github.com/exasol/exasol-personal/blob/main/user-docs/content/udfs.md)
- [Exasol connection commands](https://github.com/exasol/exasol-personal/blob/main/user-docs/content/connect.md)
- [Exasol troubleshooting](https://github.com/exasol/exasol-personal/blob/main/user-docs/content/troubleshooting.md)
- [Devcontainer configuration schema](https://github.com/devcontainers/spec/blob/main/schemas/devContainer.base.schema.json)
- [Codespaces machine requirements](https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/configuring-dev-containers/setting-a-minimum-specification-for-codespace-machines)

The current launcher and published documentation both resolve to version 2.3.
Local deployments do not install Python script-language containers by default.
Use `exasol slc install python3` rather than manually registering a container.
