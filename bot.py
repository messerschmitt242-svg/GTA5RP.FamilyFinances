import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import sqlite3
import os

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

HEAD_ROLE_ID = 1345267230300049408
GUILD_ID = 1345261255300218992

CHANNEL_FAMILY_BALANCE = 1501339448250601472
CHANNEL_DEPOSITS_LOG = 1447505999392149534
CHANNEL_TOP_SPONSORS = 1447514330252836906

CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

# ================= COLORS =================
BANK_COLOR = discord.Color.gold()
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
INFO_COLOR = discord.Color.blurple()
ADMIN_COLOR = discord.Color.dark_gray()

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

active_uploads = {}

# ================= DATABASE =================
conn = sqlite3.connect("/data/family.db")
conn.execute("PRAGMA journal_mode=WAL;")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    user_id TEXT PRIMARY KEY,
    amount INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS family_bank (
    id INTEGER PRIMARY KEY,
    balance INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sponsors (
    user_id TEXT PRIMARY KEY,
    amount INTEGER
)
""")

cursor.execute("INSERT OR IGNORE INTO family_bank (id, balance) VALUES (1, 0)")
conn.commit()

# ================= DB =================
def get_balance():
    cursor.execute("SELECT balance FROM family_bank WHERE id=1")
    return cursor.fetchone()[0]

def set_balance(amount):
    cursor.execute("UPDATE family_bank SET balance=? WHERE id=1", (amount,))
    conn.commit()

def add_balance(amount):
    set_balance(get_balance() + amount)

def subtract_balance(amount):
    set_balance(max(0, get_balance() - amount))

def get_debt(user_id):
    cursor.execute("SELECT amount FROM debts WHERE user_id=?", (str(user_id),))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_debt(user_id, amount):
    total = get_debt(user_id) + amount
    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
    """, (str(user_id), total))
    conn.commit()

def reduce_debt(user_id, amount):
    current = get_debt(user_id)
    new = max(0, current - amount)

    if new == 0:
        cursor.execute("DELETE FROM debts WHERE user_id=?", (str(user_id),))
    else:
        cursor.execute("""
        INSERT INTO debts (user_id, amount)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
        """, (str(user_id), new))

    conn.commit()

def get_all_debts():
    cursor.execute("SELECT user_id, amount FROM debts")
    return cursor.fetchall()

def add_sponsor(user_id, amount):
    cursor.execute("SELECT amount FROM sponsors WHERE user_id=?", (str(user_id),))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE sponsors SET amount=amount+? WHERE user_id=?", (amount, str(user_id)))
    else:
        cursor.execute("INSERT INTO sponsors VALUES (?, ?)", (str(user_id), amount))

    conn.commit()

def get_top_sponsors():
    cursor.execute("SELECT user_id, amount FROM sponsors ORDER BY amount DESC")
    return cursor.fetchall()

def set_sponsor(user_id, amount):
    cursor.execute("INSERT OR REPLACE INTO sponsors VALUES (?, ?)", (str(user_id), amount))
    conn.commit()

# ================= EMBED HELPER =================
def bank_embed(title, desc, color):
    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now()
    )
    embed.set_footer(text="🏦 Wayne Family Bank")
    return embed

# ================= HELPERS =================
def is_head(member: discord.Member):
    return any(role.id == HEAD_ROLE_ID for role in member.roles)

# ================= BALANCE =================
async def update_balance_message():
    channel = await bot.fetch_channel(CHANNEL_FAMILY_BALANCE)

    embed = bank_embed(
        "💰 БАЛАНС СЕМЬИ",
        f"💵 {get_balance():,}",
        BANK_COLOR
    )

    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(embed=embed)
            return

    msg = await channel.send(embed=embed)
    await msg.pin()

# ================= TOP SPONSORS =================
async def refresh_top_message():
    channel = await bot.fetch_channel(CHANNEL_TOP_SPONSORS)
    data = get_top_sponsors()

    if not data:
        embed = bank_embed("🏆 ТОП СПОНСОРОВ", "Пока пусто", INFO_COLOR)
    else:
        desc = ""
        for i, (uid, amount) in enumerate(data, 1):
            desc += f"**{i}.** <@{uid}> — 💰 {amount:,}\n"

        embed = bank_embed("🏆 ТОП СПОНСОРОВ", desc, BANK_COLOR)

    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(embed=embed)
            return

    msg = await channel.send(embed=embed)
    await msg.pin()

# ================= ADMIN LOG =================
async def admin_log(action, user, amount, admin):
    channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(
        title="🛠️ АДМИН ДЕЙСТВИЕ",
        color=ADMIN_COLOR,
        timestamp=datetime.now()
    )

    embed.add_field(name="Действие", value=action, inline=False)
    embed.add_field(name="Пользователь", value=user.mention, inline=False)
    embed.add_field(name="Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="Админ", value=admin.mention, inline=False)

    await channel.send(embed=embed)

# ================= MENU =================
class FamilyMenu(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 Взнос", style=discord.ButtonStyle.green)
    async def deposit(self, interaction, button):
        await interaction.response.send_modal(DepositModal())

    @discord.ui.button(label="💸 Долг", style=discord.ButtonStyle.blurple)
    async def loan(self, interaction, button):
        await interaction.response.send_modal(LoanModal())

    @discord.ui.button(label="📥 Погашение", style=discord.ButtonStyle.gray)
    async def repay(self, interaction, button):
        await interaction.response.send_modal(PayDebtModal())

    @discord.ui.button(label="📊 Долги", style=discord.ButtonStyle.secondary)
    async def list(self, interaction, button):

        data = get_all_debts()

        if not data:
            embed = bank_embed("📊 ДОЛГИ", "Нет долгов", INFO_COLOR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        desc = ""
        for uid, amount in data:
            desc += f"<@{uid}> — {amount:,}\n"

        embed = bank_embed("📊 ДОЛГИ", desc, BANK_COLOR)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= MODALS =================
class DepositModal(discord.ui.Modal, title="Взнос"):
    amount = discord.ui.TextInput(label="Сумма")

    async def on_submit(self, interaction):
        amount = int(self.amount.value)
        await interaction.response.send_message(
            embed=bank_embed("📎 Отправь скрин", "Загрузи файл или ссылку", INFO_COLOR),
            ephemeral=True
        )

class LoanModal(discord.ui.Modal, title="Долг"):
    amount = discord.ui.TextInput(label="Сумма")

    async def on_submit(self, interaction):
        embed = bank_embed("💸 Заявка", f"{interaction.user.mention} запросил {self.amount.value}", INFO_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PayDebtModal(discord.ui.Modal, title="Погашение"):
    amount = discord.ui.TextInput(label="Сумма")

    async def on_submit(self, interaction):
        debt = get_debt(interaction.user.id)

        embed = bank_embed(
            "📥 ПОГАШЕНИЕ",
            f"Долг: {debt:,}\nВнести: {self.amount.value}",
            SUCCESS_COLOR
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= MENU COMMAND =================
@bot.tree.command(name="menu", guild=guild)
async def menu(interaction: discord.Interaction):

    embed = bank_embed(
        "🏦 WAYNE BANK",
        "Добро пожаловать в семейный банк",
        BANK_COLOR
    )

    await interaction.response.send_message(embed=embed, view=FamilyMenu())

# ================= RUN =================
bot.run(TOKEN)
