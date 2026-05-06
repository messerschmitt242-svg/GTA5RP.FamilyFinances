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
CHANNEL_ID_LOANS = 1501385708366205028

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== DB =====
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
pending_payments = {}
pending_loans = {}

# ===== HELPERS =====
def add_loan(user_id: int, username: str, amount: int):
    cursor.execute("SELECT * FROM debts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO debts (user_id, username, debt, paid) VALUES (?, ?, ?, ?)",
            (user_id, username, amount, 0)
        )
    else:
        cursor.execute(
            "UPDATE debts SET debt = debt + ? WHERE user_id = ?",
            (amount, user_id)
        )

    conn.commit()

# ===== VIEW =====
class LoanView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = pending_loans.get(self.message_id)
        if not data:
            await interaction.response.send_message("❌ Нет данных", ephemeral=True)
            return

        add_loan(data["user_id"], data["username"], data["amount"])

        channel = await bot.fetch_channel(CHANNEL_ID_APPROVED)

        embed = discord.Embed(
            title="〖💸〗НОВАЯ ЗАПИСЬ О ДОЛГЕ",
            color=discord.Color.green()
        )

        embed.description = (
            "────────────────\n"
            f"👤 Заемщик: {data['username']}\n"
            f"💰 Сумма долга: {data['amount']:,}\n"
            f"📅 Дата выдачи: {data['date']}\n"
            f"📉 Остаток к возврату: {data['amount']:,}\n"
            "✅ Статус: Одобрено Администрацией\n"
            "────────────────"
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

# =========================================================
# ===================== PAY DEBT ==========================
# =========================================================

@bot.tree.command(name="pay_debt", description="Отправить отчет о выплате")
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    await interaction.response.defer(ephemeral=True)

    channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

    embed = discord.Embed(
        title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)

    embed.set_image(url=screenshot.url)

    message = await channel.send(embed=embed)

    pending_payments[message.id] = {
        "user_id": interaction.user.id,
        "username": interaction.user.display_name,
        "amount": amount,
        "date": datetime.now().strftime("%B %d, %Y")
    }

    await message.edit(view=LoanView(message.id))

    await interaction.followup.send("✅ Отправлено", ephemeral=True)

# =========================================================
# ===================== LOAN SYSTEM ========================
# =========================================================

@bot.tree.command(name="loan", description="Запросить долг")
async def loan(interaction: discord.Interaction, amount: int):

    await interaction.response.defer(ephemeral=True)

    channel = await bot.fetch_channel(CHANNEL_ID_LOANS)

    embed = discord.Embed(
        title="📨 ЗАПРОС НА ВЫДАЧУ ДОЛГА",
        color=discord.Color.blue()
    )

    embed.add_field(name="👤 Заемщик", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)

    message = await channel.send(embed=embed)

    pending_loans[message.id] = {
        "user_id": interaction.user.id,
        "username": interaction.user.display_name,
        "amount": amount,
        "date": datetime.now().strftime("%B %d, %Y")
    }

    await message.edit(view=LoanView(message.id))

    await interaction.followup.send("✅ Заявка отправлена", ephemeral=True)

# ===== RUN =====
bot.run(TOKEN)
