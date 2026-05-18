from __future__ import annotations

import logging

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from .constants import MUSIC_MAX_VOLUME
from .embeds import error_embed, now_playing_embed, ok_embed, queue_embed, warn_embed
from .services import MusicService
from .views import MusicControlView

log = logging.getLogger(__name__)


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = MusicService(bot)

    async def cog_load(self) -> None:
        self.bot.add_view(MusicControlView())
        await self.service.start()

    async def cog_unload(self) -> None:
        await self.service.stop()

    music = app_commands.Group(name="music", description="Музыкальная система")

    @music.command(name="panel", description="Создать панель управления музыкой")
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎵 Музыкальная система",
            description=(
                "Управление музыкой через кнопки ниже.\n\n"
                "Команды:\n"
                "`/music play` — включить или добавить трек\n"
                "`/music queue` — показать очередь\n"
                "`/music now` — текущий трек\n"
                "`/music volume` — громкость\n\n"
                "Важно: один Discord-бот может играть только в одном голосовом канале сервера одновременно."
            ),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=MusicControlView())

    @music.command(name="status", description="Проверить статус музыкального сервера")
    async def status(self, interaction: discord.Interaction):
        online = await self.service.ensure_online()
        if online:
            await interaction.response.send_message(embed=ok_embed("Lavalink доступен", "Музыкальная система готова."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed("Lavalink недоступен", "Бот попробует переподключиться автоматически."), ephemeral=True)

    @music.command(name="play", description="Включить трек или добавить его в очередь")
    @app_commands.describe(query="Название трека или ссылка")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        try:
            result = await self.service.play_or_queue(interaction, query)
        except RuntimeError as exc:
            await interaction.followup.send(embed=warn_embed("Канал уже занят", str(exc)), ephemeral=True)
            return
        except Exception as exc:
            log.warning("/music play failed: %s", exc, exc_info=True)
            await interaction.followup.send(embed=error_embed("Ошибка музыки", "Не удалось найти или запустить трек. Проверь Lavalink и источник."), ephemeral=True)
            return

        if not result or result[0] is None:
            await interaction.followup.send(embed=warn_embed("Зайди в голосовой канал", "Перед запуском музыки нужно быть в voice-канале."), ephemeral=True)
            return

        player, status, *rest = result
        if status == "NO_TRACKS":
            await interaction.followup.send(embed=warn_embed("Ничего не найдено", "Попробуй другое название или прямую ссылку."), ephemeral=True)
            return

        track = rest[0] if rest else None
        if status == "QUEUED":
            await interaction.followup.send(embed=ok_embed("Добавлено в очередь", getattr(track, "title", "Трек добавлен")))
        else:
            await interaction.followup.send(embed=now_playing_embed(track, interaction.user), view=MusicControlView())

    @music.command(name="pause", description="Поставить музыку на паузу")
    async def pause(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет"), ephemeral=True)
            return
        await player.pause(True)
        await interaction.response.send_message(embed=ok_embed("Пауза включена"), ephemeral=True)

    @music.command(name="resume", description="Продолжить музыку")
    async def resume(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет"), ephemeral=True)
            return
        await player.pause(False)
        await interaction.response.send_message(embed=ok_embed("Продолжаю"), ephemeral=True)

    @music.command(name="skip", description="Пропустить текущий трек")
    async def skip(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет"), ephemeral=True)
            return
        await player.skip(force=True)
        await interaction.response.send_message(embed=ok_embed("Трек пропущен"), ephemeral=True)

    @music.command(name="stop", description="Остановить музыку и очистить очередь")
    async def stop(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет"), ephemeral=True)
            return
        try:
            player.queue.clear()
        except Exception:
            pass
        await player.disconnect()
        await interaction.response.send_message(embed=ok_embed("Музыка остановлена", "Очередь очищена."))

    @music.command(name="queue", description="Показать очередь")
    async def queue(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Очередь пуста", "Бот не подключен к голосовому каналу."), ephemeral=True)
            return
        await interaction.response.send_message(embed=queue_embed(player), ephemeral=True)

    @music.command(name="now", description="Показать текущий трек")
    async def now(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player or not getattr(player, "current", None):
            await interaction.response.send_message(embed=warn_embed("Сейчас ничего не играет"), ephemeral=True)
            return
        await interaction.response.send_message(embed=now_playing_embed(player.current), ephemeral=True)

    @music.command(name="volume", description="Изменить громкость")
    @app_commands.describe(value=f"Громкость от 1 до {MUSIC_MAX_VOLUME}")
    async def volume(self, interaction: discord.Interaction, value: app_commands.Range[int, 1, MUSIC_MAX_VOLUME]):
        player = interaction.guild.voice_client if interaction.guild else None
        if not player:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет"), ephemeral=True)
            return
        await player.set_volume(value)
        await interaction.response.send_message(embed=ok_embed("Громкость изменена", f"Текущая громкость: `{value}%`"), ephemeral=True)

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
            else:
                # Do not disconnect instantly; keep connection for next command.
                pass
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
