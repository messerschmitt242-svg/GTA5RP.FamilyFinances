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

# ================= DB =================
conn = sqlite3.connect("debts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    user_id INTEGER PRIMARY KEY,
    amount INTEGER
)
""")
conn.commit()

# ================= DB FUNCTIONS =================
def get_debt(user_id):
    cursor.execute("SELECT amount FROM debts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_debt(user_id, amount):
    current = get_debt(user_id)
    new_amount = current + amount

    cursor.execute("REPLACE INTO debts (user_id, amount) VALUES (?, ?)", (user_id, new_amount))
    conn.commit()

    return new_amount

def subtract_debt(user_id, amount):
    current = get_debt(user_id)
    new_amount = max(current - amount, 0)

    cursor.execute("REPLACE INTO debts (user_id, amount) VALUES (?, ?)", (user_id, new_amount))
    conn.commit()

    return new_amount

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

guild = discord.Object(id=GUILD_ID)

# ================= DATE =================
def nice_date():
    return datetime.now().strftime("%B %d, %Y")

# ================= BUTTONS =================
class ApproveRejectView(discord.ui.View):
    def __init__(self, data, kind):
        super().__init__(timeout=None)
        self.data = data
        self.kind = kind

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

        user = self.data["user"]
        amount = self.data["amount"]

        log_channel = await bot.fetch_channel(CHANNEL_APPROVE)

        # ===== PAY DEBT =====
        if self.kind == "pay":
            remaining = subtract_debt(user.id, amount)

            msg = f"""〖💰〗ЧАСТИЧНОЕ ПОГАШЕНИЕ
────────────────
👤 Заемщик: {user.mention}
💸 Внесено: {amount:,}
📉 Остаток долга: {remaining:,}
📅 Дата платежа: {nice_date()}
────────────────
Принял: {interaction.user.mention}
"""

        # ===== LOAN =====
        else:
            total = add_debt(user.id, amount)

            msg = f"""〖💸〗НОВАЯ ЗАПИСЬ О ДОЛГЕ
────────────────
👤 Заемщик: {user.mention}
💰 Сумма долга: {amount:,}
📅 Дата выдачи: {nice_date()}
📉 Остаток к возврату: {total:,}
✅ Статус: Одобрено Администрацией
────────────────
Принял: {interaction.user.mention}
"""

        await log_channel.send(msg)
        await interaction.message.delete()
        await interaction.followup.send("✅ Готово", ephemeral=True)

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

        await interaction.message.delete()
        await interaction.followup.send("❌ Отклонено", ephemeral=True)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"BOT ONLINE: {bot.user}")

    try:
        synced = await bot.tree.sync(guild=guild)
        print(f"SYNCED: {len(synced)} commands")
    except Exception as e:
        print("SYNC ERROR:", e)

# ================= LOAN =================
@bot.tree.command(name="loan", description="Запрос долга", guild=guild)
async def loan(interaction: discord.Interaction, amount: int):

    embed = discord.Embed(
        title="💸 ЗАЯВКА НА ДОЛГ",
        color=discord.Color.blue()
    )

    embed.add_field(name="Пользователь", value=interaction.user.mention)
    embed.add_field(name="Сумма", value=f"{amount:,}")
    embed.add_field(name="Дата", value=nice_date())

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    await report_channel.send(
        embed=embed,
        view=ApproveRejectView({
            "user": interaction.user,
            "amount": amount
        }, "loan")
    )

    await interaction.response.send_message("✅ Заявка отправлена", ephemeral=True)

# ================= PAY DEBT =================
@bot.tree.command(name="pay_debt", description="Погашение долга", guild=guild)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    embed = discord.Embed(
        title="📥 ПОГАШЕНИЕ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="Пользователь", value=interaction.user.mention)
    embed.add_field(name="Сумма", value=f"{amount:,}")
    embed.add_field(name="Дата", value=nice_date())
    embed.set_image(url=screenshot.url)

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    await report_channel.send(
        embed=embed,
        view=ApproveRejectView({
            "user": interaction.user,
            "amount": amount
        }, "pay")
    )

    await interaction.response.send_message("✅ Отправлено", ephemeral=True)

# ================= BALANCE =================
@bot.tree.command(name="balance", description="Проверить долг", guild=guild)
async def balance(interaction: discord.Interaction, user: discord.Member = None):

    user = user or interaction.user
    debt = get_debt(user.id)

    await interaction.response.send_message(
        f"💰 Долг {user.mention}: {debt:,}",
        ephemeral=True
    )

# ================= RUN =================
bot.run(TOKEN)
