import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import sqlite3


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

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

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
def is_head(member: discord.Member):
    return any(role.id == HEAD_ROLE_ID for role in member.roles)

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
    res = cursor.fetchone()
    return res[0] if res else 0

def add_debt(user_id, amount):
    new = get_debt(user_id) + amount
    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
    """, (str(user_id), new))
    conn.commit()

def reduce_debt(user_id, amount):

    current = get_debt(user_id)
    new = max(0, current - amount)

    # если долг погашен полностью
    if new == 0:
        cursor.execute(
            "DELETE FROM debts WHERE user_id=?",
            (str(user_id),)
        )

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

# sponsors
def add_sponsor(user_id, amount):
    cursor.execute("SELECT amount FROM sponsors WHERE user_id=?", (str(user_id),))
    res = cursor.fetchone()

    if res:
        cursor.execute("UPDATE sponsors SET amount=amount+? WHERE user_id=?", (amount, str(user_id)))
    else:
        cursor.execute("INSERT INTO sponsors VALUES (?, ?)", (str(user_id), amount))
    conn.commit()

def set_sponsor(user_id, amount):
    cursor.execute("INSERT OR REPLACE INTO sponsors VALUES (?, ?)", (str(user_id), amount))
    conn.commit()

def get_top_sponsors():
    cursor.execute("SELECT user_id, amount FROM sponsors ORDER BY amount DESC")
    return cursor.fetchall()

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

balance_message = None
top_message = None

# ================= UI UPDATE =================
async def update_balance_message():
    global balance_message
    channel = await bot.fetch_channel(CHANNEL_FAMILY_BALANCE)

    text = f"💰 **БАЛАНС СЕМЬИ**\n──────────────\n{get_balance():,}"

    messages = [msg async for msg in channel.history(limit=5)]
    for msg in messages:
        if msg.author == bot.user:
            await msg.edit(content=text)
            balance_message = msg
            return

    balance_message = await channel.send(text)
    await balance_message.pin()
    
# ================= ADMIN LOG =================
async def admin_log(action: str, user: discord.User, amount: int, admin: discord.Member):
    channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(
        title="🛠️ ДЕЙСТВИЕ АДМИНИСТРАЦИИ",
        color=discord.Color.dark_gray()
    )

    embed.add_field(name="📌 Действие", value=action, inline=False)
    embed.add_field(name="👤 Пользователь", value=user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="🛡️ Администратор", value=admin.mention, inline=False)

    embed.timestamp = datetime.now()

    await channel.send(embed=embed)

async def update_top_sponsors():
    global top_message
    channel = await bot.fetch_channel(CHANNEL_TOP_SPONSORS)

    data = get_top_sponsors()

    if not data:
        text = "🏆 ТОП СПОНСОРОВ ПУСТ"
    else:
        text = "🏆 ТОП СПОНСОРОВ\n──────────────\n"
        for i, (uid, amount) in enumerate(data, 1):
            text += f"{i}. <@{uid}> — {amount:,}\n"

    messages = [msg async for msg in channel.history(limit=5)]
    for msg in messages:
        if msg.author == bot.user:
            await msg.edit(content=text)
            top_message = msg
            return

    top_message = await channel.send(text)

# ================= READY =================
@bot.event
async def on_ready():
    bot.add_view(FamilyMenu())  # ✔ регистрируем persistent view

    await bot.tree.sync(guild=guild)

    print("BOT ONLINE")

    channel = await bot.fetch_channel(CHANNEL_REQUEST)

    messages = [msg async for msg in channel.history(limit=10)]

    # ищем уже существующее меню
    for msg in messages:
        if msg.author == bot.user and "СЕМЕЙНЫЙ БАНК" in msg.content:
            return

    # создаём новое меню
    msg = await channel.send(
        "📊 СЕМЕЙНЫЙ БАНК",
        view=FamilyMenu()
    )

    await msg.pin()

# ================= VIEWS =================
class DepositView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.done = False

    def is_head(self, interaction: discord.Interaction):
        return any(role.id == HEAD_ROLE_ID for role in interaction.user.roles)

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        # 🔒 защита от повторного нажатия
        if self.done:
            await interaction.response.send_message(
                "⚠️ Эта заявка уже обработана",
                ephemeral=True
            )
            return

        self.done = True  # блокируем повторные клики
        
        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может одобрять заявки",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # 💰 логика пополнения
        add_balance(self.amount)
        add_sponsor(self.user_id, self.amount)

        user = await bot.fetch_user(self.user_id)
        log_channel = await bot.fetch_channel(CHANNEL_DEPOSITS_LOG)

        embed = discord.Embed(title="💰 ПОПОЛНЕНИЕ ФОНДА", color=discord.Color.green())
        embed.add_field(name="👤", value=user.mention)
        embed.add_field(name="💸", value=f"{self.amount:,}")
        embed.add_field(name="🛡️", value=interaction.user.mention)

        await log_channel.send(embed=embed)

        # 🛠 админ лог (апрув)
        await admin_log(
            "Одобрено пополнение фонда",
            user,
            self.amount,
            interaction.user
        )

        # 🔄 обновления
        await update_balance_message()
        await update_top_sponsors()

        # 🧹 удаление заявки
        await interaction.message.delete()

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может откланять заявки",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        user = await bot.fetch_user(self.user_id)

        # 🛠 админ лог (отказ)
        await admin_log(
            "Отклонено пополнение фонда",
            user,
            self.amount,
            interaction.user
        )

        # 🧹 удаление заявки
        await interaction.message.delete()


class LoanView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.done = False

    def is_head(self, interaction: discord.Interaction):
        return any(role.id == HEAD_ROLE_ID for role in interaction.user.roles)

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        # 🔒 защита от повторного нажатия
        if self.done:
            await interaction.response.send_message(
                "⚠️ Эта заявка уже обработана",
                ephemeral=True
            )
            return

        self.done = True  # блокируем повторные клики
        
        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может одобрять заявки",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        
        # 💰 логика выдачи
        subtract_balance(self.amount)
        add_debt(self.user_id, self.amount)

        total = get_debt(self.user_id)
        user = await bot.fetch_user(self.user_id)

        channel = await bot.fetch_channel(CHANNEL_APPROVE)

        await channel.send(
            f"💸 НОВЫЙ ДОЛГ\n"
            f"{user.mention}\n"
            f"💸Сумма: {self.amount:,}\n"
            f"💸Остаток: {total:,}\n"
            f"🛡️Принял: {interaction.user.mention}"
        )

        # 🛠 админ лог (апрув)
        await admin_log(
            "Одобрена выдача долга",
            user,
            self.amount,
            interaction.user
        )
        
        await update_balance_message()
        
        # 🧹 удаление заявки
        await interaction.message.delete()

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        # 🔒 защита от повторного нажатия
        if self.done:
            await interaction.response.send_message(
                "⚠️ Эта заявка уже обработана",
                ephemeral=True
            )
            return

        self.done = True  # блокируем повторные клики
        
        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может откланять заявки",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        user = await bot.fetch_user(self.user_id)

        # 🛠 админ лог (отказ)
        await admin_log(
            "Отклонена выдача долга",
            user,
            self.amount,
            interaction.user
        )

        # 🧹 удаление заявки
        await interaction.message.delete()


class PayDebtView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.done = False

    def is_head(self, interaction: discord.Interaction):
        return any(role.id == HEAD_ROLE_ID for role in interaction.user.roles)

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может одобрять заявки",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        
        # 💰 логика погашения
        reduce_debt(self.user_id, self.amount)
        add_balance(self.amount)

        total = get_debt(self.user_id)
        user = await bot.fetch_user(self.user_id)

        channel = await bot.fetch_channel(CHANNEL_APPROVE)

        await channel.send(
            f"💰 ПОГАШЕНИЕ\n"
            f"{user.mention}\n"
            f"💸Внесено: {self.amount:,}\n"
            f"💸Остаток: {total:,}\n"
            f"🛡️Принял: {interaction.user.mention}"
        )

        # 🛠 админ лог (апрув)
        await admin_log(
            "Одобрено погашение долга",
            user,
            self.amount,
            interaction.user
        )

        await update_balance_message()

        # 🧹 удаление заявки
        await interaction.message.delete()

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        # 🔒 проверка роли
        if not self.is_head(interaction):
            await interaction.response.send_message(
                "❌ Только Head может откланять заявки",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()

        user = await bot.fetch_user(self.user_id)
        # 🛠 админ лог (отказ)
        await admin_log(
            "Отклонено погашение долга",
            user,
            self.amount,
            interaction.user
        )
        
        # 🧹 удаление заявки
        await interaction.message.delete()
        
class FamilyMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💰 Добровольный взнос",
        style=discord.ButtonStyle.green,
        custom_id="family:deposit"
    )
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositModal())

    @discord.ui.button(
        label="💸 Взять в долг",
        style=discord.ButtonStyle.blurple,
        custom_id="family:loan"
    )
    async def loan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LoanModal())

    @discord.ui.button(
        label="📥 Погасить долг",
        style=discord.ButtonStyle.gray,
        custom_id="family:repay"
    )
    async def repay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PayDebtModal())

    @discord.ui.button(
        label="📊 Список долгов",
        style=discord.ButtonStyle.secondary,
        custom_id="family:debts"
    )
    async def debts(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = get_all_debts()

        if not data:
            await interaction.response.send_message("Нет долгов", ephemeral=True)
            return

        text = "📊 ДОЛГИ\n──────────────\n"
        for uid, amount in data:
            text += f"<@{uid}> — {amount:,}\n"

        await interaction.response.send_message(text, ephemeral=True)
        
# ================= MODALS ===================
class DepositModal(discord.ui.Modal, title="Добровольный взнос"):
    amount = discord.ui.TextInput(label="Сумма", required=True)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except:
            await interaction.response.send_message("❌ Неверная сумма", ephemeral=True)
            return

        await interaction.response.send_message(
            "📎 Отправь картинку следующим сообщением (можно просто файл или Ctrl+V)",
            ephemeral=True
        )

        def check(msg: discord.Message):
            return (
                msg.author.id == interaction.user.id and
                msg.channel.id == interaction.channel.id
            )

        try:
            msg = await interaction.client.wait_for(
                "message",
                check=check,
                timeout=60
            )

            # 🔥 ВАЖНО: ждём именно attachment (а не текст)
            if not msg.attachments:
                await interaction.followup.send("❌ Ты не отправил файл", ephemeral=True)
                return

            attachment = msg.attachments[0]

            channel = await interaction.client.fetch_channel(CHANNEL_REPORT)

            embed = discord.Embed(title="💰 ЗАЯВКА НА ПОПОЛНЕНИЕ")
            embed.add_field(name="👤", value=interaction.user.mention)
            embed.add_field(name="💸", value=f"{amount:,}")
            embed.set_image(url=attachment.url)

            await channel.send(
                embed=embed,
                view=DepositView(interaction.user.id, amount)
            )

            try:
                await msg.delete()
            except:
                pass

        except asyncio.TimeoutError:
            await interaction.followup.send("⏳ Время вышло", ephemeral=True)
        
class LoanModal(discord.ui.Modal, title="Взять в долг"):
    amount = discord.ui.TextInput(label="Сумма", required=True)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)

        except:
            await interaction.response.send_message(
                "❌ Введи корректное число",
                ephemeral=True
            )
            return

        try:
            channel = await interaction.client.fetch_channel(CHANNEL_REPORT)

            embed = discord.Embed(
                title="💸 ЗАЯВКА НА ДОЛГ",
                color=discord.Color.blue()
            )
            embed.add_field(name="👤", value=interaction.user.mention)
            embed.add_field(name="💰", value=str(amount))

            await channel.send(
                embed=embed,
                view=LoanView(interaction.user.id, amount)
            )

            await interaction.response.send_message(
                "✅ Заявка отправлена",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Ошибка: {e}",
                ephemeral=True
            )
        
class PayDebtModal(discord.ui.Modal, title="Погашение долга"):
    amount = discord.ui.TextInput(label="Сумма", required=True)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except:
            await interaction.response.send_message("❌ Неверная сумма", ephemeral=True)
            return

        debt = get_debt(interaction.user.id)

        await interaction.response.send_message(
            f"💡 Долг: {debt:,}\n📎 Отправь скриншот (Ctrl+V или файл)",
            ephemeral=True
        )

        def check(msg: discord.Message):
            return (
                msg.author.id == interaction.user.id
                and msg.channel.id == interaction.channel.id
                and (msg.attachments or msg.content.startswith("http"))
            )

        try:
            msg = await interaction.client.wait_for(
                "message",
                check=check,
                timeout=60
            )

            attachment = msg.attachments[0] if msg.attachments else None

            image_url = None

            # 📌 если файл
            if attachment:
                image_url = attachment.url

            # 📌 если вставили ссылку
            elif msg.content.startswith("http"):
                image_url = msg.content

            channel = await interaction.client.fetch_channel(CHANNEL_REPORT)

            embed = discord.Embed(title="📥 ПОГАШЕНИЕ")
            embed.add_field(name="👤", value=interaction.user.mention)
            embed.add_field(name="💰", value=str(amount))

            if image_url:
                embed.set_image(url=image_url)

            await channel.send(
                embed=embed,
                view=PayDebtView(interaction.user.id, amount)
            )

            # 🧹 удаляем сообщение со скрином
            try:
                await msg.delete()
            except:
                pass

        except:
            await interaction.followup.send("⏳ Время вышло", ephemeral=True)
        
# ================= COMMANDS =================
@bot.tree.command(name="deposit_to_family", description="Добровольный взнос на счет семьи", guild=guild)
async def deposit(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(title="💰 ЗАЯВКА НА ПОПОЛНЕНИЕ", color=discord.Color.green())
    embed.add_field(name="👤", value=interaction.user.mention)
    embed.add_field(name="💸", value=f"{amount:,}")
    embed.set_image(url=screenshot.url)

    await channel.send(embed=embed, view=DepositView(interaction.user.id, amount))
    await interaction.response.send_message("OK", ephemeral=True)

@bot.tree.command(name="loan", description="Запросить выдачу долга у семьи", guild=guild)
async def loan(interaction: discord.Interaction, amount: int):

    channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(title="💸 ЗАЯВКА НА ДОЛГ", color=discord.Color.blue())
    embed.add_field(name="👤", value=interaction.user.mention)
    embed.add_field(name="💰", value=f"{amount:,}")

    await channel.send(embed=embed, view=LoanView(interaction.user.id, amount))
    await interaction.response.send_message("OK", ephemeral=True)

@bot.tree.command(name="pay_debt", description="Погасить частично/полностью долг", guild=guild)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(title="📥 ПОГАШЕНИЕ", color=discord.Color.orange())
    embed.add_field(name="👤", value=interaction.user.mention)
    embed.add_field(name="💰", value=f"{amount:,}")
    embed.set_image(url=screenshot.url)

    await channel.send(embed=embed, view=PayDebtView(interaction.user.id, amount))
    await interaction.response.send_message("OK", ephemeral=True)

@bot.tree.command(name="all_loans", description="Получить список должников", guild=guild)
async def all_loans(interaction: discord.Interaction):

    data = get_all_debts()

    if not data:
        await interaction.response.send_message("Нет долгов", ephemeral=True)
        return

    text = "📊 ДОЛЖНИКИ\n──────────────\n"

    for uid, amount in data:
        text += f"<@{uid}> — {amount:,}\n"

    await interaction.response.send_message(text, ephemeral=True)

@bot.tree.command(name="edit_family_bank", description="Изменить баланс фонда семьи", guild=guild)
async def edit_family_bank(interaction: discord.Interaction, amount: int):

    set_balance(amount)
    await update_balance_message()

    await interaction.response.send_message("OK", ephemeral=True)

@bot.tree.command(name="edit_sponsor", description="НЕ ИСПОЛЬЗОВАТЬ!!!", guild=guild)
async def edit_sponsor_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):

    set_sponsor(user.id, amount)
    await update_top_sponsors()

    await interaction.response.send_message("OK", ephemeral=True)
    
@bot.tree.command(name="menu", description="Открыть семейное меню", guild=guild)
async def menu(interaction: discord.Interaction):
    await interaction.response.send_message(
        "📊 СЕМЕЙНЫЙ БАНК",
        view=FamilyMenu(),
        ephemeral=False
    )
# ================= RUN =================
bot.run(TOKEN)
