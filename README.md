# Discord Radio Bots

Run one or more internet radio stations in Discord voice channels with independent Discord bot accounts. Audio is delivered by FFmpeg, while optional now-playing metadata updates each bot's Discord Listening activity and voice-channel status.

The project is designed for Linux servers, including Raspberry Pi and Ubuntu Server, but can run on other systems that support Python, FFmpeg, and Discord voice connections.

## Features

- Configure **one or more radio bots**; there is no fixed four-bot limit in the application.
- Give each bot its own Discord application, token, and radio stream.
- Play direct AzuraCast or other compatible HTTP audio stream URLs through FFmpeg.
- Read now-playing information from an AzuraCast-compatible JSON API.
- Update the bot's Listening activity and voice-channel status when the track changes.
- Support for the same bot to play in multiple Discord servers at the same time, with independent voice connections and per-server playback controls.
- Slash commands: `/join`, `/leave`, `/nowplaying`, `/status`, `/reconnect`, `/help`, `/play`, `/pause`, `/volume`, and `/ping`.
- Automatically supervise voice connections and restart playback after disconnects or stream failures.
- Run continuously with systemd and start automatically after reboot.

> Each configured bot needs its own Discord bot application/token. Add only as many bot entries as your host and Discord server can reasonably support.

## How it works

Each object in `bots.json` starts one independent public Discord radio bot. By default, it stays disconnected from voice channels after startup. Invite it to any Discord server, join the voice channel where you want the station to play, and run `/join`. You can optionally configure a `channel_id` to have the bot automatically join one default voice channel after startup. The bot can serve multiple Discord servers at the same time, with a separate voice connection and independent pause, volume, and leave controls in each server.

You can configure different stations from the same radio host or stations from different providers. The application does not require AzuraCast specifically for audio playback; the stream URL must be directly playable by FFmpeg. The now-playing endpoint must return the AzuraCast-compatible JSON structure used by this project.

## Requirements

- Linux host (Ubuntu Server or Raspberry Pi OS recommended)
- Python 3.10 or newer
- FFmpeg
- libopus
- A Discord server where you can add bots
- One Discord application/bot per configured station
- Direct audio stream URL for each station
- Now-playing API URL for each station (AzuraCast-compatible)

## 1. Create a Discord bot

For each station you want to broadcast:

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an application and add a bot.
3. Open the **Bot** page and copy/reset its token. Store it privately.
4. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes.
5. Grant the bot the permissions it needs:
   - View Channels
   - Connect
   - Speak
   - Manage Channels (only needed to update voice-channel status)
6. Use the generated invite URL to add the bot to your Discord server.

Repeat these steps for every station/bot. Never publish bot tokens or paste them into screenshots, issues, or public messages. If a token is exposed, reset it immediately in the Developer Portal.

## 2. Choose where the radio plays

By default, the bot does not have a preset home server or voice channel. After inviting it to a Discord server, join the voice channel where you want the station to play and run `/join`. Each server chooses its own voice channel independently. If you configure the optional `channel_id`, the bot will automatically join that default voice channel after startup.

## 3. Install the project

On Ubuntu Server, Debian, or Raspberry Pi OS, install Git and clone the project:

```bash
sudo apt update
sudo apt install -y git

git clone https://github.com/913AycltFM/Discord-Radio-Bots.git ~/discord-radio
cd ~/discord-radio
chmod +x install.sh
./install.sh
```

The installer installs FFmpeg and required system packages, creates the Python virtual environment, installs Python dependencies, sets local permissions on the public placeholder `bots.json`, and installs the systemd service.

**The installer does not start the service.** Configure your private `bots.json` first using the next section, then enable and start the service. This prevents the example placeholder token from being used.

Supported distributions: Ubuntu, Debian, and Raspberry Pi OS. Python 3.10 or newer is required.

## 4. Configure your station bot(s)

**Recommended: use the interactive bot manager.** It lets you add, edit, or remove bot entries. It hides Discord tokens while typing, validates HTTP(S) URLs, preserves existing settings when you press Enter, creates a backup before saving, and restricts `bots.json` to owner-only access:

