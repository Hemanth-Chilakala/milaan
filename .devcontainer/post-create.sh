#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'This setup supports Linux, including Ubuntu under WSL. macOS is not verified.' >&2
    exit 1
fi
packages=(podman crun netavark uidmap fuse-overlayfs slirp4netns curl ca-certificates)
missing=()
for package in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
done
if [ "${#missing[@]}" -gt 0 ]; then
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
fi
if ! command -v exasol >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/exasol" ]; then
    installer_path=$(mktemp)
    trap 'rm -f "$installer_path"' EXIT
    curl --fail --location --proto '=https' https://downloads.exasol.com/exasol-personal/installer.sh -o "$installer_path"
    sh "$installer_path"
fi
python_path="${MILAAN_PYTHON:-python3.12}"
"$python_path" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"'
if [ ! -x .venv/bin/python ]; then
    if [ -L .venv ]; then rm .venv; fi
    if [ "${CODESPACES:-false}" = true ]; then
        # Recreate disposable packages outside the 32 GB workspace budget.
        venv_path=$(mktemp -d /tmp/milaan-venv.XXXXXX)
        "$python_path" -m venv "$venv_path"
        ln -s "$venv_path" .venv
    else
        "$python_path" -m venv .venv
    fi
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Existing .venv must use Python 3.12"'
.venv/bin/python -m pip install -r requirements-dev.txt
printf '%s\n' 'Dependencies ready. Run: ACCEPT_EXASOL_EULA=yes make bootstrap'
