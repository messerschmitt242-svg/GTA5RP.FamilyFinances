import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

GUILD_ID = 1345261255300218992  # <-- твой сервер
CHANNEL_REQUEST = 1501528770853605437
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

if not TOKEN:
    raise RuntimeError("TOKEN не найден в Railway Variables!")

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

guild = discord.Object(id=GUILD_ID)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"BOT ONLINE: {bot.user}")
    print(f"GUILD: {GUILD_ID}")

    # 🔥 SYNC COMMANDS (guild + global fallback)
    try:
        synced_guild = await bot.tree.sync(guild=guild)
        print(f"✅ GUILD SYNCED: {len(synced_guild)} commands")
    except Exception as e:
        print("❌ GUILD SYNC ERROR:", e)

    try:
        synced_global = await bot.tree.sync()
        print(f"🌍 GLOBAL SYNCED: {len(synced_global)} commands")
    except Exception as e:
        print("❌ GLOBAL SYNC ERROR:", e)


# ================= LOAN COMMAND =================
@bot.tree.command(
    name="loan",
    description="Запросить выдачу долга",
    guild=guild
)
@app_commands.describe(amount="Сумма долга")
async def loan(interaction: discord.Interaction, amount: int):

    request_channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(
        title="💸 НОВАЯ ЗАЯВКА НА ДОЛГ",
        color=discord.Color.blue()
    )

    embed.add_field(name="👤 Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)

    await request_channel.send(embed=embed)

    await interaction.response.send_message("✅ Заявка отправлена", ephemeral=True)


# ================= PAY DEBT =================
@bot.tree.command(
    name="pay_debt",
    description="Отчет о погашении долга",
    guild=guild
)
@app_commands.describe(
    amount="Сумма выплаты",
    screenshot="Скриншот"
)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(
        title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)

    embed.set_image(url=screenshot.url)

    await report_channel.send(embed=embed)

    await interaction.response.send_message("✅ Отправлено", ephemeral=True)


# ================= RUN =================
bot.run(TOKEN)