```bash
cd ~/discord-radio
./venv/bin/python configure.py
```

Follow the prompts for each station. Choose whether to add another bot when asked. The manager does not start or restart the service. After saving changes, restart the service to apply them:

You can also edit the configuration manually if you prefer:

```bash
cd ~/discord-radio
nano bots.json
```

The repository includes a public `bots.json` starter template containing fake placeholder values. Run the wizard to replace those placeholders with your private station configuration:

| Field | Value |
| --- | --- |
| `name` | A display name for this station/bot |
| `token` | The bot token from the Discord Developer Portal |
| `stream_url` | Direct audio listener URL for the station |
| `nowplaying_url` | AzuraCast-compatible now-playing API URL |
| `status_text` | Optional fallback text when no track metadata is available |

Example entry:

```json
{
  "name": "My Radio Station",
  "token": "PASTE_YOUR_DISCORD_BOT_TOKEN",
  "stream_url": "https://radio.example.com/listen/station/discord",
  "nowplaying_url": "https://radio.example.com/api/nowplaying/station",
  "status_text": "Live radio"
}
```

To add more stations, copy the complete object, add a comma between objects, and give every bot its own token and stream/API URLs. Keep the whole configuration inside the surrounding JSON array:

```json
[
  {
    "name": "Station One",
    "token": "BOT_TOKEN_ONE",
    "stream_url": "https://radio.example.com/listen/one/discord",
    "nowplaying_url": "https://radio.example.com/api/nowplaying/one",
    "status_text": "Station One"
  },
  {
    "name": "Station Two",
    "token": "BOT_TOKEN_TWO",
    "stream_url": "https://radio.example.com/listen/two/discord",
    "nowplaying_url": "https://radio.example.com/api/nowplaying/two",
    "status_text": "Station Two"
  }
]
```

Use the real listener and API paths supplied by your radio platform. If your AzuraCast server is on the same local network as the bot host, you may use its private LAN address for the stream URL. Do not copy another operator's private IP address or station shortcode.

Save Nano with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**. Protect the private configuration:

```bash
chmod 600 ~/discord-radio/bots.json
```

**Important:** The repository’s committed `bots.json` contains placeholders only. The configuration wizard replaces it locally with your real credentials and sets permissions to `600`. Never commit your edited local `bots.json`, and never publish real tokens. The installer marks the local tracked `bots.json` as Git `skip-worktree` to reduce the chance of accidentally staging private credentials. The updater temporarily clears that flag, safely backs up and restores your private configuration, and reapplies the protection. Keep the backup private too.

After saving the configuration, start the service installed by `install.sh`:

```bash
sudo systemctl enable --now discord-radio.service
sudo systemctl status discord-radio.service --no-pager
```

### Optional default voice channel

You can optionally add a `channel_id` to a bot entry in your private `bots.json`:

```json
{
  "name": "My Radio Station",
  "token": "YOUR_DISCORD_BOT_TOKEN",
  "channel_id": 123456789012345678,
  "stream_url": "https://radio.example.com/listen/station/discord",
  "nowplaying_url": "https://radio.example.com/api/nowplaying/station",
  "status_text": "Live radio"
}
```

Replace the example number with the ID of a voice channel the bot can access. When set, the bot automatically joins that channel after startup. This setting is optional, so the public `bots.json` starter template does not include a `channel_id` property. Add the property only to your private `bots.json` if you want automatic joining. If you omit it or leave the wizard prompt blank, the bot stays disconnected until someone joins a voice channel and runs `/join`. The configured channel must belong to a server where the bot is installed.

## 5. Test the bots

Run the application manually first:

```bash
cd ~/discord-radio
./venv/bin/python main.py
```

Check the terminal for each bot logging in. Bots without a configured `channel_id` remain out of voice until a server member joins a voice channel and runs `/join`. A bot with a configured `channel_id` automatically joins that default channel after startup. Test the slash commands in Discord. `/leave` and `/reconnect` require the Discord **Manage Server** permission; the other listed commands do not have that application-level permission check:

