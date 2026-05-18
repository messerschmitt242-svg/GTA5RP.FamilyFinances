from __future__ import annotations

from urllib.parse import urlparse

import discord

from .constants import EMOJI_PAUSE, EMOJI_PLAY, EMOJI_QUEUE, EMOJI_SKIP, EMOJI_STOP
from .embeds import error_embed, now_playing_embed, ok_embed, queue_embed, warn_embed


def _service(interaction: discord.Interaction):
    cog = interaction.client.get_cog("MusicCog")
    return getattr(cog, "service", None)


def _is_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class TrackSearchModal(discord.ui.Modal, title="Поиск трека"):
    query = discord.ui.TextInput(
        label="Название песни или ссылка",
        placeholder="Например: Linkin Park Numb или https://youtu.be/...",
        min_length=2,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        service = _service(interaction)
        if service is None:
            await interaction.response.send_message(embed=error_embed("Музыкальный сервис недоступен"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            tracks = await service.search_tracks(str(self.query))
        except Exception:
            await interaction.followup.send(
                embed=error_embed("Ошибка поиска", "Не удалось получить варианты. Проверь Lavalink и источник."),
                ephemeral=True,
            )
            return

        if not tracks:
            await interaction.followup.send(embed=warn_embed("Ничего не найдено", "Попробуй другое название или прямую ссылку."), ephemeral=True)
            return

        options = tracks[:5]
        embed = ok_embed("Выбери трек", "Найдено до 5 вариантов. Нажми на нужный трек в списке ниже.")
        for index, track in enumerate(options, start=1):
            title = getattr(track, "title", "Неизвестный трек")
            author = getattr(track, "author", "Неизвестный исполнитель")
            embed.add_field(name=f"{index}. {title[:80]}", value=(author or "—")[:100], inline=False)

        await interaction.followup.send(embed=embed, view=TrackSelectView(options), ephemeral=True)


class PlaylistModal(discord.ui.Modal, title="Добавить плейлист"):
    url = discord.ui.TextInput(
        label="Ссылка на плейлист",
        placeholder="Вставь ссылку на YouTube/SoundCloud плейлист",
        min_length=8,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        value = str(self.url).strip()
        if not _is_url(value):
            await interaction.response.send_message(embed=warn_embed("Нужна ссылка", "Плейлисты добавляются только ссылкой."), ephemeral=True)
            return

        service = _service(interaction)
        if service is None:
            await interaction.response.send_message(embed=error_embed("Музыкальный сервис недоступен"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            tracks = await service.search_tracks(value)
            if not tracks:
                await interaction.followup.send(embed=warn_embed("Плейлист не найден", "Проверь ссылку и доступность плейлиста."), ephemeral=True)
                return
            player, status, added = await service.queue_tracks(interaction, tracks)
        except RuntimeError as exc:
            await interaction.followup.send(embed=warn_embed("Канал уже занят", str(exc)), ephemeral=True)
            return
        except Exception:
            await interaction.followup.send(embed=error_embed("Ошибка плейлиста", "Не удалось добавить плейлист."), ephemeral=True)
            return

        if status == "NO_PLAYER":
            await interaction.followup.send(embed=warn_embed("Зайди в голосовой канал", "Перед добавлением плейлиста нужно быть в voice-канале."), ephemeral=True)
            return

        await interaction.followup.send(embed=ok_embed("Плейлист добавлен", f"Добавлено треков: `{added}`."), ephemeral=True)


class TrackSelect(discord.ui.Select):
    def __init__(self, tracks: list):
        self.tracks = tracks
        options = []
        for index, track in enumerate(tracks[:5]):
            title = getattr(track, "title", "Неизвестный трек")[:100]
            author = (getattr(track, "author", "Неизвестный исполнитель") or "—")[:100]
            options.append(discord.SelectOption(label=title, description=author, value=str(index)))
        super().__init__(placeholder="Выбери нужный трек", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        service = _service(interaction)
        if service is None:
            await interaction.response.send_message(embed=error_embed("Музыкальный сервис недоступен"), ephemeral=True)
            return

        track = self.tracks[int(self.values[0])]
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            player, status, track = await service.queue_track(interaction, track)
        except RuntimeError as exc:
            await interaction.followup.send(embed=warn_embed("Канал уже занят", str(exc)), ephemeral=True)
            return
        except Exception:
            await interaction.followup.send(embed=error_embed("Ошибка музыки", "Не удалось запустить выбранный трек."), ephemeral=True)
            return

        if status == "NO_PLAYER":
            await interaction.followup.send(embed=warn_embed("Зайди в голосовой канал", "Перед запуском музыки нужно быть в voice-канале."), ephemeral=True)
            return

        if status == "QUEUED":
            await interaction.followup.send(embed=ok_embed("Добавлено в очередь", getattr(track, "title", "Трек добавлен")), ephemeral=True)
        else:
            await interaction.followup.send(embed=now_playing_embed(track, interaction.user), ephemeral=True)


class TrackSelectView(discord.ui.View):
    def __init__(self, tracks: list):
        super().__init__(timeout=90)
        self.add_item(TrackSelect(tracks))


class MusicControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _ensure_music_channel(self, interaction: discord.Interaction) -> bool:
        allowed_channel = getattr(getattr(interaction.client, "settings", None), "channel_music", 0)
        current_channel = getattr(interaction, "channel_id", None)

        if allowed_channel and current_channel != allowed_channel:
            await interaction.response.send_message(
                embed=warn_embed("Не тот канал", f"Музыкальная панель доступна только в <#{allowed_channel}>."),
                ephemeral=True,
            )
            return False
        return True

    async def _player(self, interaction: discord.Interaction):
        if not await self._ensure_music_channel(interaction):
            return None

        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет", "Бот сейчас не подключен к голосовому каналу."), ephemeral=True)
            return None
        return interaction.guild.voice_client

    @discord.ui.button(label="Подключить бота", emoji="🔊", style=discord.ButtonStyle.success, custom_id="music:connect_search")
    async def connect_search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_music_channel(interaction):
            return
        await interaction.response.send_modal(TrackSearchModal())

    @discord.ui.button(label="Добавить плейлист", emoji="➕", style=discord.ButtonStyle.primary, custom_id="music:add_playlist")
    async def add_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_music_channel(interaction):
            return
        await interaction.response.send_modal(PlaylistModal())

    @discord.ui.button(label="Пауза", emoji=EMOJI_PAUSE, style=discord.ButtonStyle.secondary, custom_id="music:pause")
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player(interaction)
        if not player:
            return
        if not getattr(player, "playing", False):
            await interaction.response.send_message(embed=warn_embed("Нечего ставить на паузу"), ephemeral=True)
            return
        await player.pause(True)
        await interaction.response.send_message(embed=ok_embed("Пауза включена"), ephemeral=True)

    @discord.ui.button(label="Продолжить", emoji=EMOJI_PLAY, style=discord.ButtonStyle.success, custom_id="music:resume")
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player(interaction)
        if not player:
            return
        await player.pause(False)
        await interaction.response.send_message(embed=ok_embed("Продолжаю воспроизведение"), ephemeral=True)

    @discord.ui.button(label="Пропуск", emoji=EMOJI_SKIP, style=discord.ButtonStyle.primary, custom_id="music:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player(interaction)
        if not player:
            return
        await player.skip(force=True)
        await interaction.response.send_message(embed=ok_embed("Трек пропущен"), ephemeral=True)

    @discord.ui.button(label="Стоп", emoji=EMOJI_STOP, style=discord.ButtonStyle.danger, custom_id="music:stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player(interaction)
        if not player:
            return
        try:
            player.queue.clear()
        except Exception:
            pass
        await player.disconnect()
        await interaction.response.send_message(embed=ok_embed("Музыка остановлена", "Очередь очищена, бот вышел из голосового канала."), ephemeral=True)

    @discord.ui.button(label="Очередь", emoji=EMOJI_QUEUE, style=discord.ButtonStyle.secondary, custom_id="music:queue")
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player(interaction)
        if not player:
            return
        await interaction.response.send_message(embed=queue_embed(player), ephemeral=True)
