# Discord Radio Bots

Run one or more internet radio stations in Discord voice channels with independent Discord bot accounts. Audio is delivered by FFmpeg, while optional now-playing metadata updates each bot's Discord Listening activity and voice-channel status.

The project is designed for Linux servers, including Raspberry Pi and Ubuntu Server, but can run on other systems that support Python, FFmpeg, and Discord voice connections.

## Features

- Configure **one or more radio bots**; there is no fixed four-bot limit in the application.
- Give each bot its own Discord application, token, voice channel, and radio stream.
- Play direct AzuraCast or other compatible HTTP audio stream URLs through FFmpeg.
- Read now-playing information from an AzuraCast-compatible JSON API.
- Update the bot's Listening activity and voice-channel status when the track changes.
- Slash commands: `/nowplaying`, `/status`, `/reconnect`, `/help`, `/play`, `/pause`, `/volume`, and `/ping`.
- Automatically supervise voice connections and restart playback after disconnects or stream failures.
- Run continuously with systemd and start automatically after reboot.

> Each configured bot needs its own Discord bot application/token. Add only as many bot entries as your host and Discord server can reasonably support.

## How it works

Each object in `bots.json` starts one independent Discord bot. A bot joins the configured voice channel, plays its configured stream URL, and checks its now-playing API URL.

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

## 2. Get the Discord voice channel ID

Enable **Developer Mode** in Discord under **User Settings → Advanced**.

Then copy the ID of the voice channel that the bot should join:

- Desktop: right-click the voice channel and choose **Copy Channel ID**.
- Mobile: long-press the voice channel or open its options menu and choose **Copy Channel ID**.

Use the voice-channel ID, not the server ID or a text-channel ID. Repeat for each bot. Each bot should be assigned to the voice channel where that station should play.

## 3. Install the project

On Ubuntu Server or another Debian-based Linux system:

```bash
sudo apt update
sudo apt install -y ffmpeg libopus0 python3-venv python3-dev build-essential git

git clone https://github.com/913AycltFM/Discord-Radio-Bots.git ~/discord-radio
cd ~/discord-radio

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

## 4. Configure your station bot(s)

Copy the example configuration to a private local file:

```bash
cd ~/discord-radio
cp bots.example.json bots.json
nano bots.json
```

The example contains one placeholder bot. Replace its values with your own:

| Field | Value |
| --- | --- |
| `name` | A display name for this station/bot |
| `token` | The bot token from the Discord Developer Portal |
| `channel_id` | Numeric ID of the Discord voice channel |
| `stream_url` | Direct audio listener URL for the station |
| `nowplaying_url` | AzuraCast-compatible now-playing API URL |
| `status_text` | Optional fallback text when no track metadata is available |

Example entry:

```json
{
  "name": "My Radio Station",
  "token": "PASTE_YOUR_DISCORD_BOT_TOKEN",
  "channel_id": 123456789012345678,
  "stream_url": "https://radio.example.com/listen/station/discord",
  "nowplaying_url": "https://radio.example.com/api/nowplaying/station",
  "status_text": "Live radio"
}
```

To add more stations, copy the complete object, add a comma between objects, and give every bot its own token and voice-channel ID. Keep the whole configuration inside the surrounding JSON array:

```json
[
  {
    "name": "Station One",
    "token": "BOT_TOKEN_ONE",
    "channel_id": 123456789012345678,
    "stream_url": "https://radio.example.com/listen/one/discord",
    "nowplaying_url": "https://radio.example.com/api/nowplaying/one",
    "status_text": "Station One"
  },
  {
    "name": "Station Two",
    "token": "BOT_TOKEN_TWO",
    "channel_id": 234567890123456789,
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

**Important:** `bots.json` contains live credentials and is excluded from Git by `.gitignore`. Do not force-add it or commit real tokens. Keep `bots.example.json` as the public placeholder template.

## 5. Test the bots

Run the application manually first:

```bash
cd ~/discord-radio
./venv/bin/python main.py
```

Check the terminal for each bot logging in, connecting to its configured voice channel, and starting playback. Test the slash commands in Discord:

- `/nowplaying` — show the current track.
- `/status` — check voice connection and playback.
- `/reconnect` — reconnect the bot (Manage Server permission required).
- `/help` — list available commands.
- `/play` — start or resume playback.
- `/pause` — pause audio while remaining in the channel.
- `/volume` — set volume from 0 to 100 percent.
- `/ping` — show Discord gateway latency.

Stop the manual test with **Ctrl+C** before installing the system service.

## 6. Run continuously with systemd

Create the service using your current Linux username and home directory:

```bash
sudo tee /etc/systemd/system/discord-radio.service > /dev/null <<EOF
[Unit]
Description=Discord Radio Bots
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/discord-radio
ExecStart=$HOME/discord-radio/venv/bin/python $HOME/discord-radio/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now discord-radio.service
```

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
- **Bot cannot find its channel:** verify `channel_id` is the numeric ID of a voice channel in the server.
- **Bot joins but has no audio:** verify Connect and Speak permissions, confirm the stream URL is directly playable, and check that FFmpeg is installed.
- **Now-playing does not update:** verify the API URL is reachable and returns an AzuraCast-compatible `now_playing.song` object.
- **Voice-channel status does not update:** grant Manage Channels permission. Audio playback can work without this permission.
- **Slash commands are missing:** check the bot invite scopes and allow time for Discord to publish newly synced global commands.
- **A token was exposed:** reset it in the Discord Developer Portal and update your private `bots.json`.

## Security

- Never commit `bots.json`, real Discord tokens, or private credentials.
- Keep the public `bots.example.json` filled only with clearly fake placeholder values.
- Use `chmod 600 bots.json` to restrict local access.
- Avoid sharing logs that contain private stream URLs or credentials.
- Grant each bot only the Discord permissions it needs.

## Contributing

Issues and pull requests are welcome. When reporting a problem, include the operating system, Python version, relevant error messages, and sanitized configuration structure. **Remove bot tokens, private IP addresses, and credential-bearing URLs before posting.**

---

Created and maintained by [913AycltFM](https://github.com/913AycltFM).
