#!/usr/bin/env bash
set -Eeuo pipefail

# Safely update this checkout from its GitHub main branch.
# Keeps the private bots.json untouched and only restarts an already-running service.

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run this script as root or with sudo."
    echo "Run: ./update.sh"
    exit 1
fi

for command in git sudo; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Required command not found: ${command}"
        exit 1
    fi
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ ! -f main.py || ! -f requirements.txt || ! -d .git ]]; then
    echo "Run this script from the root of the cloned Discord Radio Bots project."
    exit 1
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "${CURRENT_BRANCH}" != "main" ]]; then
    echo "This updater expects the main branch. Current branch: ${CURRENT_BRANCH}"
    exit 1
fi

ORIGIN_URL="$(git remote get-url origin)"
case "${ORIGIN_URL}" in
    https://github.com/913AycltFM/Discord-Radio-Bots.git|https://github.com/913AycltFM/Discord-Radio-Bots|git@github.com:913AycltFM/Discord-Radio-Bots.git)
        ;;
    *)
        echo "The origin remote does not match the expected repository:"
        echo "  https://github.com/913AycltFM/Discord-Radio-Bots"
        echo "Found: ${ORIGIN_URL}"
        exit 1
        ;;
esac

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "Tracked local changes were found. Nothing was updated."
    echo "Commit or back up those changes, then run ./update.sh again."
    exit 1
fi

if [[ ! -x venv/bin/python ]]; then
    echo "Python virtual environment not found. Run ./install.sh first."
    exit 1
fi

if [[ ! -f bots.json ]]; then
    echo "bots.json is missing. Refusing to update this installation."
    exit 1
fi

SERVICE_NAME="discord-radio.service"
SERVICE_WAS_ACTIVE=0
if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
    SERVICE_WAS_ACTIVE=1
fi

echo "Fetching the latest main branch..."
git fetch origin main
git merge --ff-only origin/main

echo "Updating Python dependencies..."
venv/bin/python -m pip install -r requirements.txt

echo "Checking Python syntax..."
venv/bin/python -m compileall -q main.py configure.py

chmod 600 bots.json

if [[ "${SERVICE_WAS_ACTIVE}" -eq 1 ]]; then
    echo "Restarting the previously running service..."
    sudo systemctl restart "${SERVICE_NAME}"
    sudo systemctl is-active --quiet "${SERVICE_NAME}"
    echo "Update complete. discord-radio.service is active."
else
    echo "Update complete. The service was not running, so it was left stopped."
    echo "Start it when ready: sudo systemctl start ${SERVICE_NAME}"
fi
