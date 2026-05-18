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

            # Иногда после кика/редеплоя Discord оставляет zombie voice state:
            # бот визуально был в канале, но Wavelink уже не дождался VOICE_SERVER_UPDATE.
            # Если клиент выглядит мертвым, аккуратно чистим его и подключаемся заново.
            try:
                is_connected = player.is_connected() if hasattr(player, "is_connected") else True
            except Exception:
                is_connected = True

            if not is_connected:
                try:
                    await player.disconnect(force=True)
                except TypeError:
                    await player.disconnect()
                except Exception:
                    pass
                current_client = None
            else:
                if getattr(player, "channel", None) and player.channel.id != target_channel.id:
                    # One bot cannot play in two channels of the same server simultaneously.
                    raise RuntimeError(
                        f"Бот уже используется в голосовом канале: {player.channel.mention}. "
                        f"Останови музыку там или зайди в тот же канал."
                    )
                return player  # type: ignore[return-value]

        # Важные параметры для Railway/Discord Voice:
        # - timeout увеличен до 75 секунд, потому что 30 секунд часто не хватает после redeploy;
        # - reconnect=True разрешает библиотеке добить voice-handshake;
        # - self_deaf=True снижает лишнюю voice-нагрузку и не требует слушать канал.
        player: wavelink.Player = await target_channel.connect(
            cls=wavelink.Player,
            timeout=75.0,
            reconnect=True,
            self_deaf=True,
        )  # type: ignore[assignment]
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

    def _is_url(self, query: str) -> bool:
        return query.startswith(("http://", "https://"))

    def _is_youtube_url(self, query: str) -> bool:
        q = query.lower()
        return "youtube.com" in q or "youtu.be" in q

    def _youtube_url_variants(self, query: str) -> list[str]:
        """Return safer YouTube URL variants.

        YouTube links with playlist params often fail harder in Lavalink, for example:
        https://youtu.be/v2AC41dglnM?list=RDv2AC41dglnM

        We try the clean video URL as well.
        """
        from urllib.parse import parse_qs, urlparse

        variants = [query]
        try:
            parsed = urlparse(query)
            host = parsed.netloc.lower()
            video_id = ""

            if "youtu.be" in host:
                video_id = parsed.path.strip("/").split("/")[0]
            elif "youtube.com" in host:
                qs = parse_qs(parsed.query)
                video_id = (qs.get("v") or [""])[0]

            if video_id:
                variants.append(f"https://www.youtube.com/watch?v={video_id}")
                variants.append(f"https://youtu.be/{video_id}")
        except Exception:
            pass

        # Deduplicate while keeping order.
        out: list[str] = []
        seen: set[str] = set()
        for item in variants:
            if item and item not in seen:
                out.append(item)
                seen.add(item)
        return out

    def _strip_known_prefix(self, query: str) -> str:
        lowered = query.lower()
        for prefix in ("scsearch:", "ytsearch:", "ytmsearch:"):
            if lowered.startswith(prefix):
                return query[len(prefix):].strip()
        return query.strip()

    async def _search_raw(self, query: str):
        result = await wavelink.Playable.search(query)
        return self._normalize_search_result(result)

    async def _search_prefixed(self, prefix: str, query: str):
        query = self._strip_known_prefix(query)
        if not query:
            return []
        return await self._search_raw(f"{prefix}:{query}")

    async def search_tracks(self, query: str):
        query = query.strip()
        if not query:
            return []

        # URLs are resolved directly. For YouTube we try clean URL variants because
        # links with playlist/list params often fail in Lavalink/youtube-source.
        if self._is_url(query):
            url_variants = self._youtube_url_variants(query) if self._is_youtube_url(query) else [query]
            last_exc: Optional[Exception] = None

            for url in url_variants:
                try:
                    tracks = await self._search_raw(url)
                    if tracks:
                        return tracks
                except Exception as exc:
                    last_exc = exc
                    log.warning("Direct URL load failed for %s: %s", url, exc, exc_info=True)

            # Do not try fake SoundCloud search by video id: it gives garbage results.
            # The user should use a track title if YouTube direct loading is blocked.
            if last_exc:
                raise last_exc
            return []

        # Explicit user prefixes are supported.
        lowered = query.lower()
        if lowered.startswith("scsearch:"):
            return await self._search_prefixed("scsearch", query)
        if lowered.startswith("ytsearch:"):
            return await self._search_prefixed("ytsearch", query)
        if lowered.startswith("ytmsearch:"):
            return await self._search_prefixed("ytmsearch", query)

        # SoundCloud-first for stability. YouTube is fallback only.
        searches = [
            ("SoundCloud", "scsearch"),
            ("YouTube", "ytsearch"),
            ("YouTubeMusic", "ytmsearch"),
        ]

        last_exc: Optional[Exception] = None
        for source_name, prefix in searches:
            try:
                tracks = await self._search_prefixed(prefix, query)
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
        # Сначала ищем трек, потом подключаемся к voice.
        # Так бот не прыгает в канал и обратно, если YouTube/SoundCloud не отдали трек.
        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
            return None, "NO_PLAYER"

        tracks = await self.search_tracks(query)
        if not tracks:
            return None, "NO_TRACKS"

        player = await self.get_or_connect_player(interaction)
        if player is None:
            return None, "NO_PLAYER"

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
