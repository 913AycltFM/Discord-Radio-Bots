#!/usr/bin/env python3
"""Interactive, token-safe configuration wizard for Discord Radio Bots."""

import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "bots.json"
EXAMPLE_TOKEN = "PASTE_YOUR_DISCORD_BOT_TOKEN"


def ask_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("This field is required.")


def ask_url(prompt: str) -> str:
    while True:
        value = ask_required(prompt)
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
        print("Enter a valid http:// or https:// URL.")


def load_existing() -> list[dict]:
    if not CONFIG_FILE.exists():
        return []
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read bots.json: {exc}")
    if not isinstance(data, list):
        raise SystemExit("bots.json must contain a JSON array.")
    # Treat the untouched public example as an empty starter configuration.
    return [
        item for item in data
        if not (
            isinstance(item, dict)
            and item.get("token") == EXAMPLE_TOKEN
        )
    ]


def collect_bot(existing_names: set[str]) -> dict:
    print("\n--- New radio bot ---")
    while True:
        name = ask_required("Station/bot display name: ")
        if name not in existing_names:
            break
        print("That name is already configured. Choose a different name.")

    while True:
        token = getpass.getpass("Discord bot token (input hidden): ").strip()
        if token and token != EXAMPLE_TOKEN:
            break
        print("A real Discord bot token is required.")

    while True:
        channel_text = ask_required("Discord voice-channel ID: ")
        if channel_text.isdigit() and int(channel_text) > 0:
            channel_id = int(channel_text)
            break
        print("Enter the numeric ID of a voice channel.")

    stream_url = ask_url("Direct radio stream URL: ")
    nowplaying_url = ask_url("Now-playing API URL: ")
    status_text = input(f"Fallback status [{name}]: ").strip() or name

    return {
        "name": name,
        "token": token,
        "channel_id": channel_id,
        "stream_url": stream_url,
        "nowplaying_url": nowplaying_url,
        "status_text": status_text,
    }


def save_config(configs: list[dict]) -> None:
    if not configs:
        raise SystemExit("No bot entries were provided; bots.json was not changed.")

    if CONFIG_FILE.exists():
        backup = CONFIG_FILE.with_name("bots.json.backup")
        if not backup.exists():
            shutil.copy2(CONFIG_FILE, backup)
            print(f"Existing configuration backed up to {backup.name}.")

    fd, temporary_name = tempfile.mkstemp(
        prefix="bots.", suffix=".json.tmp", dir=BASE_DIR, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(configs, handle, indent=2)
            handle.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, CONFIG_FILE)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    os.chmod(CONFIG_FILE, 0o600)


def main() -> int:
    print("Discord Radio Bots — Configuration Wizard")
    print("Your bot token is hidden while typing and is never printed.\n")

    configs = load_existing()
    if configs:
        print(f"Found {len(configs)} existing bot configuration(s).")
        print("New entries will be added; existing entries will be preserved.")
    else:
        print("No configured bots found. Let's add your first station.")

    while True:
        names = {item.get("name", "") for item in configs if isinstance(item, dict)}
        configs.append(collect_bot(names))
        answer = input("\nAdd another station/bot? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            break

    save_config(configs)
    print(f"\nSaved {len(configs)} bot configuration(s) to bots.json.")
    print("File permissions set to 600. Keep this file private; never commit it.")
    print("\nNext steps:")
    print("  1. Check the configuration: python3 -m json.tool bots.json")
    print("  2. Start the service: sudo systemctl enable --now discord-radio.service")
    print("  3. Check status: sudo systemctl status discord-radio.service --no-pager")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. No new configuration was saved.")
        raise SystemExit(130)
