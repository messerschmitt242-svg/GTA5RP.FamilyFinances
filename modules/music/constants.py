import os

LAVALINK_HOST = os.getenv("LAVALINK_HOST", "").strip().replace("https://", "").replace("http://", "")
LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", "443"))
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
LAVALINK_SECURE = os.getenv("LAVALINK_SECURE", "true").lower() in {"1", "true", "yes", "y", "on"}

MUSIC_RECONNECT_INTERVAL = int(os.getenv("MUSIC_RECONNECT_INTERVAL", "600"))
MUSIC_DEFAULT_VOLUME = int(os.getenv("MUSIC_DEFAULT_VOLUME", "70"))
MUSIC_MAX_VOLUME = int(os.getenv("MUSIC_MAX_VOLUME", "150"))
MUSIC_AUTO_LEAVE_SECONDS = int(os.getenv("MUSIC_AUTO_LEAVE_SECONDS", "300"))

EMOJI_PLAY = "▶️"
EMOJI_PAUSE = "⏸️"
EMOJI_STOP = "⏹️"
EMOJI_SKIP = "⏭️"
EMOJI_QUEUE = "📜"
EMOJI_MUSIC = "🎵"
EMOJI_WARN = "⚠️"
EMOJI_OK = "✅"
EMOJI_ERROR = "❌"
