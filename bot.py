import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ====== CONFIG ======
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1501528770853605437
GUILD_ID = 1345261255300218992  # <-- ВСТАВЬ ID СВОЕГО СЕРВЕРА

if not TOKEN:
    raise RuntimeError("TOKEN не найден в переменных окружения!")

# ====== BOT SETUP ======
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ====== SYNC COMMANDS ======
@bot.event
async def on_ready():
    # МГНОВЕННЫЕ команды (guild sync)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)

    print(f"Запущен как {bot.user}")
    print("Slash команды синхронизированы (guild mode)")

# ====== SLASH COMMAND ======
@bot.tree.command(
    name="pay_debt",
    description="Отправить отчет о погашении долга",
    guild=discord.Object(id=GUILD_ID)  # <-- важно для мгновенного появления
)
@app_commands.describe(
    amount="Сумма выплаты",
    screenshot="Скриншот"
)
async def pay_debt(
    interaction: discord.Interaction,
    amount: int,
    screenshot: discord.Attachment
):

    channel = await bot.fetch_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма выплаты", value=f"{amount:,} ₽", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
    embed.add_field(name="⚠️ Статус", value="Ожидает проверки администрацией", inline=False)

    embed.set_image(url=screenshot.url)

    await channel.send(embed=embed)

    await interaction.response.send_message(
        "✅ Отчет отправлен!",
        ephemeral=True
    )

# ====== RUN BOT ======
bot.run(TOKEN)
