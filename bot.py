import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import sqlite3

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")

CHANNEL_ID_REQUEST = 1501528770853605437
CHANNEL_ID_REPORT = 1501351092125040710
CHANNEL_ID_APPROVED = 1448688906299113684

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== DB SETUP =====
conn = sqlite3.connect("debt.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    debt INTEGER DEFAULT 0,
    paid INTEGER DEFAULT 0
)
""")
conn.commit()

# ===== MEMORY =====
pending_data = {}

# ===== HELPERS =====
def add_payment(user_id: int, username: str, amount: int):
    cursor.execute("SELECT * FROM debts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO debts (user_id, username, debt, paid) VALUES (?, ?, ?, ?)",
            (user_id, username, 0, amount)
        )
    else:
        cursor.execute(
            "UPDATE debts SET paid = paid + ? WHERE user_id = ?",
            (amount, user_id)
        )

    conn.commit()

# ===== VIEW =====
class DebtView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = pending_data.get(self.message_id)
        if not data:
            await interaction.response.send_message("❌ Нет данных", ephemeral=True)
            return

        channel = await bot.fetch_channel(CHANNEL_ID_APPROVED)

        # ===== DB UPDATE =====
        add_payment(data["user_id"], data["username"], data["amount"])

        embed = discord.Embed(
            title="〖💰〗ЧАСТИЧНОЕ ПОГАШЕНИЕ",
            color=discord.Color.green()
        )

        embed.description = (
            "────────────────\n"
            f"👤 Заемщик: {data['username']}\n"
            f"💸 Внесено: {data['amount']:,}\n"
            f"📉 Остаток долга: \n"
            f"📅 Дата платежа: {data['date']}\n"
            "────────────────\n"
            f"Принял: {interaction.user.mention}"
        )

        await channel.send(embed=embed)

        await interaction.message.delete()
        await interaction.response.send_message("✅ Одобрено", ephemeral=True)

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.message.delete()
        await interaction.response.send_message("❌ Отклонено", ephemeral=True)

# ===== READY =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

# ===== COMMAND =====
@bot.tree.command(name="pay_debt", description="Отправить отчет")
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    await interaction.response.defer(ephemeral=True)

    try:
        report_channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

        embed = discord.Embed(
            title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
            color=discord.Color.orange()
        )

        embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
        embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
        embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="⚠️ Статус", value="Ожидает проверки", inline=False)

        embed.set_image(url=screenshot.url)

        message = await report_channel.send(embed=embed)

        # ===== SAVE TO MEMORY =====
        pending_data[message.id] = {
            "user_id": interaction.user.id,
            "username": interaction.user.display_name,
            "amount": amount,
            "date": datetime.now().strftime("%B %d, %Y")
        }

        await message.edit(view=DebtView(message.id))

        await interaction.followup.send("✅ Отправлено", ephemeral=True)

    except Exception as e:
        print("ERROR:", e)
        await interaction.followup.send(f"❌ Ошибка: `{e}`", ephemeral=True)

# ===== RUN =====
bot.run(TOKEN)
