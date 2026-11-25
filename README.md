# 91.3 Ayclt FM Discord Radio Bots

Four independent Discord bots stream four AzuraCast stations into four Discord voice channels. Each bot can show the current song in its Discord activity and in its voice-channel status.

Designed for **Raspberry Pi 5 (16 GB RAM) running Ubuntu Server 24.04**.

## Features

- Four separate Discord bot accounts, each assigned to one voice channel.
- Live audio from AzuraCast using FFmpeg.
- Now-playing metadata from the AzuraCast `/api/nowplaying/{station_shortcode}` endpoint.
- Updates the bot's Listening activity and the voice-channel status when the track changes.
- Dot commands: `.nowplaying` / `.np`, `.status`, `.reconnect`, and `.help`.
- A background supervisor checks voice connectivity every 15 seconds and reconnects/restarts playback after a disconnect or stream failure.
- systemd service for automatic startup and restart.

## Repository files

| File | Purpose |
| --- | --- |
| `main.py` | Runs all four bots concurrently |
| `bots.example.json` | Safe configuration template; contains no real tokens |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes tokens, local config, and virtual environments |
| `systemd/discord-radio.service.example` | Example systemd unit |

## 1. Create four Discord applications and bots

In the [Discord Developer Portal](https://discord.com/developers/applications), create four separate applications and add a bot to each one.

For each bot:

1. Open **Bot** and generate/reset its token. Store the token privately.
2. Under **Privileged Gateway Intents**, enable **Message Content Intent** so dot commands can read messages.
3. Under **OAuth2 → URL Generator**, select the `bot` scope.
4. Grant the permissions it needs: **View Channels**, **Connect**, **Speak**, and **Manage Channels**. Manage Channels is needed to change the voice-channel status; use the least permissions that work in your server.
5. Open the generated invite URL and add the bot to your Discord server.
6. Enable Developer Mode in Discord, then right-click the assigned voice channel and copy its channel ID.

Keep each bot token private. Never put a real token in a README, issue, screenshot, or committed file.

## 2. Install on Ubuntu Server 24.04

SSH into the Raspberry Pi and run:

```bash
sudo apt update
sudo apt install -y ffmpeg libopus0 python3-venv python3-dev build-essential git

git clone https://github.com/913AycltFM/Discord-Radio-Bots.git
mkdir -p ~/discord-radio
cp -a Discord-Radio-Bots/. ~/discord-radio/
cd ~/discord-radio

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

If you cloned the repository somewhere else, adjust the copy command or use that checkout directory as your working directory.

## 3. Configure the four bots

Create your private configuration file:

```bash
cd ~/discord-radio
cp bots.example.json bots.json
nano bots.json
```

For each entry, fill in:

- `name`: a label for the bot.
- `token`: that bot's Discord token.
- `channel_id`: the numeric ID of the voice channel it should join.
- `stream_url`: the direct AzuraCast listener URL for that station.
- `nowplaying_url`: the matching AzuraCast now-playing API URL.
- `status_text`: fallback text shown when the API has no current track.

The example is configured for 91.3 Ayclt FM, HD2, HD3, and HD4 using the matching station shortcode pattern. Confirm that the HD4 shortcode `91.3_ayclt_fm_hd4` is the actual AzuraCast station shortcode on your server, and verify each listener URL in a browser or media player before running the bots.

Secure the token file:

```bash
chmod 600 ~/discord-radio/bots.json
```

The `.gitignore` excludes `bots.json`; do not force-add it to Git.

## 4. Test manually

```bash
cd ~/discord-radio
./venv/bin/python main.py
```

Confirm that all four bots log in, join their assigned voice channels, play their assigned streams, and update their Listening activity/channel status. Test `.nowplaying`, `.status`, and `.help` in a server text channel. A server manager can also test `.reconnect`. Stop the test with **Ctrl+C**.

If a bot cannot update the voice-channel status, check that it has Manage Channels permission in that server. If it cannot join or play audio, check View Channel, Connect, Speak, the channel ID, the stream URL, and FFmpeg installation.

## 5. Install the systemd service

Use the current Linux username and home directory to create the service. Run this command from your SSH session:

```bash
sudo tee /etc/systemd/system/discord-radio.service > /dev/null <<EOF
[Unit]
Description=Discord 24/7 AzuraCast Radio Bots
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

## 6. Service commands

View status:

```bash
sudo systemctl status discord-radio.service
```

Follow logs:

```bash
sudo journalctl -u discord-radio.service -f
```

Restart after editing `bots.json`:

```bash
sudo systemctl restart discord-radio.service
```

Stop:

```bash
sudo systemctl stop discord-radio.service
```

Start:

```bash
sudo systemctl start discord-radio.service
```

## Configuration and security notes

- This project expects exactly four bot entries in `bots.json`.
- Each bot needs its own Discord application/token and its own voice channel.
- Do not commit `bots.json`. If a token is accidentally exposed, reset it immediately in the Discord Developer Portal.
- The stream URLs must be direct AzuraCast listener URLs, not just the AzuraCast website homepage.
- The bot checks now-playing metadata every 10 seconds. Change `POLL_SECONDS` in `main.py` to adjust this interval.
- The bots are designed to remain in their voice channels continuously while the service, network, and Discord are available. The supervisor retries every 15 seconds; systemd restarts the service after process failure.
- Dot commands require **Message Content Intent** to be enabled for each bot in the Discord Developer Portal.
- `.reconnect` is restricted to members with Manage Server permission.
- This project does not configure Discord applications or create voice channels automatically; those steps are completed in Discord.
