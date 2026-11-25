# 91.3 Ayclt FM Discord Radio Bots

Four independent Discord bots stream four AzuraCast stations into four Discord voice channels. Each bot can show the current song in its Discord activity and in its voice-channel status.

Designed for **Raspberry Pi 5 (16 GB RAM) running Ubuntu Server 24.04**.

## Features

- Four separate Discord bot accounts, each assigned to one voice channel.
- Live audio from AzuraCast using FFmpeg.
- Now-playing metadata from the AzuraCast `/api/nowplaying/{station_shortcode}` endpoint.
- Updates the bot's Listening activity and the voice-channel status when the track changes.
- Discord slash commands: `/nowplaying`, `/status`, `/reconnect`, `/help`, `/play`, `/pause`, `/volume`, and `/ping`.
- A background supervisor checks voice connectivity every 15 seconds and reconnects/restarts playback after a disconnect or stream failure.
- systemd service for automatic startup and restart.

## Repository files

| File | Purpose |
| --- | --- |
| `main.py` | Runs all four bots concurrently |
| `bots.json` | Public configuration template with placeholder tokens and channel IDs |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes tokens, local config, and virtual environments |
| `systemd/discord-radio.service.example` | Example systemd unit |

## 1. Create four Discord applications and bots

In the [Discord Developer Portal](https://discord.com/developers/applications), create four separate applications and add a bot to each one.

For each bot:

1. Open **Bot** and generate/reset its token. Store the token privately.
2. Under **OAuth2 → URL Generator**, select both the `bot` and `applications.commands` scopes so Discord can install the slash commands.
3. Grant the permissions it needs: **View Channels**, **Connect**, **Speak**, and **Manage Channels**. Manage Channels is needed to change the voice-channel status; use the least permissions that work in your server.
5. Open the generated invite URL and add the bot to your Discord server.

Keep each bot token private. Never put a real token in a README, issue, screenshot, or committed file.

## 2. Get the four Discord voice channel IDs

Each bot needs the ID of the voice channel it should join. You must copy the ID for each of your four voice channels separately.

### Enable Developer Mode

**On desktop:**

1. Open Discord.
2. Click the **User Settings** gear near your username.
3. Select **Advanced**.
4. Turn on **Developer Mode**.

**On Android or iPhone:**

1. Open the Discord app.
2. Tap your profile/avatar to open **You** or **User Settings**.
3. Open **Advanced**.
4. Turn on **Developer Mode**.

### Copy each voice channel ID

1. Return to your Discord server.
2. Find the voice channel for the **91.3 Ayclt FM** bot.
3. **Desktop:** right-click the voice channel name and select **Copy Channel ID**.
4. **Mobile:** long-press the voice channel name and select **Copy Channel ID**. Depending on your Discord app version, you may need to open the channel's options menu first.
5. Paste the copied ID temporarily into a private note.
6. Repeat for the HD2, HD3, and HD4 voice channels.

You should now have four different channel IDs. Do not copy a server ID or a text-channel ID; each value must belong to the voice channel assigned to that bot.

## 3. Install on Ubuntu Server 24.04

SSH into the Raspberry Pi and run:

```bash
sudo apt update
sudo apt install -y ffmpeg libopus0 python3-venv python3-dev build-essential git

git clone https://github.com/913AycltFM/Discord-Radio-Bots.git ~/discord-radio
cd ~/discord-radio

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

The repository is cloned directly into `~/discord-radio`, so no extra folder creation or file-copy step is needed.

## 4. Configure the four bots

Create your private configuration file:

```bash
cd ~/discord-radio
nano bots.json
```

When Nano opens, copy the configuration structure from the public [`bots.json`](https://github.com/913AycltFM/Discord-Radio-Bots/blob/main/bots.json) template and paste it into `bots.json`. Then replace the example bot tokens and channel IDs with your real values. Save with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**.

In `bots.json`, replace each example bot token and channel ID with your real values:

| Configuration entry | What to enter |
| --- | --- |
| First bot | 91.3 Ayclt FM bot token and main station voice channel ID |
| Second bot | HD2 bot token and HD2 voice channel ID |
| Third bot | HD3 bot token and HD3 voice channel ID |
| Fourth bot | HD4 bot token and HD4 voice channel ID |

The `channel_id` value must be the numeric ID you copied in Step 2. Keep it as a number, without quotation marks. For example:

```json
"channel_id": 123456789012345678
```

For each entry, check these fields:

- `name`: the bot's station label.
- `token`: that bot's Discord token.
- `channel_id`: the numeric ID of the voice channel it should join.
- `stream_url`: the direct AzuraCast listener URL for that station.
- `nowplaying_url`: the matching AzuraCast now-playing API URL.
- `status_text`: fallback text shown when the API has no current track.

The example is configured for 91.3 Ayclt FM, HD2, HD3, and HD4 using the matching station shortcode pattern. Confirm that the HD4 shortcode `91.3_ayclt_fm_hd4` is the actual AzuraCast station shortcode on your server, and verify each listener URL in a browser or media player before running the bots.

Save and exit Nano with **Ctrl+O**, press **Enter**, then **Ctrl+X**.

Secure the token file:

```bash
chmod 600 ~/discord-radio/bots.json
```

The GitHub repository is public. Your real `bots.json` configuration must remain only on the Raspberry Pi. Do not commit or push changes to `bots.json` after adding real tokens. The copy in GitHub must remain the placeholder-only template.

## 5. Test manually

```bash
cd ~/discord-radio
./venv/bin/python main.py
```

Confirm that all four bots log in, join their assigned voice channels, play their assigned streams, and update their Listening activity/channel status. In a server text channel, type `/` and select `/nowplaying`, `/status`, `/help`, `/play`, `/pause`, `/volume`, or `/ping` from the Discord command picker. `/volume` requires a number from 0 to 100. A member with Manage Server permission can also run `/reconnect`. `/pause` keeps the bot in the voice channel with audio paused; `/play` resumes or starts playback. The bots sync their slash commands with Discord when they start; global command updates can take a little time to appear. Stop the test with **Ctrl+C**.

If a bot cannot update the voice-channel status, check that it has Manage Channels permission in that server. If it cannot join or play audio, check View Channel, Connect, Speak, the channel ID, the stream URL, and FFmpeg installation.

## 6. Install the systemd service

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

## 7. Service commands

View status:

```bash
sudo systemctl status discord-radio.service
```

Follow logs:

```bash
sudo journalctl -u discord-radio.service -f
```

Restart after editing the private bot configuration:

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

- This project expects exactly four bot entries in the private configuration on the Raspberry Pi.
- Each bot needs its own Discord application/token and its own voice channel.
- Do not commit or push your locally edited bot configuration. If a token is accidentally exposed, reset it immediately in the Discord Developer Portal.
- The stream URLs must be direct AzuraCast listener URLs, not just the AzuraCast website homepage.
- For hosts on the same LAN as AzuraCast, an HTTP listener URL using the server's private LAN address can avoid routing the radio source through the public hostname. Use the correct LAN address for that installation; do not hard-code a private host address into a reusable public template.
- The bot checks now-playing metadata every 10 seconds. Change `POLL_SECONDS` in `main.py` to adjust this interval.
- The bots are designed to remain in their voice channels continuously while the service, network, and Discord are available. The supervisor retries every 15 seconds; systemd restarts the service after process failure.
- Slash commands are registered with Discord when each bot starts. Restart the service if you change the command definitions.
- `/reconnect` is restricted to members with Manage Server permission. Message Content Intent is not required for these slash commands.
- `/volume` controls the PCM audio output, so the bot uses FFmpeg PCM decoding before sending audio to Discord.
- This project does not configure Discord applications or create voice channels automatically; those steps are completed in Discord.

## Operations log

See [the November 25, 2026 operations log](docs/OPERATIONS-2026-11-25.md) for the private-LAN stream source change, service restart verification, UDP receive-buffer troubleshooting, and outstanding DAVE/audio-dropout diagnostics.
