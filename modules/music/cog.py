from __future__ import annotations

import logging

import discord
import wavelink
from discord.ext import commands

from .embeds import music_center_embed
from .services import MusicService
from .views import MusicControlView

log = logging.getLogger(__name__)


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = MusicService(bot)

    async def cog_load(self) -> None:
        # Persistent buttons after bot restart.
        self.bot.add_view(MusicControlView())
        await self.service.start()

    async def cog_unload(self) -> None:
        await self.service.stop()

    async def start(self) -> None:
        """Create the permanent music center embed automatically.

        Slash commands are intentionally not registered in this cog anymore.
        The music module is controlled only from the embed buttons.
        """
        allowed_channel = getattr(self.bot.settings, "channel_music", 0)
        if not allowed_channel:
            return

        channel = self.bot.get_channel(allowed_channel)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(allowed_channel)
            except Exception as exc:
                log.warning("Could not fetch music channel %s: %s", allowed_channel, exc, exc_info=True)
                return

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        # Keep only one visible music center message from this bot.
        try:
            async for message in channel.history(limit=30):
                if message.author == self.bot.user and message.embeds:
                    title = message.embeds[0].title or ""
                    if "Музыкальный центр" in title:
                        await message.delete()
        except Exception as exc:
            log.warning("Could not cleanup old music center messages: %s", exc, exc_info=True)

        try:
            await channel.send(embed=music_center_embed(), view=MusicControlView())
        except Exception as exc:
            log.warning("Could not send music center panel: %s", exc, exc_info=True)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        self.service.online = True
        log.info("Wavelink node ready: %s", payload.node)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player:
            return
        try:
            if player.queue:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
        except Exception as exc:
            log.warning("Track end handler failed: %s", exc, exc_info=True)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload):
        log.warning("Track exception: %s", payload)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload):
        log.warning("Track stuck: %s", payload)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
