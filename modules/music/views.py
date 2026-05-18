import discord
import wavelink

from .embeds import error_embed, now_playing_embed, ok_embed, queue_embed, warn_embed
from .constants import EMOJI_PAUSE, EMOJI_PLAY, EMOJI_QUEUE, EMOJI_SKIP, EMOJI_STOP


class MusicControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _player(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=warn_embed("Музыка не играет", "Бот сейчас не подключен к голосовому каналу."), ephemeral=True)
            return None
        return interaction.guild.voice_client

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
