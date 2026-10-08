#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

sudo apt-get update
sudo apt-get install -y podman crun uidmap fuse-overlayfs slirp4netns curl ca-certificates python3.12-venv

if ! command -v exasol >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/exasol" ]; then
    installer_path=$(mktemp)
    trap 'rm -f "$installer_path"' EXIT
    curl --fail --location --proto '=https' \
        https://downloads.exasol.com/exasol-personal/installer.sh -o "$installer_path"
    sh "$installer_path"
fi

python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock

printf '%s\n' 'Dependencies installed. Activate with: source .venv/bin/activate' \
    'After accepting the Exasol Personal EULA, run the deployment steps in README.md.'
