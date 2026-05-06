import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

import os
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1501528770853605437

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Запущен как {bot.user}")

@bot.tree.command(name="pay_debt", description="Отправить отчет о погашении долга")
@app_commands.describe(
    amount="Сумма выплаты",
    screenshot="Скриншот"
)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    channel = bot.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма выплаты", value=f"{amount:,}", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
    embed.add_field(name="⚠️ Статус", value="Ожидает проверки администрацией", inline=False)

    embed.set_image(url=screenshot.url)

    await channel.send(embed=embed)

    await interaction.response.send_message("✅ Отчет отправлен!", ephemeral=True)

bot.run(TOKEN)