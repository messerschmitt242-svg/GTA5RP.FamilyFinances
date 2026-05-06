import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import json

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

GUILD_ID = 1345261255300218992
CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

DB_FILE = "debts.json"

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

# ================= DB =================
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ================= BOT =================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=GUILD_ID)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild)
    print(f"BOT ONLINE: {bot.user}")

# ================= VIEWS =================
class LoanView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        db = load_db()
        user_id = str(self.user_id)

        db[user_id] = db.get(user_id, 0) + self.amount
        save_db(db)

        approve_channel = await bot.fetch_channel(CHANNEL_APPROVE)
        user = await bot.fetch_user(self.user_id)

        text = f"""〖💸〗НОВАЯ ЗАПИСЬ О ДОЛГЕ
────────────────
👤 Заемщик: {user.mention}
💰 Сумма долга: {self.amount:,}
📅 Дата выдачи: {datetime.now().strftime("%B %d, %Y")}

📉 Остаток к возврату: {db[user_id]:,}
✅ Статус: Одобрено
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

        db = load_db()
        user_id = str(self.user_id)

        current_debt = db.get(user_id, 0)
        new_debt = max(0, current_debt - self.amount)
        db[user_id] = new_debt
        save_db(db)

        approve_channel = await bot.fetch_channel(CHANNEL_APPROVE)
        user = await bot.fetch_user(self.user_id)

        text = f"""〖💰〗ЧАСТИЧНОЕ ПОГАШЕНИЕ
────────────────
👤 Заемщик: {user.mention}
💸 Внесено: {self.amount:,}
📉 Остаток долга: {new_debt:,}
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

    embed = discord.Embed(
        title="💸 ЗАЯВКА НА ДОЛГ",
        color=discord.Color.blue()
    )
    embed.add_field(name="👤 Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)

    await report_channel.send(embed=embed, view=LoanView(interaction.user.id, amount))
    await interaction.response.send_message("✅ Заявка отправлена", ephemeral=True)


@bot.tree.command(name="pay_debt", description="Погашение долга", guild=guild)
@app_commands.describe(amount="Сумма", screenshot="Скрин")
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    embed = discord.Embed(
        title="📥 ПОГАШЕНИЕ ДОЛГА",
        color=discord.Color.orange()
    )
    embed.add_field(name="👤 Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
    embed.set_image(url=screenshot.url)

    await report_channel.send(embed=embed, view=PayDebtView(interaction.user.id, amount))
    await interaction.response.send_message("✅ Отправлено", ephemeral=True)


# 🔥 НОВАЯ КОМАНДА
@bot.tree.command(name="all_loans", description="Все долги", guild=guild)
async def all_loans(interaction: discord.Interaction):

    db = load_db()

    if not db:
        await interaction.response.send_message("❌ Нет должников", ephemeral=True)
        return

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    text = "📊 **ВСЕ ДОЛЖНИКИ**\n────────────────\n"

    for user_id, amount in db.items():
        user = await bot.fetch_user(int(user_id))
        text += f"{user.mention} — {amount:,}\n"

    await report_channel.send(text)

    await interaction.response.send_message("✅ Отправлено в канал", ephemeral=True)


# ================= RUN =================
bot.run(TOKEN)
