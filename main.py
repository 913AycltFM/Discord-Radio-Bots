import asyncio
import json
import logging
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "bots.private.json"
POLL_SECONDS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("discord-radio")

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
        log.warning("Now-playing request failed for %s: %s", api_url, exc)
        return None


class RadioBot(commands.Bot):
    def __init__(
        self,
        *,
        name: str,
        channel_id: int,
        stream_url: str,
        nowplaying_url: str,
        fallback_status: str,
        **kwargs,
    ):
        super().__init__(command_prefix=commands.when_mentioned, help_command=None, **kwargs)
        self.tree.add_command(discord.app_commands.Command(name='nowplaying', description='Show the currently playing song.', callback=self.nowplaying_slash))
        self.tree.add_command(discord.app_commands.Command(name='status', description='Check this radio bot connection and stream status.', callback=self.status_slash))
        reconnect_command = discord.app_commands.Command(name='reconnect', description='Reconnect this bot to its radio voice channel.', callback=self.reconnect_slash)
        reconnect_command.add_check(discord.app_commands.checks.has_permissions(manage_guild=True))
        self.tree.add_command(reconnect_command)
        self.tree.add_command(discord.app_commands.Command(name='help', description='Show the available radio commands.', callback=self.help_slash))
        self.tree.add_command(discord.app_commands.Command(name='play', description='Start or resume the radio stream.', callback=self.play_slash))
        self.tree.add_command(discord.app_commands.Command(name='pause', description='Pause the radio stream without leaving the voice channel.', callback=self.pause_slash))
        self.tree.add_command(discord.app_commands.Command(name='volume', description='Set the radio volume from 0 to 100 percent.', callback=self.volume_slash))
        self.tree.add_command(discord.app_commands.Command(name='ping', description='Show the bot response latency.', callback=self.ping_slash))
        self.bot_name = name
        self.channel_id = channel_id
        self.stream_url = stream_url
        self.nowplaying_url = nowplaying_url
        self.fallback_status = fallback_status
        self.current_title: str | None = None
        self.volume = 1.0
        self.user_paused = False
        self.metadata_task: asyncio.Task | None = None
        self.connection_task: asyncio.Task | None = None

    def start_stream(self, voice_client: discord.VoiceClient) -> None:
        if (not voice_client.is_connected() or voice_client.is_playing()
                or voice_client.is_paused() or self.user_paused):
            return

        pcm_source = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(pcm_source, volume=self.volume)

        def after_playback(error: Exception | None) -> None:
            if error:
                log.error("[%s] Playback error: %s", self.bot_name, error)
            if voice_client.is_connected() and not self.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.restart_stream(voice_client), self.loop
                )

        voice_client.play(source, after=after_playback)
        log.info("[%s] Streaming %s", self.bot_name, self.stream_url)

    async def restart_stream(self, voice_client: discord.VoiceClient) -> None:
        await asyncio.sleep(3)
        if (voice_client.is_connected() and not voice_client.is_playing()
                and not voice_client.is_paused() and not self.user_paused):
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

                    channel = self.get_channel(self.channel_id)
                    if isinstance(channel, discord.VoiceChannel):
                        try:
                            await channel.edit(status=display_text)
                        except discord.Forbidden:
                            log.error(
                                "[%s] Missing permission to edit voice-channel status",
                                self.bot_name,
                            )
                        except discord.DiscordException:
                            log.exception(
                                "[%s] Could not update voice-channel status",
                                self.bot_name,
                            )

                await asyncio.sleep(POLL_SECONDS)

    async def ensure_connected(self) -> None:
        channel = self.get_channel(self.channel_id)

        if not isinstance(channel, discord.VoiceChannel):
            log.error(
                "[%s] Voice channel %s was not found or is not a voice channel",
                self.bot_name,
                self.channel_id,
            )
            return

        voice_client = discord.utils.get(
            self.voice_clients, guild=channel.guild
        )

        try:
            if not voice_client or not voice_client.is_connected():
                voice_client = await channel.connect(
                    self_deaf=True,
                    reconnect=True,
                )
                log.info("[%s] Connected to %s", self.bot_name, channel.name)

            if not self.user_paused:
                self.start_stream(voice_client)
        except discord.DiscordException:
            log.exception("[%s] Voice connection failed", self.bot_name)

    async def connection_supervisor(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self.ensure_connected()
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
        channel = self.get_channel(self.channel_id)
        voice = (
            discord.utils.get(self.voice_clients, guild=channel.guild)
            if isinstance(channel, discord.VoiceChannel)
            else None
        )
        connected = bool(voice and voice.is_connected())
        playing = bool(voice and voice.is_playing())
        await interaction.response.send_message(
            f"**{self.bot_name}** — Voice: "
            f"{'connected' if connected else 'disconnected'}; stream: "
            f"{'playing' if playing else 'not playing'}."
        )

    async def reconnect_slash(self, interaction: discord.Interaction) -> None:
        channel = self.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message(
                "I cannot find my configured voice channel.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        voice = discord.utils.get(self.voice_clients, guild=channel.guild)
        if voice and voice.is_connected():
            await voice.disconnect(force=True)
        await self.ensure_connected()
        await interaction.followup.send(
            f"Reconnected to **{channel.name}** and restarted the radio stream."
        )

    async def play_slash(self, interaction: discord.Interaction) -> None:
        self.user_paused = False
        channel = self.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("I cannot find my configured voice channel.", ephemeral=True)
            return
        voice = discord.utils.get(self.voice_clients, guild=channel.guild)
        if voice and voice.is_connected() and voice.is_paused():
            voice.resume()
            result = "Resumed the radio stream."
        else:
            await self.ensure_connected()
            result = "Started the radio stream."
        await interaction.response.send_message(result)

    async def pause_slash(self, interaction: discord.Interaction) -> None:
        channel = self.get_channel(self.channel_id)
        voice = (discord.utils.get(self.voice_clients, guild=channel.guild)
                 if isinstance(channel, discord.VoiceChannel) else None)
        if not voice or not voice.is_connected() or not voice.is_playing():
            await interaction.response.send_message("The radio stream is not currently playing.", ephemeral=True)
            return
        self.user_paused = True
        voice.pause()
        await interaction.response.send_message("Paused the radio stream. I will stay in the voice channel.")

    async def volume_slash(self, interaction: discord.Interaction, volume: int) -> None:
        if not 0 <= volume <= 100:
            await interaction.response.send_message("Choose a volume from 0 to 100.", ephemeral=True)
            return
        self.volume = volume / 100
        channel = self.get_channel(self.channel_id)
        voice = (discord.utils.get(self.voice_clients, guild=channel.guild)
                 if isinstance(channel, discord.VoiceChannel) else None)
        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = self.volume
        await interaction.response.send_message(f"Radio volume set to **{volume}%**.")

    async def ping_slash(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.latency * 1000)
        await interaction.response.send_message(f"Pong! Gateway latency: **{latency_ms} ms**.")

    async def help_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "**Radio slash commands**\n"
            "`/nowplaying` — Show the current song.\n"
            "`/status` — Check voice connection and stream playback.\n"
            "`/reconnect` — Reconnect the bot (Manage Server permission required).\n"
            "`/help` — Show this command list.\n"
            "`/play` — Start or resume the stream.\n"
            "`/pause` — Pause audio but stay in the voice channel.\n"
            "`/volume` — Set volume from 0–100%.\n"
            "`/ping` — Show bot latency."
        )

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        if isinstance(error, discord.app_commands.MissingPermissions):
            message = "You need Manage Server permission to use `/reconnect`."
        else:
            log.error("[%s] Slash command error: %s", self.bot_name, error)
            message = "The command failed. Check the bot logs."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    async def on_ready(self) -> None:
        log.info("[%s] Logged in as %s", self.bot_name, self.user)

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
        if self.user and member.id == self.user.id and after.channel is None:
            await asyncio.sleep(3)
            await self.ensure_connected()


async def run_bot(config: dict, intents: discord.Intents) -> None:
    bot = RadioBot(
        name=config["name"],
        channel_id=int(config["channel_id"]),
        stream_url=config["stream_url"],
        nowplaying_url=config["nowplaying_url"],
        fallback_status=config.get("status_text", config["name"]),
        intents=intents,
    )
    await bot.start(config["token"])


async def main() -> None:
    if not CONFIG_FILE.is_file():
        raise SystemExit(
            "Missing bots.private.json. Copy bots.json to bots.private.json and configure it."
        )

    with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
        configs = json.load(config_file)

    if not isinstance(configs, list) or len(configs) != 4:
        raise SystemExit("bots.private.json must contain a JSON array with exactly four bots.")

    required = {"name", "token", "channel_id", "stream_url", "nowplaying_url"}
    for index, config in enumerate(configs, start=1):
        missing = required - config.keys()
        if missing:
            raise SystemExit(
                f"Bot entry {index} is missing: {', '.join(sorted(missing))}"
            )

    intents = discord.Intents.default()
    await asyncio.gather(*(run_bot(config, intents) for config in configs))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
