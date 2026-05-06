import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

GUILD_ID = 1345261255300218992

CHANNEL_REQUEST = 1501385708366205028
CHANNEL_REPORT = 1501351092125040710
CHANNEL_APPROVE = 1448688906299113684

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

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
            remaining = self.data.get("remaining", 0)

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
            msg = f"""〖💸〗НОВАЯ ЗАПИСЬ О ДОЛГЕ
────────────────
👤 Заемщик: {user.mention}
💰 Сумма долга: {amount:,}
📅 Дата выдачи: {nice_date()}

✅ Статус: Одобрено Администрацией
────────────────
Принял: {interaction.user.mention}
"""

        await log_channel.send(msg)
        await interaction.message.delete()
        await interaction.followup.send("✅ Одобрено", ephemeral=True)

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


# ================= /loan =================
@bot.tree.command(name="loan", description="Запрос долга", guild=guild)
async def loan(interaction: discord.Interaction, amount: int):

    channel = await bot.fetch_channel(CHANNEL_REQUEST)

    embed = discord.Embed(
        title="💸 ЗАЯВКА НА ДОЛГ",
        color=discord.Color.blue()
    )

    embed.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="Дата", value=nice_date(), inline=False)

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    await report_channel.send(
        embed=embed,
        view=ApproveRejectView({
            "user": interaction.user,
            "amount": amount
        }, "loan")
    )

    await interaction.response.send_message("✅ Заявка отправлена", ephemeral=True)


# ================= /pay_debt =================
@bot.tree.command(name="pay_debt", description="Погашение долга", guild=guild)
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    channel = await bot.fetch_channel(CHANNEL_REQUEST)

    embed = discord.Embed(
        title="📥 ПОГАШЕНИЕ ДОЛГА",
        color=discord.Color.orange()
    )

    embed.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
    embed.add_field(name="Сумма", value=f"{amount:,}", inline=False)
    embed.add_field(name="Дата", value=nice_date(), inline=False)

    embed.set_image(url=screenshot.url)

    report_channel = await bot.fetch_channel(CHANNEL_REPORT)

    await report_channel.send(
        embed=embed,
        view=ApproveRejectView({
            "user": interaction.user,
            "amount": amount,
            "remaining": 0  # позже подключим базу
        }, "pay")
    )

    await interaction.response.send_message("✅ Отправлено", ephemeral=True)


# ================= RUN =================
bot.run(TOKEN)