- `/join` — join the voice channel you are currently in and start the configured radio stream. Use this in each additional server.
- `/leave` — leave the voice channel in this server (Manage Server permission required).
- `/nowplaying` — show the current track.
- `/status` — check this server's voice connection and playback.
- `/reconnect` — reconnect the bot to the last selected voice channel (Manage Server permission required).
- `/help` — list available commands.
- `/play` — start or resume playback.
- `/pause` — pause audio while remaining in the channel.
- `/volume` — set volume from 0 to 100 percent.
- `/ping` — show Discord gateway latency.

Stop the manual test with **Ctrl+C** before installing the system service.

## 6. Start the systemd service

The installer has already created the systemd unit. After you have configured and manually tested your bots, enable the service and start it:

```bash
sudo systemctl enable --now discord-radio.service
sudo systemctl status discord-radio.service --no-pager
```

## Update the bot software

After making sure your private configuration is backed up, run the updater from your project checkout:

```bash
cd ~/discord-radio
./update.sh
```

The updater:

1. Makes a private, permission-restricted temporary backup of your local `bots.json`.
2. Temporarily clears the Git `skip-worktree` protection on the tracked starter file, then restores the public template before pulling.
3. Pulls the latest `main` branch using `git pull --ff-only`; it will not create a merge commit.
4. Restores your private `bots.json`, sets its permissions to `600`, and reapplies Git's `skip-worktree` protection.
5. Installs the Python dependencies listed in `requirements.txt`.
6. Checks the syntax of `main.py` and `configure.py`.
7. Restarts `discord-radio.service` and displays its status.

Run this updater from the same project checkout used by the systemd service. It updates the project files in that checkout; it does not migrate the installation to another directory. If the fast-forward-only pull is blocked by local Git changes or a divergent branch, stop and review the Git status rather than forcing the update. Keep your own separate backups of `bots.json`; never commit real tokens or private stream URLs.

The updater is intended for the standard installation created by `install.sh`. It expects the virtual environment at `./venv` and the service name `discord-radio.service`.

## 7. Service commands

Check service status:

```bash
sudo systemctl status discord-radio.service --no-pager
```

Follow live logs:

```bash
sudo journalctl -u discord-radio.service -f
```

Restart all configured bots:

```bash
sudo systemctl restart discord-radio.service
```

Stop all bots:

```bash
sudo systemctl stop discord-radio.service
```

Start all bots:

```bash
sudo systemctl start discord-radio.service
```

## Troubleshooting

- **Bot does not log in:** check its token and confirm the bot has been added to your server.
- **Bot does not join voice:** if no `channel_id` is configured, join a voice channel in the server and run `/join`. If a `channel_id` is configured, verify that it is the correct voice-channel ID and that the bot has View Channel, Connect, and Speak permissions.
- **Bot joins but has no audio:** verify Connect and Speak permissions, confirm the stream URL is directly playable, and check that FFmpeg is installed.
- **Now-playing does not update:** verify the API URL is reachable and returns an AzuraCast-compatible `now_playing.song` object.
- **Voice-channel status does not update:** grant Manage Channels permission. Audio playback can work without this permission.
- **Slash commands are missing:** check that the bot was invited with both `bot` and `applications.commands` scopes, then allow time for Discord to publish newly synced global commands.
- **`/leave` or `/reconnect` is denied:** the user running either command needs the Discord **Manage Server** permission.
- **A token was exposed:** reset it in the Discord Developer Portal and update your private `bots.json`.

## Security

- Never commit `bots.json`, real Discord tokens, or private credentials.
- Keep the public `bots.json` filled only with clearly fake placeholder values.
- Use `chmod 600 bots.json` to restrict local access.
- Avoid sharing logs that contain private stream URLs or credentials.
- Grant each bot only the Discord permissions it needs.

## Contributing

Issues and pull requests are welcome. When reporting a problem, include the operating system, Python version, relevant error messages, and sanitized configuration structure. **Remove bot tokens, private IP addresses, and credential-bearing URLs before posting.**

---

Created and maintained by [913AycltFM](https://github.com/913AycltFM).
