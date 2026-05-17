from datetime import datetime
import io
import discord
from discord.ext import commands

from core.utils import clear_channel, is_head, parse_positive_int, safe_pin

BANK_COLOR = discord.Color.from_rgb(0, 255, 140)


class BankService:
    def __init__(self, db):
        self.db = db

    def balance(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT balance FROM family_bank WHERE id=1").fetchone()[0]

    def set_balance(self, value: int) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE family_bank SET balance=? WHERE id=1", (max(0, value),))

    def add_balance(self, value: int) -> None:
        self.set_balance(self.balance() + value)

    def subtract_balance(self, value: int) -> None:
        self.set_balance(self.balance() - value)

    def debt(self, uid: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT amount FROM debts WHERE user_id=?", (str(uid),)).fetchone()
            return row[0] if row else 0

    def add_debt(self, uid: int, value: int) -> None:
        new_amount = self.debt(uid) + value
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO debts (user_id, amount) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount
            """, (str(uid), new_amount))

    def reduce_debt(self, uid: int, value: int) -> int:
        current = self.debt(uid)
        paid = min(value, current)
        new_amount = max(0, current - paid)
        with self.db.connect() as conn:
            if new_amount == 0:
                conn.execute("DELETE FROM debts WHERE user_id=?", (str(uid),))
            else:
                conn.execute("UPDATE debts SET amount=? WHERE user_id=?", (new_amount, str(uid)))
        return paid

    def debts(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT user_id, amount FROM debts ORDER BY amount DESC").fetchall()

    def add_sponsor(self, uid: int, value: int) -> None:
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO sponsors (user_id, amount) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET amount=sponsors.amount + EXCLUDED.amount
            """, (str(uid), value))

    def sponsors(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT user_id, amount FROM sponsors ORDER BY amount DESC").fetchall()

    def add_log(self, action: str, uid: int, amount: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO bank_logs (action, amount, user_id, time) VALUES (?, ?, ?, ?)",
                (action, amount, str(uid), datetime.now().strftime("%d.%m %H:%M")),
            )

    def logs(self, limit: int = 10):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT action, amount, user_id, time FROM bank_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()


def bank_embed(service: BankService) -> discord.Embed:
    debts = service.debts()
    top = service.sponsors()[:3]
    top_text = "\n".join([f"{idx+1}. <@{row['user_id']}> — 💰 ${row['amount']:,}" for idx, row in enumerate(top)]) or "Нет данных"
    return discord.Embed(
        title="🏦 БАНКОВСКИЙ ТЕРМИНАЛ WAYNE INC.",
        description=(
            "```css\nФИНАНСОВАЯ СИСТЕМА WAYNE INC.\n```\n\n"
            f"💰 **БАЛАНС СЕМЬИ:** ${service.balance():,}\n"
            "────────────────────────────\n\n"
            f"📊 **АКТИВНЫЕ ДОЛГИ:** {len(debts)}\n"
            "────────────────────────────\n\n"
            f"🏆 **ТОП-3 СПОНСОРОВ:**\n{top_text}\n"
            "────────────────────────────\n\n"
            "⚙️ *Выберите действие ниже*"
        ),
        color=BANK_COLOR,
    )


class BankUI(discord.ui.View):
    def __init__(self, cog: "BankCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="💰 Взнос", style=discord.ButtonStyle.green, custom_id="bank_deposit")
    async def dep(self, i, b):
        await i.response.send_modal(DepositModal(self.cog))

    @discord.ui.button(label="💸 Кредит", style=discord.ButtonStyle.blurple, custom_id="bank_loan")
    async def loan(self, i, b):
        await i.response.send_modal(LoanModal(self.cog))

    @discord.ui.button(label="📥 Погашение", style=discord.ButtonStyle.gray, custom_id="bank_repay")
    async def repay(self, i, b):
        await i.response.send_modal(PayDebtModal(self.cog))

    @discord.ui.button(label="📊 Долги", style=discord.ButtonStyle.secondary, custom_id="bank_debts")
    async def debts(self, i, b):
        data = self.cog.service.debts()
        desc = "\n".join([f"<@{r['user_id']}> — 💸 ${r['amount']:,}" for r in data]) or "Нет долгов"
        await i.response.send_message(embed=discord.Embed(title="📊 АКТИВНЫЕ ДОЛГИ", description=desc, color=BANK_COLOR), ephemeral=True)

    @discord.ui.button(label="🏆 Топ", style=discord.ButtonStyle.success, custom_id="bank_top")
    async def top(self, i, b):
        data = self.cog.service.sponsors()
        desc = "\n".join([f"{x+1}. <@{r['user_id']}> — 💰 ${r['amount']:,}" for x, r in enumerate(data)]) or "Пусто"
        await i.response.send_message(embed=discord.Embed(title="🏆 ТОП СПОНСОРОВ", description=desc, color=BANK_COLOR), ephemeral=True)

    @discord.ui.button(label="📜 Логи", style=discord.ButtonStyle.gray, custom_id="bank_logs")
    async def logs(self, i, b):
        data = self.cog.service.logs()
        desc = "\n".join([f"[{r['time']}] {r['action']} | <@{r['user_id']}> | ${r['amount']:,}" for r in data]) or "Нет логов"
        await i.response.send_message(embed=discord.Embed(title="📜 БАНКОВСКИЕ ЛОГИ", description=desc, color=BANK_COLOR), ephemeral=True)

    @discord.ui.button(label="📈 График", style=discord.ButtonStyle.blurple, custom_id="bank_graph")
    async def graph(self, i, b):
        import matplotlib.pyplot as plt
        logs = self.cog.service.logs(30)
        values = [self.cog.service.balance()]
        for _ in logs[:6]:
            values.append(self.cog.service.balance())
        values = values[::-1]
        plt.figure()
        plt.plot(list(range(len(values))), values)
        plt.title("BANK BALANCE")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        await i.response.send_message(file=discord.File(buf, "graph.png"), ephemeral=True)


class ApprovalView(discord.ui.View):
    action_name = "ACTION"
    log_accept = "ACTION"
    log_reject = "ОТКЛОНЕНО"

    def __init__(self, cog: "BankCog", uid: int, amount: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.uid = uid
        self.amount = amount

    async def accepted(self, i: discord.Interaction):
        raise NotImplementedError

    @discord.ui.button(label="✔", style=discord.ButtonStyle.green)
    async def ok(self, i, b):
        if not is_head(i.user, self.cog.bot.settings.head_role_id):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)
        await self.accepted(i)
        await self.cog.update_terminal()
        await i.message.delete()

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
    async def reject(self, i, b):
        if not is_head(i.user, self.cog.bot.settings.head_role_id):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)
        self.cog.service.add_log(self.log_reject, self.uid, self.amount)
        await self.cog.admin_log(self.log_reject, self.uid, self.amount, i.user)
        await i.message.delete()


class DepositView(ApprovalView):
    log_reject = "ОТКЛОНЁН ПЛАТЁЖ"
    async def accepted(self, i):
        self.cog.service.add_balance(self.amount)
        self.cog.service.add_sponsor(self.uid, self.amount)
        self.cog.service.add_log("DEPOSIT", self.uid, self.amount)


class LoanView(ApprovalView):
    log_reject = "ОТКЛОНЁН КРЕДИТ"
    async def accepted(self, i):
        self.cog.service.subtract_balance(self.amount)
        self.cog.service.add_debt(self.uid, self.amount)
        self.cog.service.add_log("LOAN", self.uid, self.amount)


class PayDebtView(ApprovalView):
    log_reject = "ОТКЛОНЁН ПЛАТЁЖ"
    async def accepted(self, i):
        paid = self.cog.service.reduce_debt(self.uid, self.amount)
        self.cog.service.add_balance(paid)
        self.cog.service.add_log("REPAY", self.uid, paid)


class DepositModal(discord.ui.Modal, title="Deposit"):
    amount = discord.ui.TextInput(label="Amount")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        amount = parse_positive_int(self.amount.value)
        if amount is None:
            return await i.response.send_message("❌ Сумма должна быть числом больше 0", ephemeral=True)
        uid = i.user.id
        async def cb(msg):
            ch = await self.cog.bot.fetch_channel(self.cog.bot.settings.channel_report)
            file = await msg.attachments[0].to_file() if msg.attachments else None
            embed = discord.Embed(title="💰 DEPOSIT", description=f"<@{uid}> ${amount:,}", color=BANK_COLOR)
            if file: embed.set_image(url=f"attachment://{file.filename}")
            await ch.send(embed=embed, file=file, view=DepositView(self.cog, uid, amount))
        self.cog.bot.active_uploads[uid] = {"callback": cb, "channel_id": i.channel.id}
        await i.response.send_message("📷 Отправьте скриншот", ephemeral=True)


class LoanModal(discord.ui.Modal, title="Loan"):
    amount = discord.ui.TextInput(label="Amount")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        amount = parse_positive_int(self.amount.value)
        if amount is None:
            return await i.response.send_message("❌ Сумма должна быть числом больше 0", ephemeral=True)
        ch = await self.cog.bot.fetch_channel(self.cog.bot.settings.channel_report)
        await ch.send(embed=discord.Embed(title="💸 LOAN REQUEST", description=f"{i.user.mention} ${amount:,}", color=BANK_COLOR), view=LoanView(self.cog, i.user.id, amount))
        await i.response.send_message("✅ Заявка отправлена", ephemeral=True)


class PayDebtModal(discord.ui.Modal, title="Repay"):
    amount = discord.ui.TextInput(label="Amount")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        amount = parse_positive_int(self.amount.value)
        if amount is None:
            return await i.response.send_message("❌ Сумма должна быть числом больше 0", ephemeral=True)
        if self.cog.service.debt(i.user.id) <= 0:
            return await i.response.send_message("❌ У вас нет активного долга", ephemeral=True)
        uid = i.user.id
        async def cb(msg):
            ch = await self.cog.bot.fetch_channel(self.cog.bot.settings.channel_report)
            file = await msg.attachments[0].to_file() if msg.attachments else None
            embed = discord.Embed(title="📥 REPAY", description=f"<@{uid}> ${amount:,}", color=BANK_COLOR)
            if file: embed.set_image(url=f"attachment://{file.filename}")
            await ch.send(embed=embed, file=file, view=PayDebtView(self.cog, uid, amount))
        self.cog.bot.active_uploads[uid] = {"callback": cb, "channel_id": i.channel.id}
        await i.response.send_message("📷 Отправьте скриншот", ephemeral=True)


class BankCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = BankService(bot.db)
        self.message_id: int | None = None

    async def start(self):
        self.bot.add_view(BankUI(self))
        await self.update_terminal()

    async def ensure_terminal(self):
        if not self.message_id:
            await self.update_terminal()
            return
        try:
            ch = await self.bot.fetch_channel(self.bot.settings.channel_request)
            await ch.fetch_message(self.message_id)
        except Exception:
            self.message_id = None
            await self.update_terminal()

    async def update_terminal(self):
        ch = await self.bot.fetch_channel(self.bot.settings.channel_request)
        embed = bank_embed(self.service)
        if self.message_id:
            try:
                msg = await ch.fetch_message(self.message_id)
                await msg.edit(embed=embed, view=BankUI(self))
                return
            except Exception:
                self.message_id = None
        await clear_channel(ch)
        msg = await ch.send(embed=embed, view=BankUI(self))
        await safe_pin(msg)
        self.message_id = msg.id

    async def admin_log(self, action: str, uid: int, amount: int, admin: discord.Member):
        try:
            ch = await self.bot.fetch_channel(self.bot.settings.channel_approve)
            await ch.send(embed=discord.Embed(title=f"📜 {action}", description=f"👤 Игрок: <@{uid}>\n💵 Сумма: ${amount:,}\n🛡️ Администратор: {admin.mention}", color=discord.Color.orange()))
        except Exception as exc:
            print("ADMIN LOG ERROR:", exc)

    @commands.command(name="setbank")
    async def setbank(self, ctx: commands.Context, amount: int):
        if ctx.channel.id != self.bot.settings.channel_report:
            return
        self.service.set_balance(amount)
        await self.update_terminal()
        await ctx.send(embed=discord.Embed(title="🏦 BANK OVERRIDE", description=f"Баланс установлен: ${amount:,}", color=BANK_COLOR))
