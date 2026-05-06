import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import sqlite3

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

GUILD_ID = 1345261255300218992
CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

# ================= DATABASE =================
conn = sqlite3.connect("debts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    user_id TEXT PRIMARY KEY,
    amount INTEGER
)
""")
conn.commit()

def get_debt(user_id):
    cursor.execute("SELECT amount FROM debts WHERE user_id = ?", (str(user_id),))
    result = cursor.fetchone()
    return result[0] if result else 0

def add_debt(user_id, amount):
    current = get_debt(user_id)
    new_amount = current + amount

    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
    """, (str(user_id), new_amount))
    conn.commit()

def reduce_debt(user_id, amount):
    current = get_debt(user_id)
    new_amount = max(0, current - amount)

    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
    """, (str(user_id), new_amount))
    conn.commit()

def get_all_debts():
    cursor.execute("SELECT user_id, amount FROM debts")
    return cursor.fetchall()

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild)
    print(f"✅ BOT ONLINE: {bot.user}")

# ================= VIEWS =================
class LoanView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        add_debt(self.user_id, self.amount)
        total = get_debt(self.user_id)

        approve_channel = await bot.fetch_channel(CHANNEL_APPROVE)
        user = await bot.fetch_user(self.user_id)

        text = f"""〖💸〗НОВАЯ ЗАПИСЬ О ДОЛГЕ
────────────────
👤 Заемщик: {user.mention}
💰 Сумма долга: {self.amount:,}
📅 Дата выдачи: {datetime.now().strftime("%B %d, %Y")}

📉 Остаток к возврату: {total:,}
✅ Статус: Одобрено Администрацией
────────────────
Принял: {interaction.user.mention}
"""

        await approve_channel.send(text)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class PayDebtView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        reduce_debt(self.user_id, self.amount)
        total = get_debt(self.user_id)

        approve_channel = await bot.fetch_channel(CHANNEL_APPROVE)
        user = await bot.fetch_user(self.user_id)

        text = f"""〖💰〗ЧАСТИЧНОЕ ПОГАШЕНИЕ
────────────────
👤 Заемщик: {user.mention}
💸 Внесено: {self.amount:,}
📉 Остаток долга: {total:,}
📅 Дата платежа: {datetime.now().strftime("%B %d, %Y")}
────────────────
Принял: {interaction.user.mention}
"""

        await approve_channel.send(text)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

# ================= COMMANDS =================
@bot.tree.command(name="loan", description="Запросить долг", guild=guild)
@app_commands.describe(amount="Сумма")
async def loan(interaction: discord.Interaction, amount: int):

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(title="💸 ЗАЯВКА НА ДОЛГ", color=discord.Color.blue())
    embed.add_field(name="👤 Пользователь", value=interaction.user.mention)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}")

    await report_channel.send(embed=embed, view=LoanView(interaction.user.id, amount))
    await interaction.response.send_message("✅ Заявка отправлена", ephemeral=True)


@bot.tree.command(name="pay_debt", description="Погашение долга", guild=guild)
@app_commands.describe(amount="Сумма", screenshot="Скрин")
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(title="📥 ПОГАШЕНИЕ ДОЛГА", color=discord.Color.orange())
    embed.add_field(name="👤 Пользователь", value=interaction.user.mention)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}")
    embed.set_image(url=screenshot.url)

    await report_channel.send(embed=embed, view=PayDebtView(interaction.user.id, amount))
    await interaction.response.send_message("✅ Отправлено", ephemeral=True)


@bot.tree.command(name="all_loans", description="Все долги", guild=guild)
async def all_loans(interaction: discord.Interaction):

    data = get_all_debts()

    if not data:
        await interaction.response.send_message("❌ Нет должников", ephemeral=True)
        return

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    text = "📊 ВСЕ ДОЛЖНИКИ\n────────────────\n"

    for user_id, amount in data:
        user = await bot.fetch_user(int(user_id))
        text += f"{user.mention} — {amount:,}\n"

    await report_channel.send(text)
    await interaction.response.send_message("✅ Отправлено", ephemeral=True)


# ================= RUN =================
bot.run(TOKEN)
