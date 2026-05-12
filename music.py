import discord
import asyncio
import yt_dlp

# =========================
# STATE
# =========================

voice_client = None
queue = []
playing = False

# =========================
# YT-DLP CONFIG
# =========================

ytdl = yt_dlp.YoutubeDL({
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": False,
})

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}

# =========================
# SEARCH / EXTRACT
# =========================

def search_youtube(query: str):
    """Возвращает 5 результатов поиска"""
    data = ytdl.extract_info(f"ytsearch5:{query}", download=False)

    results = []
    for entry in data["entries"]:
        results.append({
            "title": entry.get("title"),
            "url": entry.get("webpage_url")
        })

    return results


def extract_audio(url: str):
    """Получить прямой аудиопоток"""
    info = ytdl.extract_info(url, download=False)
    return info["url"], info.get("title", "Unknown")


# =========================
# QUEUE SYSTEM
# =========================

def add_to_queue(url: str):
    queue.append(url)


def clear_queue():
    queue.clear()


def get_queue():
    return queue


# =========================
# PLAYER ENGINE
# =========================

async def play_next(bot):

    global voice_client, playing

    if not queue:
        playing = False
        return

    playing = True

    url = queue.pop(0)

    audio_url, title = extract_audio(url)

    source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)

    def after_play(err):
        fut = asyncio.run_coroutine_threadsafe(play_next(bot), bot.loop)

    if voice_client and voice_client.is_connected():
        voice_client.play(source, after=after_play)


async def start_playing(bot):
    """Запуск проигрывания"""
    global playing

    if not playing:
        await play_next(bot)


# =========================
# VOICE CONTROL
# =========================

async def connect_to_voice(channel: discord.VoiceChannel):
    global voice_client

    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()

    voice_client = await channel.connect()
    return voice_client


async def stop_music():
    global voice_client, queue, playing

    queue.clear()
    playing = False

    if voice_client:
        await voice_client.disconnect()
        voice_client = None


# =========================
# STATUS
# =========================

def is_playing():
    return playing


def get_voice():
    return voice_client
