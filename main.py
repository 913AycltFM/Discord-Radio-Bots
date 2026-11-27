import asyncio
import json
import logging
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "bots.json"
POLL_SECONDS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("discord-radio")

async def require_manage_guild(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_guild
    )


# PCM audio must be encoded with Opus before it can be sent to Discord voice.
try:
    discord.opus.load_opus("libopus.so.0")
except OSError:
    log.exception("Could not load the Opus library")
    raise

if not discord.opus.is_loaded():
    raise RuntimeError("Opus is required for PCM Discord voice playback but could not be loaded.")

log.info("Opus audio encoder loaded.")

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


async def fetch_now_playing(
    session: aiohttp.ClientSession, api_url: str
) -> str | None:
    try:
        async with session.get(api_url) as response:
            response.raise_for_status()
            data = await response.json()

        song = data.get("now_playing", {}).get("song", {})
        title = (song.get("title") or "").strip()
        artist = (song.get("artist") or "").strip()

        if artist and title:
            return f"{artist} - {title}"
        return title or song.get("text") or None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
        log.warning("Now-playing request failed (%s)", type(exc).__name__)
        return None


class RadioBot(commands.Bot):
    def __init__(
        self,
        *,
        name: str,
        stream_url: str,
        nowplaying_url: str,
        fallback_status: str,
        channel_id: int | None = None,
        **kwargs,
    ):
        super().__init__(command_prefix=commands.when_mentioned, help_command=None, **kwargs)
        self.tree.add_command(discord.app_commands.Command(name='nowplaying', description='Show the currently playing song.', callback=self.nowplaying_slash))
        self.tree.add_command(discord.app_commands.Command(name='status', description='Check this radio bot connection and stream status.', callback=self.status_slash))
        reconnect_command = discord.app_commands.Command(name='reconnect', description='Reconnect this bot to its radio voice channel.', callback=self.reconnect_slash)
        reconnect_command.add_check(require_manage_guild)
        self.tree.add_command(reconnect_command)
        self.tree.add_command(discord.app_commands.Command(name='help', description='Show the available radio commands.', callback=self.help_slash))
        self.tree.add_command(discord.app_commands.Command(name='join', description='Join your current voice channel and start the radio.', callback=self.join_slash))
        leave_command = discord.app_commands.Command(name='leave', description='Leave the voice channel in this server.', callback=self.leave_slash)
        leave_command.add_check(require_manage_guild)
        self.tree.add_command(leave_command)
        self.tree.add_command(discord.app_commands.Command(name='play', description='Start or resume the radio stream in this server.', callback=self.play_slash))
        self.tree.add_command(discord.app_commands.Command(name='pause', description='Pause the radio stream without leaving the voice channel.', callback=self.pause_slash))
        self.tree.add_command(discord.app_commands.Command(name='volume', description='Set the radio volume from 0 to 200 percent.', callback=self.volume_slash))
        self.tree.add_command(discord.app_commands.Command(name='ping', description='Show the bot response latency.', callback=self.ping_slash))
        self.bot_name = name
        self.stream_url = stream_url
        self.nowplaying_url = nowplaying_url
        self.fallback_status = fallback_status
        self.configured_channel_id = channel_id
        self.current_title: str | None = None
        self.guild_volumes: dict[int, float] = {}
        self.guild_paused: dict[int, bool] = {}
        self.guild_channel_ids: dict[int, int] = {}
        self.guild_opted_out: set[int] = set()
        self.metadata_task: asyncio.Task | None = None
        self.connection_task: asyncio.Task | None = None

    def start_stream(self, voice_client: discord.VoiceClient) -> None:
        guild_id = voice_client.guild.id
        if (not voice_client.is_connected() or voice_client.is_playing()
                or voice_client.is_paused() or self.guild_paused.get(guild_id, False)):
            return

        pcm_source = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(pcm_source, volume=self.guild_volumes.get(guild_id, 1.0))

        def after_playback(error: Exception | None) -> None:
            if error:
                log.error("[%s] Playback process ended with an error: %s", self.bot_name, error)
            else:
                log.warning("[%s] Playback process ended; checking recovery", self.bot_name)

            if voice_client.is_connected() and not self.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.restart_stream(voice_client), self.loop
                )
            else:
                log.warning(
                    "[%s] Playback ended while voice was disconnected; connection supervisor will handle recovery",
                    self.bot_name
                )

        voice_client.play(source, after=after_playback)
        log.info("[%s] Radio stream playback started", self.bot_name)

    async def restart_stream(self, voice_client: discord.VoiceClient) -> None:
        await asyncio.sleep(3)
        if (voice_client.is_connected() and not voice_client.is_playing()
                and not voice_client.is_paused()
                and not self.guild_paused.get(voice_client.guild.id, False)):
            try:
                self.start_stream(voice_client)
            except Exception:
                log.exception("[%s] Could not restart stream", self.bot_name)

    async def metadata_loop(self) -> None:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self.is_closed():
                track = await fetch_now_playing(session, self.nowplaying_url)
                display_text = (track or self.fallback_status)[:128]

                if display_text != self.current_title:
                    self.current_title = display_text
                    log.info("[%s] Now playing: %s", self.bot_name, display_text)

                    try:
                        await self.change_presence(
                            activity=discord.Activity(
                                type=discord.ActivityType.listening,
                                name=display_text,
                            )
                        )
                    except discord.DiscordException:
                        log.exception("[%s] Could not update bot presence", self.bot_name)

                    for channel_id in set(self.guild_channel_ids.values()):
                        channel = self.get_channel(channel_id)
                        if isinstance(channel, discord.VoiceChannel):
                            try:
                                await channel.edit(status=display_text)
                            except discord.Forbidden:
                                log.warning("[%s] Missing permission to edit voice-channel status in guild %s", self.bot_name, channel.guild.id)
                            except discord.DiscordException:
                                log.exception("[%s] Could not update voice-channel status in guild %s", self.bot_name, channel.guild.id)

                await asyncio.sleep(POLL_SECONDS)

    async def ensure_connected(self, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            log.error("[%s] Voice channel %s was not found or is not a voice channel", self.bot_name, channel_id)
            return

        guild_id = channel.guild.id
        self.guild_channel_ids[guild_id] = channel.id
        voice_client = discord.utils.get(self.voice_clients, guild=channel.guild)

        try:
            if voice_client and voice_client.is_connected():
                if voice_client.channel != channel:
                    log.info(
                        "[%s] Moving voice connection in guild %s to %s",
                        self.bot_name, guild_id, channel.name
                    )
                    await voice_client.move_to(channel)
            else:
                if voice_client is not None:
                    log.warning(
                        "[%s] Voice connection lost in guild %s; reconnecting",
                        self.bot_name, guild_id
                    )
                    await voice_client.disconnect(force=True)

                voice_client = await channel.connect(self_deaf=True, reconnect=True)
                log.info(
                    "[%s] Connected to %s in guild %s",
                    self.bot_name, channel.name, guild_id
                )

            if (
                voice_client.is_connected()
                and not voice_client.is_playing()
                and not voice_client.is_paused()
                and not self.guild_paused.get(guild_id, False)
            ):
                log.warning(
                    "[%s] Radio playback is not active in guild %s; restarting stream",
                    self.bot_name, guild_id
                )

            self.start_stream(voice_client)

        except discord.DiscordException:
            log.exception("[%s] Voice connection or playback recovery failed in guild %s", self.bot_name, guild_id)

    async def connection_supervisor(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                channel_ids = set(self.guild_channel_ids.values())
                if self.configured_channel_id is not None:
                    channel_ids.add(self.configured_channel_id)

                for channel_id in channel_ids:
                    channel = self.get_channel(channel_id)
                    if isinstance(channel, discord.VoiceChannel) and channel.guild.id in self.guild_opted_out:
                        continue
                    await self.ensure_connected(channel_id)
            except Exception:
                log.exception('[%s] Voice connection check failed', self.bot_name)
            await asyncio.sleep(15)

    async def setup_hook(self) -> None:
        synced = await self.tree.sync()
        log.info("[%s] Synced %s slash commands", self.bot_name, len(synced))

    async def nowplaying_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"**{self.bot_name}:** {self.current_title or self.fallback_status}"
        )

    async def status_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
        connected = bool(voice and voice.is_connected())
        playing = bool(voice and voice.is_playing())
        await interaction.response.send_message(
            f"**{self.bot_name}** — Voice: "
            f"{'connected' if connected else 'disconnected'}; stream: "
            f"{'playing' if playing else 'not playing'}."
        )

    async def join_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        if not interaction.user.voice or not isinstance(interaction.user.voice.channel, discord.VoiceChannel):
            await interaction.response.send_message("Join a voice channel first, then use `/join`.", ephemeral=True)
            return
        channel = interaction.user.voice.channel
        self.guild_opted_out.discard(interaction.guild.id)
        self.guild_channel_ids[interaction.guild.id] = channel.id
        self.guild_paused[interaction.guild.id] = False
        await interaction.response.defer(ephemeral=True)
        await self.ensure_connected(channel.id)
        await interaction.followup.send(f"Joined **{channel.name}** and started **{self.bot_name}**.")

    async def leave_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return

        # Acknowledge immediately, then edit the original response when finished.
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        try:
            self.guild_opted_out.add(guild_id)
            self.guild_channel_ids.pop(guild_id, None)
            self.guild_paused.pop(guild_id, None)
            self.guild_volumes.pop(guild_id, None)

            voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
            if voice and voice.is_connected():
                await voice.disconnect(force=True)
        except Exception:
            log.exception("[%s] Could not leave voice channel in guild %s", self.bot_name, guild_id)
            message = "I couldn't leave the voice channel. Check the bot logs."
        else:
            message = "I left the voice channel in this server."

        try:
            await interaction.edit_original_response(content=message)
        except discord.HTTPException:
            log.exception("[%s] Could not send the /leave response in guild %s", self.bot_name, guild_id)

    async def reconnect_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        channel_id = self.guild_channel_ids.get(interaction.guild.id)
        if channel_id is None:
            await interaction.response.send_message("Use `/join` first so I know which voice channel to reconnect to.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if voice and voice.is_connected():
            await voice.disconnect(force=True)
        await self.ensure_connected(channel_id)
        await interaction.followup.send("Reconnected and restarted the radio stream.")

    async def play_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_connected():
            await interaction.response.send_message("Use `/join` while in a voice channel first.", ephemeral=True)
            return
        self.guild_paused[interaction.guild.id] = False
        if voice.is_paused():
            voice.resume()
        elif not voice.is_playing():
            self.start_stream(voice)
        await interaction.response.send_message("Radio playback started in this server.")

    async def pause_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_connected() or not voice.is_playing():
            await interaction.response.send_message("The radio stream is not currently playing here.", ephemeral=True)
            return
        self.guild_paused[interaction.guild.id] = True
        voice.pause()
        await interaction.response.send_message("Paused the radio stream in this server.")

    async def volume_slash(self, interaction: discord.Interaction, volume: int) -> None:
        if not 0 <= volume <= 200:
            await interaction.response.send_message("Choose a volume from 0 to 200.", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        self.guild_volumes[interaction.guild.id] = volume / 100
        voice = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume / 100
        await interaction.response.send_message(f"Radio volume in this server set to **{volume}%**.")

    async def ping_slash(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.latency * 1000)
        await interaction.response.send_message(f"Pong! Gateway latency: **{latency_ms} ms**.")

    async def help_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "**Radio slash commands**\n"
            "`/nowplaying` — Show the current song.\n"
            "`/status` — Check this server's voice connection and playback.\n"
            "`/join` — Join your current voice channel and start the radio.\n"
            "`/leave` — Leave the voice channel in this server.\n"
            "`/reconnect` — Reconnect this server's radio connection (Manage Server required).\n"
            "`/help` — Show this command list.\n"
            "`/play` — Start or resume playback in this server.\n"
            "`/pause` — Pause playback in this server.\n"
            "`/volume` — Set this server's volume from 0–200%.\n"
            "`/ping` — Show bot latency."
        )

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        if isinstance(error, (discord.app_commands.MissingPermissions, discord.app_commands.CheckFailure)):
            message = "You need Manage Server permission to use `/leave` and `/reconnect`."
        else:
            log.error("[%s] Slash command error: %s", self.bot_name, error)
            message = "The command failed. Check the bot logs."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    async def on_ready(self) -> None:
        log.info("[%s] Logged in as %s", self.bot_name, self.user)

        # An optional configured channel starts this bot automatically.
        # Without channel_id, the bot stays disconnected until /join is used.
        if self.configured_channel_id is not None:
            channel = self.get_channel(self.configured_channel_id)
            if isinstance(channel, discord.VoiceChannel):
                self.guild_channel_ids[channel.guild.id] = channel.id
            else:
                log.warning(
                    "[%s] Configured channel_id %s was not found or is not a voice channel",
                    self.bot_name,
                    self.configured_channel_id,
                )

        if self.connection_task is None or self.connection_task.done():
            self.connection_task = asyncio.create_task(self.connection_supervisor())

        if self.metadata_task is None or self.metadata_task.done():
            self.metadata_task = asyncio.create_task(self.metadata_loop())

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if (
            self.user
            and member.id == self.user.id
            and before.channel is not None
            and after.channel is None
        ):
            log.warning(
                "[%s] Discord voice state reports disconnection from %s in guild %s",
                self.bot_name,
                before.channel.name,
                member.guild.id,
            )
            channel_id = self.guild_channel_ids.get(member.guild.id)
            if channel_id is not None:
                await asyncio.sleep(3)
                if (
                    member.guild.id not in self.guild_opted_out
                    and self.guild_channel_ids.get(member.guild.id) == channel_id
                ):
                    await self.ensure_connected(channel_id)


async def run_bot(config: dict, intents: discord.Intents) -> None:
    bot = RadioBot(
        name=config["name"],
        stream_url=config["stream_url"],
        nowplaying_url=config["nowplaying_url"],
        fallback_status=config.get("status_text", config["name"]),
        channel_id=config.get("channel_id"),
        intents=intents,
    )
    await bot.start(config["token"])


async def main() -> None:
    if not CONFIG_FILE.is_file():
        raise SystemExit(
            "Missing bots.json. Create bots.json from the repository template and configure it."
        )

    with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
        configs = json.load(config_file)

    if not isinstance(configs, list) or not configs:
        raise SystemExit("bots.json must contain a JSON array with at least one bot.")

    required = {"name", "token", "stream_url", "nowplaying_url"}
    for index, config in enumerate(configs, start=1):
        if not isinstance(config, dict):
            raise SystemExit(f"Bot entry {index} must be a JSON object.")

        missing = required - config.keys()
        if missing:
            raise SystemExit(
                f"Bot entry {index} is missing: {', '.join(sorted(missing))}"
            )

        for field in ("name", "token", "stream_url", "nowplaying_url"):
            if not isinstance(config[field], str) or not config[field].strip():
                raise SystemExit(
                    f"Bot entry {index} field '{field}' must be a non-empty string."
                )

        channel_id = config.get("channel_id")
        if channel_id is not None and (
            isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id <= 0
        ):
            raise SystemExit(
                f"Bot entry {index} field 'channel_id' must be a positive integer when provided."
            )

    intents = discord.Intents.default()
    await asyncio.gather(*(run_bot(config, intents) for config in configs))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
