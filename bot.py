import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")

CHANNEL_ID_REQUEST = 1501528770853605437  # куда пишут команду (и откуда удаляем)
CHANNEL_ID_REPORT = 1501351092125040710   # куда отправляем красивый отчёт

GUILD_ID = 123456789012345678  # <-- ВСТАВЬ ID СВОЕГО СЕРВЕРА

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

# ===== BOT =====
intents = discord.Intents.default()
intents.message_content = True  # на будущее (не обязательно для slash, но полезно)

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD = discord.Object(id=GUILD_ID)

# ===== READY =====
@bot.event
async def on_ready():
    await bot.tree.sync(guild=GUILD)
    print(f"Запущен как {bot.user}")

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
async def pay_debt(
    interaction: discord.Interaction,
    amount: int,
    screenshot: discord.Attachment
):

    # 💡 убираем "не отвечает"
    await interaction.response.defer(ephemeral=True)

    # канал где была команда
    request_channel = await bot.fetch_channel(CHANNEL_ID_REQUEST)

    # канал куда отправляем отчёт
    report_channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

    # ===== EMBED =====
    embed = discord.Embed(
        title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма выплаты", value=f"{amount:,} ₽", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
    embed.add_field(name="⚠️ Статус", value="Ожидает проверки администрацией", inline=False)

    embed.set_image(url=screenshot.url)

    # ===== 1. отправляем в отчёт канал =====
    await report_channel.send(embed=embed)

    # ===== 2. удаляем сообщение команды =====
    try:
        # это удалит сам slash interaction message (если возможно)
        await interaction.delete_original_response()
    except:
        pass

    # ===== 3. подтверждение пользователю (в ЛС-стиле ephemeral) =====
    await interaction.followup.send("✅ Запрос обработан и отправлен", ephemeral=True)

# ===== RUN =====
bot.run(TOKEN)
