#!/usr/bin/env bash
set -Eeuo pipefail

# Install dependencies and prepare the Discord Radio Bots systemd service.
# Run this script as the normal Linux user who will own/run the bots.
# It deliberately does NOT start the service until bots.json is configured.

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run this script with sudo or as root."
    echo "Run: ./install.sh"
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required to install system packages and register the service."
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "Cannot identify this Linux distribution (/etc/os-release missing)."
    exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}" in
    ubuntu|debian|raspbian)
        ;;
    *)
        echo "This installer currently supports Ubuntu, Debian, and Raspberry Pi OS."
        echo "Detected: ${PRETTY_NAME:-unknown}"
        exit 1
        ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
CONFIG_FILE="${SCRIPT_DIR}/bots.json"
EXAMPLE_FILE="${SCRIPT_DIR}/bots.example.json"
SERVICE_FILE="/etc/systemd/system/discord-radio.service"
SERVICE_NAME="discord-radio.service"

if [[ ! -f "${SCRIPT_DIR}/main.py" || ! -f "${SCRIPT_DIR}/requirements.txt" ]]; then
    echo "Run this script from a valid Discord Radio Bots project checkout."
    exit 1
fi

if [[ ! -f "${EXAMPLE_FILE}" ]]; then
    echo "Missing bots.example.json. Update your project checkout and try again."
    exit 1
fi

echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y ffmpeg libopus0 python3 python3-venv python3-dev build-essential

PYTHON_BIN="$(command -v python3)"
"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required. Found: " + sys.version.split()[0])
print("Using Python", sys.version.split()[0])
PY

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating Python virtual environment..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

echo "Installing Python dependencies..."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${SCRIPT_DIR}/requirements.txt"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    cp "${EXAMPLE_FILE}" "${CONFIG_FILE}"
    chmod 600 "${CONFIG_FILE}"
    echo "Created private configuration: ${CONFIG_FILE}"
else
    chmod 600 "${CONFIG_FILE}"
    echo "Existing bots.json found; it was preserved."
fi

echo "Installing systemd service..."
sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Discord Radio Bots
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python ${SCRIPT_DIR}/main.py
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo
echo "Installation preparation is complete."
echo
echo "NEXT STEPS:"
echo "  1. Edit your private configuration:"
echo "     nano \"${CONFIG_FILE}\""
echo "  2. Add your Discord bot token(s), voice-channel ID(s), stream URL(s),"
echo "     and now-playing API URL(s). Keep bots.json private."
echo "  3. Start the service after configuration is complete:"
echo "     sudo systemctl enable --now ${SERVICE_NAME}"
echo "  4. Check the service:"
echo "     sudo systemctl status ${SERVICE_NAME} --no-pager"
echo
echo "The service has NOT been started, so placeholder settings cannot connect."
