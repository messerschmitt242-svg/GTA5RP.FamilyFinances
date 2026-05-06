import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import sqlite3
import os

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

GUILD_ID = 1345261255300218992

CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

CHANNEL_FAMILY_BALANCE = 1501339448250601472
CHANNEL_FAMILY_LOG = 1447505999392149534
CHANNEL_TOP_SPONSORS = 1447514330252836906

if not TOKEN:
    raise RuntimeError("TOKEN не найден")

# ================= DB =================
conn = sqlite3.connect("family.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS family_bank (
    id INTEGER PRIMARY KEY,
    balance INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sponsors (
    user_id INTEGER PRIMARY KEY,
    amount INTEGER
)
""")

conn.commit()

# INIT balance
cursor.execute("SELECT balance FROM family_bank WHERE id=1")
if cursor.fetchone() is None:
    cursor.execute("INSERT INTO family_bank (id, balance) VALUES (1, 0)")
    conn.commit()

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

# ================= HELPERS =================

async def update_family_balance_message():
    channel = await bot.fetch_channel(CHANNEL_FAMILY_BALANCE)

    cursor.execute("SELECT balance FROM family_bank WHERE id=1")
    balance = cursor.fetchone()[0]

    text = f"💰 Баланс семьи: **{balance:,}**"

    messages = [msg async for msg in channel.history(limit=5)]
    if messages:
        await messages[0].edit(content=text)
    else:
        await channel.send(text)


async def update_top_sponsors():
    channel = await bot.fetch_channel(CHANNEL_TOP_SPONSORS)

    cursor.execute("SELECT user_id, amount FROM sponsors ORDER BY amount DESC")
    rows = cursor.fetchall()

    if not rows:
        text = "🏆 Топ спонсоров пуст"
    else:
        text = "🏆 **ТОП СПОНСОРОВ**\n────────────────\n"
        for i, (user_id, amount) in enumerate(rows, start=1):
            text += f"{i}. <@{user_id}> — {amount:,}\n"

    messages = [msg async for msg in channel.history(limit=5)]
    if messages:
        await messages[0].edit(content=text)
    else:
        await channel.send(text)


def add_to_balance(amount):
    cursor.execute("UPDATE family_bank SET balance = balance + ? WHERE id=1", (amount,))
    conn.commit()


def set_balance(amount):
    cursor.execute("UPDATE family_bank SET balance = ? WHERE id=1", (amount,))
    conn.commit()


def add_sponsor(user_id, amount):
    cursor.execute("SELECT amount FROM sponsors WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE sponsors SET amount = amount + ? WHERE user_id=?", (amount, user_id))
    else:
        cursor.execute("INSERT INTO sponsors (user_id, amount) VALUES (?, ?)", (user_id, amount))

    conn.commit()


def set_sponsor(user_id, amount):
    cursor.execute("INSERT OR REPLACE INTO sponsors (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()

# ================= READY =================
@bot.event
async def on_ready():
    print(f"BOT ONLINE: {bot.user}")

    await bot.tree.sync(guild=guild)

    await update_family_balance_message()
    await update_top_sponsors()

# ================= DEPOSIT =================

class DepositView(discord.ui.View):
    def __init__(self, user, amount):
        super().__init__(timeout=None)
        self.user = user
        self.amount = amount

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        add_to_balance(self.amount)
        add_sponsor(self.user.id, self.amount)

        await update_family_balance_message()
        await update_top_sponsors()

        log_channel = await bot.fetch_channel(CHANNEL_FAMILY_LOG)

        await log_channel.send(
            f"💸 Пополнение фонда\n"
            f"👤 {self.user.mention}\n"
            f"💰 {self.amount:,}"
        )

        await interaction.message.delete()


@bot.tree.command(name="deposit_to_family", guild=guild)
@app_commands.describe(amount="Сумма", screenshot="Скрин")
async def deposit(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    embed = discord.Embed(title="💰 ВЗНОС В ФОНД", color=discord.Color.green())
    embed.add_field(name="👤 Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.set_image(url=screenshot.url)

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    await report_channel.send(
        embed=embed,
        view=DepositView(interaction.user, amount)
    )

    await interaction.response.send_message("Заявка отправлена", ephemeral=True)

# ================= EDIT BALANCE =================

@bot.tree.command(name="edit_family_bank", guild=guild)
@app_commands.describe(amount="Новый баланс")
async def edit_balance(interaction: discord.Interaction, amount: int):

    set_balance(amount)

    await update_family_balance_message()

    await interaction.response.send_message(f"Баланс обновлен: {amount}", ephemeral=True)

# ================= EDIT SPONSOR =================

@bot.tree.command(name="edit_sponsor", guild=guild)
@app_commands.describe(user="Пользователь", amount="Сумма")
async def edit_sponsor_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):

    set_sponsor(user.id, amount)

    await update_top_sponsors()

    await interaction.response.send_message("Спонсор обновлен", ephemeral=True)

# ================= RUN =================
bot.run(TOKEN)
