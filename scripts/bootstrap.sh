#!/usr/bin/env bash
# Install or verify the local deployment without changing existing source data.
set -euo pipefail
eula='https://www.exasol.com/terms-and-conditions/#h-exasol-personal-end-user-license-agreement'
if [ "${ACCEPT_EXASOL_EULA:-}" != yes ]; then
    printf '%s\n' "Review the Exasol Personal EULA: $eula" \
        'After accepting it, run: ACCEPT_EXASOL_EULA=yes make bootstrap' >&2
    exit 2
fi
printf '%s\n' "Exasol Personal EULA accepted via ACCEPT_EXASOL_EULA=yes: $eula"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
deployment_dir="${EXASOL_DEPLOYMENT_DIR:-$PWD/private/exasol-rootful}"
export EXASOL_DEPLOYMENT_DIR="$deployment_dir"

python3.12 - <<'PY'
import os
import shutil
from pathlib import Path

free = shutil.disk_usage(Path.cwd()).free
if free < 6_000_000_000:
    raise SystemExit(f"Need at least 6 GB free in the workspace; available {free / 1e9:.2f} GB.")
memory = int(Path('/proc/meminfo').read_text().split('MemTotal:')[1].split()[0]) * 1024
if (os.cpu_count() or 0) < 4 or memory < 16_000_000_000:
    raise SystemExit('Exasol needs at least 4 CPUs and 16 GB host memory for this setup.')
print(f"Host check: {os.cpu_count()} CPUs, {memory / 2**30:.2f} GiB RAM, {free / 1e9:.2f} GB free.")
PY
bash .devcontainer/post-create.sh
wrapper=(bash scripts/exasol-local.sh)
if sudo test -f "$deployment_dir/deployment.json"; then
    if ! timeout 20 "${wrapper[@]}" connect -c 'SELECT 1' >/dev/null 2>&1; then
        "${wrapper[@]}" start --auto-approve
        if ! timeout 20 "${wrapper[@]}" connect -c 'SELECT 1' >/dev/null 2>&1; then
            "${wrapper[@]}" stop --auto-approve
            "${wrapper[@]}" start --auto-approve
        fi
    fi
else
    "${wrapper[@]}" install local --ports "${EXASOL_PORT:-8563}" --auto-approve
fi
"${wrapper[@]}" slc install python3 --auto-approve
"${wrapper[@]}" connect -f sql/00_feasibility.sql
sudo .venv/bin/python scripts/check_environment.py --deployment-dir "$deployment_dir" --write-env
.venv/bin/python - <<'PY'
from milaan.db import query
assert query('SELECT 1 AS N')[0]['N'] == 1
assert query('SELECT MILAAN_CHECK.PING() AS N')[0]['N'] == 'pong'
print('BOOTSTRAP READY: configured Python connection and Python UDF verified.')
PY
