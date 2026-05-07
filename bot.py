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

CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684
CHANNEL_FAMILY_BALANCE = 1501339448250601472
CHANNEL_TOP_SPONSORS = 1447514330252836906

# ================= COLORS =================
BANK_COLOR = discord.Color.from_rgb(0, 255, 140)

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

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

# ================= DB FUNCS =================
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
        title="🏦 БАНКОВСКИЙ ТЕРМИНАЛ WAYNE ENT.",
        description=(
            "```css\nФИНАНСОВАЯ СИСТЕМА WAYNE ENT.\n```\n\n"

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

    await state["callback"](msg, img)

    await msg.delete()
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
    await bot.tree.sync(guild=guild)
    print("BANK ONLINE")
    await update_bank()

# ================= RUN =================
bot.run(TOKEN)
