```python
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

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

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

cursor.execute("""
INSERT OR IGNORE INTO family_bank (id, balance)
VALUES (1, 0)
""")

conn.commit()

# ================= DB =================
def get_balance():
    cursor.execute("SELECT balance FROM family_bank WHERE id=1")
    return cursor.fetchone()[0]

def set_balance(amount):
    cursor.execute(
        "UPDATE family_bank SET balance=? WHERE id=1",
        (amount,)
    )
    conn.commit()

def add_balance(amount):
    set_balance(get_balance() + amount)

def subtract_balance(amount):
    set_balance(max(0, get_balance() - amount))

def get_debt(user_id):

    cursor.execute(
        "SELECT amount FROM debts WHERE user_id=?",
        (str(user_id),)
    )

    row = cursor.fetchone()

    return row[0] if row else 0

def add_debt(user_id, amount):

    total = get_debt(user_id) + amount

    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id)
    DO UPDATE SET amount=excluded.amount
    """, (str(user_id), total))

    conn.commit()

def reduce_debt(user_id, amount):

    current = get_debt(user_id)

    new = max(0, current - amount)

    if new == 0:

        cursor.execute(
            "DELETE FROM debts WHERE user_id=?",
            (str(user_id),)
        )

    else:

        cursor.execute("""
        INSERT INTO debts (user_id, amount)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET amount=excluded.amount
        """, (str(user_id), new))

    conn.commit()

def get_all_debts():

    cursor.execute(
        "SELECT user_id, amount FROM debts"
    )

    return cursor.fetchall()

def add_sponsor(user_id, amount):

    cursor.execute(
        "SELECT amount FROM sponsors WHERE user_id=?",
        (str(user_id),)
    )

    row = cursor.fetchone()

    if row:

        cursor.execute("""
        UPDATE sponsors
        SET amount=amount+?
        WHERE user_id=?
        """, (amount, str(user_id)))

    else:

        cursor.execute("""
        INSERT INTO sponsors VALUES (?, ?)
        """, (str(user_id), amount))

    conn.commit()

def get_top_sponsors():

    cursor.execute("""
    SELECT user_id, amount
    FROM sponsors
    ORDER BY amount DESC
    """)

    return cursor.fetchall()

# ================= HELPERS =================
def is_head(member: discord.Member):

    return any(
        role.id == HEAD_ROLE_ID
        for role in member.roles
    )

async def update_balance_message():

    channel = await bot.fetch_channel(
        CHANNEL_FAMILY_BALANCE
    )

    text = (
        "💰 БАЛАНС СЕМЬИ\n"
        "──────────────\n"
        f"{get_balance():,}"
    )

    messages = [
        msg async for msg
        in channel.history(limit=10)
    ]

    for msg in messages:

        if msg.author == bot.user:

            await msg.edit(content=text)
            return

    msg = await channel.send(text)

    await msg.pin()

async def update_top_sponsors():

    channel = await bot.fetch_channel(
        CHANNEL_TOP_SPONSORS
    )

    data = get_top_sponsors()

    if not data:

        text = "🏆 ТОП СПОНСОРОВ ПУСТ"

    else:

        text = (
            "🏆 ТОП СПОНСОРОВ\n"
            "──────────────\n"
        )

        for i, (uid, amount) in enumerate(data, 1):

            text += f"{i}. <@{uid}> — {amount:,}\n"

    messages = [
        msg async for msg
        in channel.history(limit=10)
    ]

    for msg in messages:

        if msg.author == bot.user:

            await msg.edit(content=text)
            return

    await channel.send(text)

async def admin_log(action, user, amount, admin):

    channel = await bot.fetch_channel(
        CHANNEL_REPORT
    )

    embed = discord.Embed(
        title="🛠️ ДЕЙСТВИЕ АДМИНИСТРАЦИИ",
        color=discord.Color.dark_gray()
    )

    embed.add_field(
        name="📌 Действие",
        value=action,
        inline=False
    )

    embed.add_field(
        name="👤 Пользователь",
        value=user.mention,
        inline=False
    )

    embed.add_field(
        name="💰 Сумма",
        value=f"{amount:,}",
        inline=False
    )

    embed.add_field(
        name="🛡️ Администратор",
        value=admin.mention,
        inline=False
    )

    embed.timestamp = datetime.now()

    await channel.send(embed=embed)

# ================= EVENTS =================
@bot.event
async def on_ready():

    bot.add_view(FamilyMenu())

    await bot.tree.sync(guild=guild)

    print("BOT ONLINE")

    channel = await bot.fetch_channel(
        CHANNEL_REQUEST
    )

    messages = [
        msg async for msg
        in channel.history(limit=10)
    ]

    for msg in messages:

        if (
            msg.author == bot.user
            and "СЕМЕЙНЫЙ БАНК" in msg.content
        ):
            return

    menu = await channel.send(
        "📊 СЕМЕЙНЫЙ БАНК",
        view=FamilyMenu()
    )

    await menu.pin()

@bot.event
async def on_message(message: discord.Message):

    await bot.process_commands(message)

    if message.author.bot:
        return

    uid = message.author.id

    if uid not in active_uploads:
        return

    state = active_uploads[uid]

    if message.channel.id != state["channel_id"]:
        return

    image_url = None

    if message.attachments:

        image_url = message.attachments[0].url

    elif message.content.startswith("http"):

        image_url = message.content

    if not image_url:
        return

    try:
        await message.delete()
    except:
        pass

    await state["callback"](message, image_url)

    del active_uploads[uid]

# ================= APPROVE VIEWS =================
class DepositView(discord.ui.View):

    def __init__(self, user_id, amount):

        super().__init__(timeout=None)

        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(
        label="✅ Одобрить",
        style=discord.ButtonStyle.green
    )
    async def approve(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        add_balance(self.amount)

        add_sponsor(self.user_id, self.amount)

        await update_balance_message()
        await update_top_sponsors()

        user = await bot.fetch_user(self.user_id)

        await admin_log(
            "Одобрено пополнение",
            user,
            self.amount,
            interaction.user
        )

        await interaction.message.delete()

    @discord.ui.button(
        label="❌ Отказать",
        style=discord.ButtonStyle.red
    )
    async def reject(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        await interaction.message.delete()

class LoanView(discord.ui.View):

    def __init__(self, user_id, amount):

        super().__init__(timeout=None)

        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(
        label="✅ Одобрить",
        style=discord.ButtonStyle.green
    )
    async def approve(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        subtract_balance(self.amount)

        add_debt(self.user_id, self.amount)

        await update_balance_message()

        user = await bot.fetch_user(self.user_id)

        await admin_log(
            "Одобрена выдача долга",
            user,
            self.amount,
            interaction.user
        )

        channel = await bot.fetch_channel(
            CHANNEL_APPROVE
        )

        await channel.send(
            f"💸 ДОЛГ\n"
            f"{user.mention}\n"
            f"💰 {self.amount:,}"
        )

        await interaction.message.delete()

    @discord.ui.button(
        label="❌ Отказать",
        style=discord.ButtonStyle.red
    )
    async def reject(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        await interaction.message.delete()

class PayDebtView(discord.ui.View):

    def __init__(self, user_id, amount):

        super().__init__(timeout=None)

        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(
        label="✅ Одобрить",
        style=discord.ButtonStyle.green
    )
    async def approve(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        reduce_debt(self.user_id, self.amount)

        add_balance(self.amount)

        await update_balance_message()

        user = await bot.fetch_user(self.user_id)

        await admin_log(
            "Одобрено погашение",
            user,
            self.amount,
            interaction.user
        )

        channel = await bot.fetch_channel(
            CHANNEL_APPROVE
        )

        await channel.send(
            f"📥 ПОГАШЕНИЕ\n"
            f"{user.mention}\n"
            f"💰 {self.amount:,}"
        )

        await interaction.message.delete()

    @discord.ui.button(
        label="❌ Отказать",
        style=discord.ButtonStyle.red
    )
    async def reject(self, interaction, button):

        if not is_head(interaction.user):

            return await interaction.response.send_message(
                "❌ Нет доступа",
                ephemeral=True
            )

        await interaction.message.delete()

# ================= MODALS =================
class DepositModal(discord.ui.Modal, title="Добровольный взнос"):

    amount = discord.ui.TextInput(
        label="Сумма"
    )

    async def on_submit(self, interaction):

        try:
            amount = int(self.amount.value)

        except:

            return await interaction.response.send_message(
                "❌ Неверная сумма",
                ephemeral=True
            )

        uid = interaction.user.id

        async def callback(message, image_url):

            channel = await bot.fetch_channel(
                CHANNEL_REPORT
            )

            embed = discord.Embed(
                title="💰 ЗАЯВКА НА ПОПОЛНЕНИЕ",
                color=discord.Color.green()
            )

            embed.add_field(
                name="👤",
                value=interaction.user.mention
            )

            embed.add_field(
                name="💸",
                value=f"{amount:,}"
            )

            embed.set_image(url=image_url)

            await channel.send(
                embed=embed,
                view=DepositView(uid, amount)
            )

        active_uploads[uid] = {
            "callback": callback,
            "channel_id": interaction.channel.id
        }

        await interaction.response.send_message(
            "📎 Отправь картинку",
            ephemeral=True
        )

class LoanModal(discord.ui.Modal, title="Взять в долг"):

    amount = discord.ui.TextInput(
        label="Сумма"
    )

    async def on_submit(self, interaction):

        try:
            amount = int(self.amount.value)

        except:

            return await interaction.response.send_message(
                "❌ Неверная сумма",
                ephemeral=True
            )

        uid = interaction.user.id

        async def callback(message, image_url):

            channel = await bot.fetch_channel(
                CHANNEL_REPORT
            )

            embed = discord.Embed(
                title="💸 ЗАЯВКА НА ДОЛГ",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="👤",
                value=interaction.user.mention
            )

            embed.add_field(
                name="💰",
                value=f"{amount:,}"
            )

            embed.set_image(url=image_url)

            await channel.send(
                embed=embed,
                view=LoanView(uid, amount)
            )

        active_uploads[uid] = {
            "callback": callback,
            "channel_id": interaction.channel.id
        }

        await interaction.response.send_message(
            "📎 Отправь скриншот",
            ephemeral=True
        )

class PayDebtModal(discord.ui.Modal, title="Погашение долга"):

    amount = discord.ui.TextInput(
        label="Сумма"
    )

    async def on_submit(self, interaction):

        try:
            amount = int(self.amount.value)

        except:

            return await interaction.response.send_message(
                "❌ Неверная сумма",
                ephemeral=True
            )

        debt = get_debt(interaction.user.id)

        uid = interaction.user.id

        async def callback(message, image_url):

            channel = await bot.fetch_channel(
                CHANNEL_REPORT
            )

            embed = discord.Embed(
                title="📥 ПОГАШЕНИЕ",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="👤",
                value=interaction.user.mention
            )

            embed.add_field(
                name="💰",
                value=f"{amount:,}"
            )

            embed.set_image(url=image_url)

            await channel.send(
                embed=embed,
                view=PayDebtView(uid, amount)
            )

        active_uploads[uid] = {
            "callback": callback,
            "channel_id": interaction.channel.id
        }

        await interaction.response.send_message(
            f"📊 Долг: {debt:,}\n📎 Отправь скриншот",
            ephemeral=True
        )

# ================= MENU =================
class FamilyMenu(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="💰 Добровольный взнос",
        style=discord.ButtonStyle.green,
        custom_id="family_deposit"
    )
    async def deposit(self, interaction, button):

        await interaction.response.send_modal(
            DepositModal()
        )

    @discord.ui.button(
        label="💸 Взять в долг",
        style=discord.ButtonStyle.blurple,
        custom_id="family_loan"
    )
    async def loan(self, interaction, button):

        await interaction.response.send_modal(
            LoanModal()
        )

    @discord.ui.button(
        label="📥 Погасить долг",
        style=discord.ButtonStyle.gray,
        custom_id="family_repay"
    )
    async def repay(self, interaction, button):

        await interaction.response.send_modal(
            PayDebtModal()
        )

    @discord.ui.button(
        label="📊 Список долгов",
        style=discord.ButtonStyle.secondary,
        custom_id="family_list"
    )
    async def debt_list(self, interaction, button):

        data = get_all_debts()

        if not data:

            return await interaction.response.send_message(
                "Нет долгов",
                ephemeral=True
            )

        text = (
            "📊 ДОЛГИ\n"
            "──────────────\n"
        )

        for uid, amount in data:

            text += f"<@{uid}> — {amount:,}\n"

        await interaction.response.send_message(
            text,
            ephemeral=True
        )

# ================= COMMAND =================
@bot.tree.command(
    name="menu",
    description="Открыть меню",
    guild=guild
)
async def menu(interaction: discord.Interaction):

    await interaction.response.send_message(
        "📊 СЕМЕЙНЫЙ БАНК",
        view=FamilyMenu()
    )

# ================= RUN =================
bot.run(TOKEN)
```
