import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import asyncio

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")

CHANNEL_ID_REQUEST = 1501528770853605437
CHANNEL_ID_REPORT = 1501351092125040710

GUILD_ID = 1345261255300218992

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

GUILD = discord.Object(id=GUILD_ID)

# ===== READY =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # 🔥 безопасный sync (главный фикс твоей проблемы)
    try:
        synced = await bot.tree.sync(guild=GUILD)
        print(f"✅ Guild sync OK: {len(synced)} commands")
    except Exception as e:
        print("❌ Guild sync error:", e)

        # fallback (очень важно)
        try:
            synced_global = await bot.tree.sync()
            print(f"⚠️ Global sync OK: {len(synced_global)} commands")
        except Exception as e2:
            print("❌ Global sync failed:", e2)

# ===== COMMAND =====
@bot.tree.command(
    name="pay_debt",
    description="Отправить отчет о погашении долга",
    guild=GUILD
)
@app_commands.describe(
    amount="Сумма выплаты",
    screenshot="Скриншот"
)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    await interaction.response.defer(ephemeral=True)

    try:
        channel = bot.get_channel(CHANNEL_ID_REPORT)

        # fallback если get_channel вернул None
        if channel is None:
            channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

        embed = discord.Embed(
            title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
            color=discord.Color.orange()
        )

        embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
        embed.add_field(name="💰 Сумма", value=f"{amount:,} ₽", inline=False)
        embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="⚠️ Статус", value="Ожидает проверки", inline=False)

        embed.set_image(url=screenshot.url)

        await channel.send(embed=embed)

        await interaction.followup.send("✅ Отчет отправлен", ephemeral=True)

    except Exception as e:
        print("❌ COMMAND ERROR:", e)

        await interaction.followup.send(
            f"❌ Ошибка: `{e}`",
            ephemeral=True
        )

# ===== RUN =====
bot.run(TOKEN)
