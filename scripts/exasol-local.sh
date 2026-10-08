#!/usr/bin/env bash
# Manage the local database using the verified rootful Podman deployment.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
launcher_path="${EXASOL_LAUNCHER:-$HOME/.local/bin/exasol}"
if [ ! -x "$launcher_path" ]; then
    launcher_path="$(command -v exasol)"
fi

if [ "$#" -eq 0 ]; then
    printf '%s\n' 'Usage: bash scripts/exasol-local.sh install local|slc install python3|connect ...|info|start|stop'
    exit 2
fi

# Writable script-language image layers need a native backing filesystem.
# The workspace is ext4; the Codespace's /var/lib path is itself an overlay.
mkdir -p "$project_dir/private"
storage_config="$project_dir/private/podman-storage.conf"
if [ ! -f "$storage_config" ]; then
    printf '%s\n' '[storage]' 'driver = "overlay"' \
        "graphroot = \"$project_dir/private/podman-storage\"" \
        'runroot = "/tmp/milaan-podman-rootful"' > "$storage_config"
fi

exec sudo env "CONTAINERS_STORAGE_CONF=$storage_config" \
    "CONTAINERS_CONF=$project_dir/.devcontainer/containers.conf" "$launcher_path" "$@" \
    --deployment-dir "$project_dir/private/exasol-rootful"
