import wavelink
import discord
import asyncio

# =====================
# STATE
# =====================

class MusicState:
    def __init__(self):
        self.queue = []
        self.loop = False

state = MusicState()

# =====================
# INIT LAVALINK
# =====================

async def init_lavalink(bot):
    node = wavelink.Node(
        uri="http://localhost:2333",
        password="youshallnotpass"
    )

    await wavelink.Pool.connect(
        client=bot,
        nodes=[node]
    )

# =====================
# VOICE
# =====================

async def connect(channel: discord.VoiceChannel):
    player: wavelink.Player = await channel.connect(cls=wavelink.Player)
    return player

# =====================
# SEARCH
# =====================

async def search(query: str):
    return await wavelink.Playable.search(query)

# =====================
# QUEUE
# =====================

def add(track):
    state.queue.append(track)

def clear():
    state.queue.clear()

def get_queue():
    return state.queue

# =====================
# PLAYBACK
# =====================

async def play_next(player: wavelink.Player):
    if not state.queue:
        return

    track = state.queue.pop(0)
    await player.play(track)

    # auto next
    async def next_track(_):
        await play_next(player)

    player.playing = track
    player.finished_callback = next_track

# =====================
# START
# =====================

async def start(player: wavelink.Player):
    if player.is_playing():
        return

    await play_next(player)

# =====================
# STOP
# =====================

async def stop(player: wavelink.Player):
    state.queue.clear()
    await player.disconnect()
