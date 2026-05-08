import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import sqlite3
import os
import asyncio

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

HEAD_ROLE_ID = 1345267230300049408
GUILD_ID = 1345261255300218992

CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684
CHANNEL_FAMILY_BALANCE = 1501339448250601472
CHANNEL_TOP_SPONSORS = 1447514330252836906

PASSPORT_CHANNEL = 1447305826644525136

# ================= COLORS =================
BANK_COLOR = discord.Color.from_rgb(0, 255, 140)

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

active_uploads = {}
BANK_MESSAGE_ID = None

# ================= DB =================
conn = sqlite3.connect("/data/family.db")
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS bank_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    amount INTEGER,
    user_id TEXT,
    time TEXT
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS passports (
    user_id TEXT PRIMARY KEY,
    passport TEXT UNIQUE
)
""")
conn.commit()

# ================= DB FUNCS =================
def add_passport(uid, passport):

    cursor.execute("""
    INSERT OR REPLACE INTO passports
    VALUES (?, ?)
    """, (str(uid), passport))

    conn.commit()


def delete_passport(uid):

    cursor.execute("""
    DELETE FROM passports
    WHERE user_id=?
    """, (str(uid),))

    conn.commit()

def get_all_passports():
    cursor.execute("""
    SELECT user_id, passport
    FROM passports
    """)
    return cursor.fetchall()

def get_passport(uid):

    cursor.execute("""
    SELECT passport FROM passports
    WHERE user_id=?
    """, (str(uid),))

    row = cursor.fetchone()

    return row[0] if row else None

def passport_embed():

    return discord.Embed(
        title="🪪 РЕЕСТР WAYNE INC.",
        description=(
            "```fix\n"
            "ПАСПОРТНАЯ СИСТЕМА GTA RP\n"
            "```\n\n"

            "────────────────────────────\n"
            "⚙️ Используйте кнопки ниже"
        ),
        color=discord.Color.dark_blue()
    )

def add_log(action, uid, amount):
    cursor.execute("""
    INSERT INTO bank_logs (action, user_id, amount, time)
    VALUES (?, ?, ?, ?)
    """, (
        action,
        str(uid),
        amount,
        datetime.now().strftime("%d.%m %H:%M")
    ))
    conn.commit()

def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)
    
def get_balance():
    cursor.execute("SELECT balance FROM family_bank WHERE id=1")
    return cursor.fetchone()[0]

def set_balance(v):
    cursor.execute("UPDATE family_bank SET balance=? WHERE id=1", (v,))
    conn.commit()

def add_balance(v):
    set_balance(get_balance() + v)

def subtract_balance(v):
    set_balance(max(0, get_balance() - v))

def get_debt(uid):
    cursor.execute("SELECT amount FROM debts WHERE user_id=?", (str(uid),))
    r = cursor.fetchone()
    return r[0] if r else 0

def add_debt(uid, v):
    cursor.execute("""
    INSERT INTO debts (user_id, amount)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
    """, (str(uid), get_debt(uid) + v))
    conn.commit()

def reduce_debt(uid, v):
    cur = get_debt(uid)
    new = max(0, cur - v)

    if new == 0:
        cursor.execute("DELETE FROM debts WHERE user_id=?", (str(uid),))
    else:
        cursor.execute("""
        INSERT INTO debts (user_id, amount)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
        """, (str(uid), new))

    conn.commit()

def get_all_debts():
    cursor.execute("SELECT user_id, amount FROM debts")
    return cursor.fetchall()

def add_sponsor(uid, v):
    cursor.execute("SELECT amount FROM sponsors WHERE user_id=?", (str(uid),))
    r = cursor.fetchone()

    if r:
        cursor.execute("UPDATE sponsors SET amount=amount+? WHERE user_id=?", (v, str(uid)))
    else:
        cursor.execute("INSERT INTO sponsors VALUES (?, ?)", (str(uid), v))

    conn.commit()

def set_sponsor(uid, v):
    cursor.execute("INSERT OR REPLACE INTO sponsors VALUES (?, ?)", (str(uid), v))
    conn.commit()

def get_top_sponsors():
    cursor.execute("SELECT user_id, amount FROM sponsors ORDER BY amount DESC")
    return cursor.fetchall()

# ================= UI =================
def bank_embed():
    debts = get_all_debts()
    top = get_top_sponsors()

    top_text = "Нет данных"
    if top:
        top_text = f"<@{top[0][0]}> — 💰 ${top[0][1]:,}"

    return discord.Embed(
        title="🏦 БАНКОВСКИЙ ТЕРМИНАЛ WAYNE INC.",
        description=(
            "```css\nФИНАНСОВАЯ СИСТЕМА WAYNE INC.\n```\n\n"

            "💰 **БАЛАНС СЕМЬИ:** "
            f"${get_balance():,}\n"
            "────────────────────────────\n\n"

            "📊 **АКТИВНЫЕ ДОЛГИ:** "
            f"{len(debts)}\n"
            "────────────────────────────\n\n"

            "🏆 **ТОП СПОНСОР:** "
            f"{top_text}\n"
            "────────────────────────────\n\n"

            "⚙️ *Выберите действие ниже*"
        ),
        color=BANK_COLOR
    )

class PassportUI(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="➕ Добавить",
        style=discord.ButtonStyle.green,
        custom_id="passport_add"
    )
    async def add_btn(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "👤 Выберите игрока",
            view=AddPassportView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="❌ Удалить",
        style=discord.ButtonStyle.red,
        custom_id="passport_delete"
    )
    async def del_btn(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            DeletePassportModal()
        )

    @discord.ui.button(
        label="🔍 Найти",
        style=discord.ButtonStyle.blurple,
        custom_id="passport_find"
    )
    async def find_btn(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            FindPassportModal()
        )

    @discord.ui.button(
        label="📋 Реестр",
        style=discord.ButtonStyle.gray,
        custom_id="passport_registry"
    )
    async def registry_btn(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        data = get_all_passports()

        if not data:
            return await interaction.response.send_message(
                "📭 Паспортов нет",
                ephemeral=True
            )

        # сортировка по имени на сервере
        members = []

        for uid, passport in data:
            member = interaction.guild.get_member(int(uid))

            if member:
                members.append((member.display_name, member.mention, passport))

        members.sort(key=lambda x: x[0].lower())

        desc = "\n".join([
            f"👤 {name} | {mention} — 🪪 #{passport}"
            for name, mention, passport in members
        ])

        embed = discord.Embed(
            title="📋 ПАСПОРТНЫЙ РЕЕСТР",
            description=desc,
            color=discord.Color.dark_blue()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

async def resolve_member(guild, text):

    text = text.strip()

    # @mention
    if text.startswith("<@") and text.endswith(">"):

        try:
            uid = int(
                text.replace("<@", "")
                .replace(">", "")
                .replace("!", "")
            )

            member = guild.get_member(uid)

            if member:
                return member

        except:
            pass

    # display name / username
    for member in guild.members:

        if text.lower() in member.display_name.lower():
            return member

        if text.lower() in member.name.lower():
            return member
        
    return None

class MemberSelect(discord.ui.UserSelect):

    def __init__(self):
        super().__init__(
            placeholder="Выберите игрока...",
            min_values=1,
            max_values=1,
            custom_id="passport_member_select"
        )
        
    async def callback(self, interaction):

        member = self.values[0]

        await interaction.response.send_modal(
            AddPassportModal(member)
        )


class AddPassportView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(MemberSelect())


class AddPassportModal(
    discord.ui.Modal,
    title="Добавить паспорт"
):

    def __init__(self, member):
        super().__init__()

        self.member = member

    passport = discord.ui.TextInput(
        label="Номер паспорта"
    )

    async def on_submit(self, i):

        passport = self.passport.value.strip()

        if (
            not passport.isdigit()
            or len(passport) != 6
        ):
            return await i.response.send_message(
                "❌ Паспорт должен быть 6-значным",
                ephemeral=True
            )

        add_passport(self.member.id, passport)

        await i.response.send_message(
            embed=discord.Embed(
                title="✅ ПАСПОРТ ДОБАВЛЕН",
                description=(
                    f"👤 {self.member.mention}\n"
                    f"🪪 #{passport}"
                ),
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        
class FindPassportModal(
    discord.ui.Modal,
    title="Найти паспорт"
):

    user = discord.ui.TextInput(
        label="Игрок"
    )

    async def on_submit(self, i):

        member = await resolve_member(
            i.guild,
            self.user.value
        )

        if not member:

            return await i.response.send_message(
                "❌ Игрок не найден",
                ephemeral=True
            )

        passport = get_passport(member.id)

        if not passport:

            return await i.response.send_message(
                "❌ Паспорт не найден",
                ephemeral=True
            )

        await i.response.send_message(
            embed=discord.Embed(
                title="🪪 ПАСПОРТ ГРАЖДАНИНА",
                description=(
                    f"👤 {member.mention}\n"
                    f"🪪 #{passport}"
                ),
                color=discord.Color.blurple()
            ),
            ephemeral=True
        )

class DeletePassportModal(
    discord.ui.Modal,
    title="Удалить паспорт"
):

    user = discord.ui.TextInput(
        label="Игрок"
    )

    async def on_submit(self, i):

        member = await resolve_member(
            i.guild,
            self.user.value
        )

        if not member:

            return await i.response.send_message(
                "❌ Игрок не найден",
                ephemeral=True
            )

        passport = get_passport(member.id)

        if not passport:

            return await i.response.send_message(
                "❌ Паспорт не найден",
                ephemeral=True
            )

        await i.response.send_message(
            embed=discord.Embed(
                title="⚠️ ПОДТВЕРЖДЕНИЕ",
                description=(
                    f"👤 {member.mention}\n"
                    f"🪪 #{passport}\n\n"
                    "Удалить паспорт?"
                ),
                color=discord.Color.orange()
            ),
            view=DeletePassportConfirm(member.id),
            ephemeral=True
        )
        
class DeletePassportConfirm(discord.ui.View):

    def __init__(self, uid):
        super().__init__(timeout=30)
        self.uid = uid

    @discord.ui.button(
        label="✅ Да",
        style=discord.ButtonStyle.green
    )
    async def yes(self, i, b):

        delete_passport(self.uid)

        await i.response.edit_message(
            embed=discord.Embed(
                title="🗑️ ПАСПОРТ УДАЛЁН",
                description=f"<@{self.uid}>",
                color=discord.Color.red()
            ),
            view=None
        )

    @discord.ui.button(
        label="❌ Нет",
        style=discord.ButtonStyle.gray
    )
    async def no(self, i, b):

        await i.response.edit_message(
            embed=discord.Embed(
                title="❌ УДАЛЕНИЕ ОТМЕНЕНО",
                color=discord.Color.dark_gray()
            ),
            view=None
        )

class BankUI(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 Взнос", style=discord.ButtonStyle.green)
    async def dep(self, i, b):
        await i.response.send_modal(DepositModal())

    @discord.ui.button(label="💸 Кредит", style=discord.ButtonStyle.blurple)
    async def loan(self, i, b):
        await i.response.send_modal(LoanModal())

    @discord.ui.button(label="📥 Погашение", style=discord.ButtonStyle.gray)
    async def repay(self, i, b):
        await i.response.send_modal(PayDebtModal())

    @discord.ui.button(label="📊 Долги", style=discord.ButtonStyle.secondary)
    async def debts(self, i, b):

        data = get_all_debts()
        desc = "\n".join([f"<@{u}> — 💸 ${a:,}" for u,a in data]) or "Нет долгов"

        await i.response.send_message(
            embed=discord.Embed(
                title="📊 АКТИВНЫЕ ДОЛГИ",
                description=desc,
                color=BANK_COLOR
            ),
            ephemeral=True
        )

    @discord.ui.button(label="🏆 Топ", style=discord.ButtonStyle.success)
    async def top(self, i, b):

        data = get_top_sponsors()
        desc = "\n".join([f"{x+1}. <@{u}> — 💰 ${a:,}" for x,(u,a) in enumerate(data)]) or "Пусто"

        await i.response.send_message(
            embed=discord.Embed(
                title="🏆 ТОП СПОНСОРОВ",
                description=desc,
                color=BANK_COLOR
            ),
            ephemeral=True
        )
    @discord.ui.button(label="📜 Логи", style=discord.ButtonStyle.gray)
    async def logs(self, i, b):

        cursor.execute("""
        SELECT action, amount, user_id, time
        FROM bank_logs
        ORDER BY id DESC
        LIMIT 10
        """)

        data = cursor.fetchall()

        desc = "\n".join([
            f"[{t}] {a} | <@{u}> | ${v:,}"
            for a,v,u,t in data
        ]) or "Нет логов"

        await i.response.send_message(
            embed=discord.Embed(
                title="📜 БАНКОВСКИЕ ЛОГИ",
                description=desc,
                color=BANK_COLOR
            ),
            ephemeral=True
        )

    @discord.ui.button(label="📈 График", style=discord.ButtonStyle.blurple)
    async def graph(self, i, b):
        import matplotlib.pyplot as plt
        import io

        cursor.execute("""
        SELECT balance, rowid FROM family_bank
        ORDER BY rowid DESC LIMIT 7
        """)

        data = cursor.fetchall()[::-1]

        if not data:
            return await i.response.send_message("Нет данных", ephemeral=True)

        values = [x[0] for x in data]
        labels = list(range(len(values)))

        plt.figure()
        plt.plot(labels, values)

        plt.title("BANK BALANCE 7D")

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)

        await i.response.send_message(
            file=discord.File(buf, "graph.png"),
            ephemeral=True
        )
# ================= DASHBOARD =================
async def update_bank():
    global BANK_MESSAGE_ID

    ch = await bot.fetch_channel(CHANNEL_REQUEST)

    embed = bank_embed()

    if BANK_MESSAGE_ID:
        try:
            msg = await ch.fetch_message(BANK_MESSAGE_ID)
            await msg.edit(embed=embed, view=BankUI())
            return
        except:
            pass

    msg = await ch.send(embed=embed, view=BankUI())
    await msg.pin()
    BANK_MESSAGE_ID = msg.id

# ================= PASSPORT TERMINAL =================
PASSPORT_MESSAGE_ID = None

async def update_passport_terminal():

    global PASSPORT_MESSAGE_ID

    ch = await bot.fetch_channel(PASSPORT_CHANNEL)

    embed = passport_embed()

    # пытаемся обновить существующий терминал
    if PASSPORT_MESSAGE_ID:

        try:
            msg = await ch.fetch_message(
                PASSPORT_MESSAGE_ID
            )

            await msg.edit(
                embed=embed,
                view=PassportUI()
            )

            return

        except:
            PASSPORT_MESSAGE_ID = None

    # ищем терминал среди последних сообщений
    async for m in ch.history(limit=20):

        if (
            m.author == bot.user
            and m.embeds
            and "ГОСУДАРСТВЕННЫЙ РЕЕСТР"
            in m.embeds[0].title
        ):

            PASSPORT_MESSAGE_ID = m.id

            try:
                await m.edit(
                    embed=embed,
                    view=PassportUI()
                )

                return

            except:
                pass

    # если терминала нет — создаем заново
    msg = await ch.send(
        embed=embed,
        view=PassportUI()
    )

    await msg.pin()

    PASSPORT_MESSAGE_ID = msg.id

# ================= AUTO TERMINAL CHECK =================
@tasks.loop(seconds=30)
async def terminal_guard():

    global BANK_MESSAGE_ID

    try:
        ch = await bot.fetch_channel(CHANNEL_REQUEST)

        # если ID нет — создать заново
        if not BANK_MESSAGE_ID:
            await update_bank()
            return

        try:
            await ch.fetch_message(BANK_MESSAGE_ID)

        except:

            # сообщение удалили -> создать новое
            BANK_MESSAGE_ID = None
            await update_bank()

    except Exception as e:
        print("TERMINAL GUARD ERROR:", e)
        
# ================= CALLBACK UPLOAD =================
@bot.event
async def on_message(msg):
    await bot.process_commands(msg)

    if msg.author.bot:
        return

    uid = msg.author.id

    if uid not in active_uploads:
        return

    state = active_uploads[uid]

    if msg.channel.id != state["channel_id"]:
        return

    img = None

    if msg.attachments:
        img = msg.attachments[0].url
    elif msg.content.startswith("http"):
        img = msg.content

    if not img:
        return

    loading = await msg.channel.send(
        "📤 Обрабатываем изображение...\n"
        "⏳ Подождите 10 секунд"
    )

    await asyncio.sleep(10)

    try:
        await state["callback"](msg, img)

        await loading.edit(
            content="✅ Скриншот успешно загружен"
        )

    except Exception as e:

        await loading.edit(
            content=f"❌ Ошибка загрузки: {e}"
        )

    await asyncio.sleep(3)

    try:
        await loading.delete()
    except:
        pass

    try:
        await msg.delete()
    except:
        pass

    del active_uploads[uid]

# ================= VIEWS (APPROVALS) =================
class DepositView(discord.ui.View):
    def __init__(self, uid, amount):
        super().__init__()
        self.uid = uid
        self.amount = amount

    @discord.ui.button(label="✔", style=discord.ButtonStyle.green)
    async def ok(self, i, b):
        add_balance(self.amount)
        add_sponsor(self.uid, self.amount)

        add_log("DEPOSIT", self.uid, self.amount)
        
        await update_bank()
        await i.message.delete()

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
    async def reject(self, i, b):

        if not is_head(i.user):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)

        add_log("ОТКЛОНЁН ПЛАТЁЖ", self.uid, self.amount)

        await admin_log(
            "ОТКЛОНЁН ПЛАТЁЖ",
            await bot.fetch_user(self.uid),
            self.amount,
            i.user
            )
        
        await i.message.delete()

class LoanView(discord.ui.View):
    def __init__(self, uid, amount):
        super().__init__()
        self.uid = uid
        self.amount = amount
        
    @discord.ui.button(label="✔", style=discord.ButtonStyle.green)
    async def ok(self, i, b):
        subtract_balance(self.amount)
        add_debt(self.uid, self.amount)

        add_log("LOAN", self.uid, self.amount)
        
        await update_bank()
        await i.message.delete()
        
    @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
    async def reject(self, i, b):

        if not is_head(i.user):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)

        add_log("ОТКЛОНЁН КРЕДИТ", self.uid, self.amount)
        
        await admin_log(
            "ОТКЛОНЁН КРЕДИТ",
            await bot.fetch_user(self.uid),
            self.amount,
            i.user
        )

        await i.message.delete()
    
class PayDebtView(discord.ui.View):
    def __init__(self, uid, amount):
        super().__init__()
        self.uid = uid
        self.amount = amount

    @discord.ui.button(label="✔", style=discord.ButtonStyle.green)
    async def ok(self, i, b):
        current = get_debt(self.uid)
        paid = min(self.amount, current)

        reduce_debt(self.uid, paid)
        add_balance(paid)

        add_log("REPAY", self.uid, paid)

        await update_bank()
        await i.message.delete()

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
    async def reject(self, i, b):

        if not is_head(i.user):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)

        add_log("ОТКЛОНЁН ПЛАТЁЖ", self.uid, self.amount)
        
        await admin_log(
            "ОТКЛОНЁН ПЛАТЁЖ",
            await bot.fetch_user(self.uid),
            self.amount,
            i.user
        )

        await i.message.delete()
    
# ================= MODALS =================
class DepositModal(discord.ui.Modal, title="Deposit"):
    amount = discord.ui.TextInput(label="Amount")

    async def on_submit(self, i):
        uid = i.user.id

        async def cb(msg, img):
            ch = await bot.fetch_channel(CHANNEL_REPORT)

            await ch.send(embed=discord.Embed(
                title="💰 DEPOSIT",
                description=f"<@{uid}> {self.amount.value}",
                color=BANK_COLOR
            ).set_image(url=img), view=DepositView(uid, int(self.amount.value)))

        active_uploads[uid] = {"callback": cb, "channel_id": i.channel.id}

        await i.response.send_message("Send screenshot", ephemeral=True)

class LoanModal(discord.ui.Modal, title="Loan"):
    amount = discord.ui.TextInput(label="Amount")

    async def on_submit(self, i):
        ch = await bot.fetch_channel(CHANNEL_REPORT)

        await ch.send(embed=discord.Embed(
            title="💸 LOAN REQUEST",
            description=f"{i.user.mention} {self.amount.value}",
            color=BANK_COLOR
        ), view=LoanView(i.user.id, int(self.amount.value)))

        await i.response.send_message("Sent", ephemeral=True)

class PayDebtModal(discord.ui.Modal, title="Repay"):
    amount = discord.ui.TextInput(label="Amount")

    async def on_submit(self, i):
        uid = i.user.id

        async def cb(msg, img):
            ch = await bot.fetch_channel(CHANNEL_REPORT)

            await ch.send(embed=discord.Embed(
                title="📥 REPAY",
                description=f"<@{uid}> {self.amount.value}",
                color=BANK_COLOR
            ).set_image(url=img), view=PayDebtView(uid, int(self.amount.value)))

        active_uploads[uid] = {"callback": cb, "channel_id": i.channel.id}

        await i.response.send_message("Send screenshot", ephemeral=True)

# ================= READY =================
@bot.command()
async def setbank(ctx, amount: int):

    if ctx.channel.id != CHANNEL_REPORT:
        return

    set_balance(amount)

    await update_bank()

    await ctx.send(
        embed=discord.Embed(
            title="🏦 BANK OVERRIDE",
            description=f"Баланс установлен: ${amount:,}",
            color=BANK_COLOR
        )
    )
@bot.event
async def on_ready():
    bot.add_view(PassportUI())
    bot.add_view(AddPassportView())
    
    await bot.tree.sync(guild=guild)
    print("BANK ONLINE")
    
    await update_bank()
    await update_passport_terminal()

    if not terminal_guard.is_running():
        terminal_guard.start()

# ================= AUTO RESTORE TERMINALS =================
@tasks.loop(seconds=30)
async def terminal_guard():

    try:
        await update_bank()
    except:
        pass

    try:
        await update_passport_terminal()
    except:
        pass
        
# ================= RUN =================
bot.run(TOKEN)
