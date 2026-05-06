import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")

CHANNEL_ID_REQUEST = 1501528770853605437
CHANNEL_ID_REPORT = 1501351092125040710
CHANNEL_ID_APPROVED = 1448688906299113684

if not TOKEN:
    raise RuntimeError("TOKEN не найден!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== GLOBAL STORAGE (для передачи данных кнопкам) =====
pending_data = {}

# ===== VIEW (кнопки) =====
class DebtView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = pending_data.get(self.message_id)
        if not data:
            await interaction.response.send_message("❌ Данные не найдены", ephemeral=True)
            return

        channel = await bot.fetch_channel(CHANNEL_ID_APPROVED)

        embed = discord.Embed(
            title="〖💰〗ЧАСТИЧНОЕ ПОГАШЕНИЕ",
            color=discord.Color.green()
        )

        embed.description = (
            "────────────────\n"
            f"👤 Заемщик: {data['user']}\n"
            f"💸 Внесено: {data['amount']:,}\n"
            f"📉 Остаток долга: \n"
            f"📅 Дата платежа: {data['date']}\n"
            "────────────────\n"
            f"Принял: {interaction.user.mention}"
        )

        await channel.send(embed=embed)

        await interaction.message.delete()
        await interaction.response.send_message("✅ Одобрено", ephemeral=True)

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.message.delete()
        await interaction.response.send_message("❌ Отклонено", ephemeral=True)

# ===== READY =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Sync OK: {len(synced)} commands")
    except Exception as e:
        print("SYNC ERROR:", e)

# ===== COMMAND =====
@bot.tree.command(name="pay_debt", description="Отправить отчет")
async def pay_debt(interaction: discord.Interaction, amount: int, screenshot: discord.Attachment):

    await interaction.response.defer(ephemeral=True)

    try:
        report_channel = await bot.fetch_channel(CHANNEL_ID_REPORT)

        embed = discord.Embed(
            title="📥 ОТЧЕТ О ПОГАШЕНИИ ДОЛГА",
            color=discord.Color.orange()
        )

        embed.add_field(name="👤 Отправитель", value=interaction.user.mention, inline=False)
        embed.add_field(name="💰 Сумма", value=f"{amount:,}", inline=False)
        embed.add_field(name="📅 Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="⚠️ Статус", value="Ожидает проверки", inline=False)

        embed.set_image(url=screenshot.url)

        # отправляем сообщение и получаем message
        message = await report_channel.send(embed=embed)

        # сохраняем данные для кнопок
        pending_data[message.id] = {
            "user": interaction.user.mention,
            "amount": amount,
            "date": datetime.now().strftime("%B %d, %Y")
        }

        # добавляем кнопки
        await message.edit(view=DebtView(message.id))

        await interaction.followup.send("✅ Отправлено на проверку", ephemeral=True)

    except Exception as e:
        print("ERROR:", e)

        await interaction.followup.send(f"❌ Ошибка: `{e}`", ephemeral=True)

# ===== RUN =====
bot.run(TOKEN)
