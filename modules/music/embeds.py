import discord
from .constants import EMOJI_ERROR, EMOJI_MUSIC, EMOJI_OK, EMOJI_WARN


def base_embed(title: str, description: str = "", color: int = 0x2B2D31) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


def ok_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"{EMOJI_OK} {title}", description, 0x2ECC71)


def error_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"{EMOJI_ERROR} {title}", description, 0xE74C3C)


def warn_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"{EMOJI_WARN} {title}", description, 0xF1C40F)


def music_center_embed() -> discord.Embed:
    embed = base_embed(
        "🎛️ Музыкальный центр WAYNE INC.",
        (
            "Управление музыкой теперь полностью через кнопки.\n\n"
            "**Подключить бота** — ввести название трека и выбрать один из 5 вариантов.\n"
            "**Добавить плейлист** — добавить плейлист только по ссылке.\n"
            "**Пауза / Продолжить / Пропуск / Стоп / Очередь** — управление текущим воспроизведением.\n\n"
            "Все ответы бота, кроме этого центра, отображаются временно только для пользователя."
        ),
        0x5865F2,
    )
    embed.set_footer(text="Один Discord-бот может играть только в одном голосовом канале сервера одновременно.")
    return embed


def now_playing_embed(track, requester=None) -> discord.Embed:
    title = getattr(track, "title", "Неизвестный трек")
    uri = getattr(track, "uri", None)
    author = getattr(track, "author", "Неизвестный исполнитель")

    embed = base_embed(f"{EMOJI_MUSIC} Сейчас играет", color=0x5865F2)
    embed.description = f"[{title}]({uri})" if uri else title
    embed.add_field(name="Исполнитель", value=author or "—", inline=True)
    if requester:
        embed.add_field(name="Добавил", value=requester.mention, inline=True)
    return embed


def queue_embed(player, limit: int = 10) -> discord.Embed:
    embed = base_embed(f"{EMOJI_MUSIC} Очередь", color=0x5865F2)
    current = getattr(player, "current", None)
    lines = []
    if current:
        lines.append(f"**Сейчас:** {getattr(current, 'title', 'Неизвестный трек')}")

    queue = getattr(player, "queue", None)
    items = []
    try:
        items = list(queue)[:limit] if queue is not None else []
    except Exception:
        items = []

    if items:
        lines.append("\n**Далее:**")
        for index, track in enumerate(items, start=1):
            lines.append(f"`{index}.` {getattr(track, 'title', 'Неизвестный трек')}")
    else:
        lines.append("\nОчередь пуста.")

    embed.description = "\n".join(lines)
    return embed
