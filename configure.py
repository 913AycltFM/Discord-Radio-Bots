#!/usr/bin/env python3
"""Interactive, token-safe configuration manager for Discord Radio Bots."""

import getpass
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "bots.json"


def is_placeholder(item: dict) -> bool:
    token = str(item.get("token", ""))
    return not token or token.startswith("PASTE_")


def load_existing() -> list[dict]:
    if not CONFIG_FILE.exists():
        return []
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read bots.json: {exc}")
    if not isinstance(data, list):
        raise SystemExit("bots.json must contain a JSON array.")
    if any(not isinstance(item, dict) for item in data):
        raise SystemExit("Every bots.json entry must be a JSON object.")
    # Ignore untouched public starter entries, but preserve configured bots.
    return [item for item in data if not is_placeholder(item)]


def ask_required(prompt: str, current: str | None = None) -> str:
    while True:
        suffix = f" [{current}]" if current else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if current is not None:
            return current
        print("This field is required.")


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def ask_url(prompt: str, current: str | None = None) -> str:
    while True:
        value = input(f"{prompt}" + (f" [{current}]" if current else "") + ": ").strip()
        if not value and current is not None:
            return current
        if valid_url(value):
            return value
        print("Enter a valid http:// or https:// URL.")


def ask_channel_id(current: int | None = None, adding: bool = False) -> int | None:
    if adding:
        prompt = "Optional default Discord voice channel ID (Enter to skip): "
    else:
        shown = str(current) if current is not None else "not set"
        prompt = (
            f"Default voice channel ID [{shown}] "
            "(Enter keeps it; type 'none' to clear): "
        )
    while True:
        value = input(prompt).strip()
        if not value:
            return None if adding else current
        if not adding and value.lower() in {"none", "clear"}:
            return None
        if value.isdigit() and int(value) > 0:
            return int(value)
        print("Enter a positive channel ID" + (", or leave blank to skip." if adding else ", 'none', or press Enter."))


def collect_new_bot(existing_names: set[str]) -> dict:
    print("\n--- Add a station bot ---")
    while True:
        name = ask_required("Station/bot display name")
        if name not in existing_names:
            break
        print("That name is already configured.")

    while True:
        token = getpass.getpass("Discord bot token (input hidden): ").strip()
        if token and not token.startswith("PASTE_"):
            break
        print("A real Discord bot token is required.")

    stream_url = ask_url("Direct radio stream URL")
    nowplaying_url = ask_url("Now-playing API URL")
    status_text = input(f"Fallback status [{name}]: ").strip() or name
    channel_id = ask_channel_id(adding=True)

    result = {
        "name": name,
        "token": token,
        "stream_url": stream_url,
        "nowplaying_url": nowplaying_url,
        "status_text": status_text,
    }
    if channel_id is not None:
        result["channel_id"] = channel_id
    return result


def edit_bot(bot: dict) -> dict:
    print(f"\nEditing: {bot.get('name', 'Unnamed bot')}")
    edited = dict(bot)
    edited["name"] = ask_required("Station/bot display name", str(bot.get("name", "")))

    token = getpass.getpass("New Discord bot token (Enter keeps current; input hidden): ").strip()
    if token:
        if token.startswith("PASTE_"):
            print("Placeholder token ignored; existing token kept.")
        else:
            edited["token"] = token

    edited["stream_url"] = ask_url("Direct radio stream URL", str(bot.get("stream_url", "")))
    edited["nowplaying_url"] = ask_url("Now-playing API URL", str(bot.get("nowplaying_url", "")))
    edited["status_text"] = input(
        f"Fallback status [{bot.get('status_text') or bot.get('name', '')}]: "
    ).strip() or bot.get("status_text") or bot.get("name", "")

    channel_id = ask_channel_id(bot.get("channel_id"))
    if channel_id is None:
        edited.pop("channel_id", None)
    else:
        edited["channel_id"] = channel_id
    return edited


def choose_bot(configs: list[dict]) -> int | None:
    if not configs:
        print("No configured bots.")
        return None
    for index, bot in enumerate(configs, start=1):
        print(f"  {index}. {bot.get('name', 'Unnamed bot')}")
    while True:
        value = input("Select bot number (Enter to cancel): ").strip()
        if not value:
            return None
        if value.isdigit() and 1 <= int(value) <= len(configs):
            return int(value) - 1
        print("Choose one of the listed numbers.")


def save_config(configs: list[dict]) -> None:
    if not configs:
        raise SystemExit("At least one bot must remain configured; bots.json was not changed.")
    if CONFIG_FILE.exists():
        backup = CONFIG_FILE.with_name("bots.json.backup")
        if not backup.exists():
            shutil.copy2(CONFIG_FILE, backup)
            os.chmod(backup, 0o600)
            print(f"Original configuration backed up to {backup.name}.")

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
    configs = load_existing()
    print("Discord Radio Bots — Configuration Manager")
    print("Tokens are hidden while typing and are never displayed.\n")

    while True:
        print("\nConfigured bots:")
        if configs:
            for index, bot in enumerate(configs, start=1):
                print(f"  {index}. {bot.get('name', 'Unnamed bot')}")
        else:
            print("  No configured bots yet.")
        print("\nChoose an action:")
        print("  1. Add a bot")
        print("  2. Edit a bot")
        print("  3. Remove a bot")
        print("  4. Save and exit")
        choice = input("Selection [1-4]: ").strip()

        if choice == "1":
            names = {str(bot.get("name", "")) for bot in configs}
            configs.append(collect_new_bot(names))
        elif choice == "2":
            index = choose_bot(configs)
            if index is not None:
                edited = edit_bot(configs[index])
                duplicate = any(
                    i != index and bot.get("name") == edited.get("name")
                    for i, bot in enumerate(configs)
                )
                if duplicate:
                    print("That name is already used by another bot; changes discarded.")
                else:
                    configs[index] = edited
                    print("Bot changes staged.")
        elif choice == "3":
            if len(configs) <= 1:
                print("At least one bot must remain configured.")
                continue
            index = choose_bot(configs)
            if index is not None:
                name = configs[index].get("name", "Unnamed bot")
                confirm = input(f"Remove '{name}'? [y/N]: ").strip().lower()
                if confirm in {"y", "yes"}:
                    configs.pop(index)
                    print("Bot removed from the pending configuration.")
        elif choice == "4":
            if not configs:
                print("Add at least one bot before saving.")
                continue
            save_config(configs)
            print(f"\nSaved {len(configs)} bot configuration(s).")
            print("bots.json permissions are set to 600. Keep this file private.")
            print("Restart the service to apply changes:")
            print("  sudo systemctl restart discord-radio.service")
            return 0
        else:
            print("Choose 1, 2, 3, or 4.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Changes were not saved.")
        raise SystemExit(130)
