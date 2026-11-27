#!/usr/bin/env bash
set -Eeuo pipefail

# Safely update the checkout without replacing the private local bots.json.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/bots.json"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python"
CONFIG_BACKUP=""
CONFIG_IS_TRACKED=false

restore_config() {
    if [[ -n "${CONFIG_BACKUP}" && -f "${CONFIG_BACKUP}" ]]; then
        cp -p -- "${CONFIG_BACKUP}" "${CONFIG_FILE}"
        chmod 600 "${CONFIG_FILE}"
        rm -f -- "${CONFIG_BACKUP}"
        CONFIG_BACKUP=""
    fi
}

protect_config_from_git() {
    if [[ "${CONFIG_IS_TRACKED}" == true ]]; then
        git -C "${SCRIPT_DIR}" update-index --skip-worktree bots.json || true
    fi
}

cleanup() {
    restore_config
    protect_config_from_git
}
trap cleanup EXIT

if ! git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "This folder is not a Git checkout."
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Python virtual environment not found."
    echo "Run ./install.sh first."
    exit 1
fi

if git -C "${SCRIPT_DIR}" ls-files --error-unmatch bots.json >/dev/null 2>&1; then
    CONFIG_IS_TRACKED=true
fi

if [[ -f "${CONFIG_FILE}" ]]; then
    CONFIG_BACKUP="$(mktemp "${TMPDIR:-/tmp}/discord-radio-bots-config.XXXXXX")"
    chmod 600 "${CONFIG_BACKUP}"
    if ! cp -p -- "${CONFIG_FILE}" "${CONFIG_BACKUP}"; then
        rm -f -- "${CONFIG_BACKUP}"
        CONFIG_BACKUP=""
        echo "Could not back up bots.json; stopping without changing it."
        exit 1
    fi
    echo "Private bots.json safely backed up for the update."
fi

# Clear the local Git protection temporarily, then reset the tracked template
# so a changed public template cannot overwrite the private configuration.
if [[ "${CONFIG_IS_TRACKED}" == true ]]; then
    git -C "${SCRIPT_DIR}" update-index --no-skip-worktree bots.json || true
    git -C "${SCRIPT_DIR}" checkout -- bots.json
fi

echo "Fetching the latest GitHub changes..."
git -C "${SCRIPT_DIR}" pull --ff-only

# Restore the private configuration and hide its local differences from Git.
restore_config
protect_config_from_git
trap - EXIT

echo "Updating Python dependencies..."
"${VENV_PYTHON}" -m pip install -r "${SCRIPT_DIR}/requirements.txt"

echo "Checking Python syntax..."
"${VENV_PYTHON}" -m py_compile "${SCRIPT_DIR}/main.py" "${SCRIPT_DIR}/configure.py"

echo "Restarting Discord Radio Bots..."
sudo systemctl restart discord-radio.service
sudo systemctl --no-pager --full status discord-radio.service

echo
echo "Update complete. Your private bots.json was preserved."
