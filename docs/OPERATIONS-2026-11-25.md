# Operations log — 2026-11-25

This record documents the Discord radio bot host troubleshooting and configuration work completed on November 25, 2026.

## Stream source moved to the private LAN

The four bot stream sources were changed on the Ubuntu host from the public AzuraCast hostname to the AzuraCast server's private LAN address.

Use the following URL pattern in the host's private bot configuration:

| Bot | Listener path |
| --- | --- |
| 91.3 Ayclt FM | `/listen/91.3_ayclt_fm/discord` |
| 91.3 Ayclt FM HD2 | `/listen/91.3_ayclt_fm_hd2/discord` |
| 91.3 Ayclt FM HD3 | `/listen/91.3_ayclt_fm_hd3/discord` |
| 91.3 Ayclt FM HD4 | `/listen/91.3_ayclt_fm_hd4/discord` |

The deployed host uses the private AzuraCast LAN address with **HTTP**, not HTTPS. The main station listener was checked with `curl -I` and returned `HTTP/1.1 200 OK` with `Content-Type: audio/mpeg`.

Do not copy a host-specific private IP into the public configuration template. Replace `<AZURACAST_LAN_IP>` with the correct address for the local network:

```text
http://<AZURACAST_LAN_IP>/listen/91.3_ayclt_fm/discord
http://<AZURACAST_LAN_IP>/listen/91.3_ayclt_fm_hd2/discord
http://<AZURACAST_LAN_IP>/listen/91.3_ayclt_fm_hd3/discord
http://<AZURACAST_LAN_IP>/listen/91.3_ayclt_fm_hd4/discord
```

The change was made only to the deployed host's local bot configuration. **Do not commit the live `bots.json` or any file containing real Discord bot tokens.** Keep secrets in the private host configuration and ensure they remain excluded from Git.

## Service restart and verification

The systemd service was restarted after the URL change:

```bash
sudo systemctl restart discord-radio.service
sudo systemctl status discord-radio.service --no-pager -l
```

At the subsequent status check on November 25, the service was `active (running)`. Its Python process had four FFmpeg child processes, each using the corresponding private-LAN listener URL for the main, HD2, HD3, and HD4 stations. The main bot completed its Discord voice handshake and connected to its voice channel.

This confirms the service and FFmpeg processes launched. It does not, by itself, prove that all Discord voice sessions completed encryption setup or that the audio-dropout problem is resolved.

## Audio dropout investigation

The bots had been experiencing intermittent audio cutouts across the four stations even while the bot status reported that voice was connected and playback was active.

Earlier diagnostics showed UDP receive queues reaching the previous socket receive-buffer limit, with nonzero drop counters. The following runtime kernel settings were then applied:

```bash
sudo sysctl -w net.core.rmem_max=4194304
sudo sysctl -w net.core.rmem_default=1048576
```

These commands change the running kernel settings; they are **not persistent across reboot** unless separately saved in a sysctl configuration file. After restarting the service, socket receive buffers showed a 1 MiB limit and initially zero socket drop counters. Later samples showed receive queues growing, so this adjustment has not yet been confirmed as a fix.

The stream-source move to the private LAN is a separate isolation test: it avoids fetching the radio audio through the public hostname, but Discord voice traffic still travels over the network to Discord's voice servers.

## DAVE / Discord voice diagnostics still to investigate

Immediately after the November 25 service restart, the main bot completed its voice connection. The initial diagnostics also showed DAVE encryption not yet ready. The delayed diagnostics for HD2, HD3, and HD4 reported:

- DAVE session exists.
- Session status was `pending`.
- Session was not ready.
- Encryption was not yet available (`can_encrypt=False`).
- Epoch was `0`, with no pending transitions reported.

These are observations taken shortly after connection; they do not establish the final state after the sessions have had time to initialize. Check later service logs for subsequent DAVE state changes and errors.

Useful safe diagnostics:

```bash
sudo journalctl -u discord-radio.service --since "10 minutes ago" --no-pager -o cat | grep -Ei "Connected to|Streaming http|DAVE|Playback error|ERROR"
sudo systemctl status discord-radio.service --no-pager -l
```

Do not enable Discord voice gateway DEBUG logging or log raw voice WebSocket messages/payload bytes. Those payloads may contain sensitive key material.

## Current follow-up

1. Listen to all four Discord voice channels and determine whether the private-LAN source improves the dropouts.
2. Recheck DAVE delayed diagnostics after the voice sessions have had time to initialize.
3. If audio still cuts out, continue investigating the Discord voice UDP receive path separately from the AzuraCast source path.
4. If the larger receive-buffer settings are desired after reboot, persist them deliberately in a sysctl configuration file and verify the resulting values after reboot.
