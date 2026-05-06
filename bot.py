import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")

CHANNEL_ID_REQUEST = 1501528770853605437  # где пишут команду
CHANNEL_ID_REPORT = 1501351092125040710   # куда отправляется отчет

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== READY =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # 🔥 global sync (самый стабильный вариант)
    try:
        synced = await bot.tree.sync()
        print(f"✅ Global sync OK: {len(synced)} commands")
    except Exception as e:
        print("SYNC ERROR:", e)

# ===== COMMAND =====
@bot.tree.command(
    name="pay_debt",
    description="Отправить отчет о погашении долга"
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

    await interaction.response.defer(ephemeral=True)

    try:
        # ===== проверка канала (request channel) =====
        if interaction.channel_id != CHANNEL_ID_REQUEST:
            await interaction.followup.send(
                "❌ Эту команду можно использовать только в нужном канале",
                ephemeral=True
            )
            return

        # ===== report channel =====
        report_channel = bot.get_channel(CHANNEL_ID_REPORT)

        if report_channel is None:
            report_channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

        # ===== embed =====
        embed = discord.Embed(
            title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
            color=discord.Color.orange()
        )

        embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
        embed.add_field(name="💰 Сумма", value=f"{amount:,} $", inline=False)
        embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="⚠️ Статус", value="Ожидает проверки", inline=False)

        embed.set_image(url=screenshot.url)

        # ===== отправка =====
        await report_channel.send(embed=embed)

        # ===== ответ пользователю =====
        await interaction.followup.send("✅ Отчет отправлен", ephemeral=True)

    except Exception as e:
        print("❌ ERROR:", e)

        await interaction.followup.send(
            f"❌ Ошибка: `{e}`",
            ephemeral=True
        )

# ===== RUN =====
bot.run(TOKEN)
