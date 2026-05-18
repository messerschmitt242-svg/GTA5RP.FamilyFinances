from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
import wavelink
from discord.ext import commands

from .constants import (
    LAVALINK_HOST,
    LAVALINK_PASSWORD,
    LAVALINK_PORT,
    LAVALINK_SECURE,
    MUSIC_DEFAULT_VOLUME,
    MUSIC_RECONNECT_INTERVAL,
)

log = logging.getLogger(__name__)


class MusicService:
    """Safe wrapper around Wavelink/Lavalink.

    Important Discord limitation: one bot account can have only one active voice
    connection per guild. This service supports one independent player per guild.
    For simultaneous playback in 5 voice channels of one guild, run 5 bot accounts.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.online: bool = False
        self.connecting: bool = False
        self._health_task: Optional[asyncio.Task] = None

    @property
    def uri(self) -> str:
        scheme = "https" if LAVALINK_SECURE else "http"
        return f"{scheme}://{LAVALINK_HOST}:{LAVALINK_PORT}"

    async def start(self) -> None:
        await self.connect_node()
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self.health_loop(), name="music-health-loop")

    async def stop(self) -> None:
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()

    async def connect_node(self) -> bool:
        if self.connecting:
            return self.online
        if not LAVALINK_HOST:
            log.warning("LAVALINK_HOST is empty. Music module is offline.")
            self.online = False
            return False

        self.connecting = True
        try:
            node = wavelink.Node(uri=self.uri, password=LAVALINK_PASSWORD)
            await wavelink.Pool.connect(client=self.bot, nodes=[node], cache_capacity=100)
            self.online = True
            log.info("Lavalink connected: %s", self.uri)
            return True
        except Exception as exc:
            self.online = False
            log.warning("Lavalink connect failed: %s", exc, exc_info=True)
            return False
        finally:
            self.connecting = False

    async def health_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(MUSIC_RECONNECT_INTERVAL)
                if not self.online or not self.has_node():
                    log.warning("Music health: Lavalink offline. Trying reconnect...")
                    await self.connect_node()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Music health loop error: %s", exc, exc_info=True)

    def has_node(self) -> bool:
        try:
            return bool(wavelink.Pool.nodes)
        except Exception:
            return False

    async def ensure_online(self) -> bool:
        if self.online and self.has_node():
            return True
        return await self.connect_node()

    async def get_or_connect_player(self, interaction: discord.Interaction) -> Optional[wavelink.Player]:
        if not await self.ensure_online():
            return None

        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
            return None

        guild = interaction.guild
        if guild is None:
            return None

        current_client = guild.voice_client
        target_channel = user.voice.channel

        if current_client:
            player = current_client  # type: ignore[assignment]
            if getattr(player, "channel", None) and player.channel.id != target_channel.id:
                # One bot cannot play in two channels of the same server simultaneously.
                raise RuntimeError(
                    f"Бот уже используется в голосовом канале: {player.channel.mention}. "
                    f"Останови музыку там или зайди в тот же канал."
                )
            return player  # type: ignore[return-value]

        player: wavelink.Player = await target_channel.connect(cls=wavelink.Player)  # type: ignore[assignment]
        try:
            await player.set_volume(MUSIC_DEFAULT_VOLUME)
        except Exception:
            pass
        return player

    def _normalize_search_result(self, result):
        """Wavelink can return either a list of tracks or a Playlist object."""
        if not result:
            return []

        tracks = getattr(result, "tracks", None)
        if tracks:
            return list(tracks)

        try:
            return list(result)
        except TypeError:
            return [result]

    def _track_source(self, name: str):
        """Return Wavelink TrackSource enum when available, otherwise prefix string."""
        source_enum = getattr(wavelink, "TrackSource", None)
        if source_enum is not None:
            value = getattr(source_enum, name, None)
            if value is not None:
                return value

        fallback = {
            "SoundCloud": "scsearch",
            "YouTube": "ytsearch",
            "YouTubeMusic": "ytmsearch",
        }
        return fallback.get(name)

    async def _search_one(self, query: str, source):
        """Search with Wavelink 3 source API. Falls back to old prefix style if needed."""
        if source is None:
            result = await wavelink.Playable.search(query, source=None)
            return self._normalize_search_result(result)

        try:
            result = await wavelink.Playable.search(query, source=source)
            return self._normalize_search_result(result)
        except TypeError:
            # Compatibility fallback for older Wavelink signatures.
            prefix = str(source).strip(":")
            result = await wavelink.Playable.search(f"{prefix}:{query}")
            return self._normalize_search_result(result)

    async def search_tracks(self, query: str):
        query = query.strip()
        if not query:
            return []

        # URLs must be resolved directly without adding search prefixes.
        if query.startswith(("http://", "https://")):
            try:
                return await self._search_one(query, None)
            except Exception as exc:
                log.warning("Direct URL load failed for %s: %s", query, exc, exc_info=True)
                raise

        # SoundCloud-first for stability, then YouTube, then YouTube Music.
        sources = [
            ("SoundCloud", self._track_source("SoundCloud")),
            ("YouTube", self._track_source("YouTube")),
            ("YouTubeMusic", self._track_source("YouTubeMusic")),
        ]

        last_exc: Optional[Exception] = None
        for source_name, source in sources:
            if source is None:
                continue
            try:
                tracks = await self._search_one(query, source)
                if tracks:
                    log.info("Music search success: source=%s query=%s results=%s", source_name, query, len(tracks))
                    return tracks
            except Exception as exc:
                last_exc = exc
                log.warning("Music search failed: source=%s query=%s error=%s", source_name, query, exc, exc_info=True)

        if last_exc:
            raise last_exc
        return []

    async def play_or_queue(self, interaction: discord.Interaction, query: str):
        player = await self.get_or_connect_player(interaction)
        if player is None:
            return None, "NO_PLAYER"

        tracks = await self.search_tracks(query)
        if not tracks:
            return player, "NO_TRACKS"

        track = tracks[0]
        try:
            track.extras = {"requester_id": interaction.user.id}
        except Exception:
            pass

        if player.playing or player.paused:
            await player.queue.put_wait(track)
            return player, "QUEUED", track

        await player.play(track)
        return player, "PLAYING", track

    async def cleanup_player(self, player: wavelink.Player) -> None:
        try:
            player.queue.clear()
        except Exception:
            pass
        try:
            await player.stop()
        except Exception:
            pass
        try:
            await player.disconnect()
        except Exception:
            pass
