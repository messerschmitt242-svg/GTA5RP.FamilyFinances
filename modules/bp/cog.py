import discord
from discord.ext import commands

from core.utils import clear_channel


class BPView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


def bp_embed() -> discord.Embed:
    embed = discord.Embed(title="🎯 BONUS POINTS (BP) — WAYNE INC.", description="```fix\nСИСТЕМА НАЧИСЛЕНИЯ BONUS POINTS\n```\n\n| без VIP | VIP x2 |\n────────────────────────────", color=discord.Color.gold())
    sections = [
        ("🏛 Гос. организации", "Выдать 5 медкарт EMS              | 1 | 2 |\nЗакрыть 15 вызовов EMS            | 2 | 4 |\n1 арест LSPD/LSSD                 | 1 | 2 |\n2 авто на учёт                    | 1 | 2 |\n5 гос. вызовов                    | 2 | 4 |\n2 залога адвокат                  | 2 | 4 |\n40 проверок Weazel                | 2 | 4 |\n1 эфир Weazel News                | 2 | 4 |"),
        ("🔫 Crime / Нелегал", "Капт / Бизвар                     | 1 | 2 |\nХаммер с ВЗХ                      | 3 | 6 |\nВыполнить 5 оплат контрабанды     | 2 | 4 |\nВыполнить 15 взломов/угонов       | 2 | 4 |\nЗакрасить 7 граффити              | 1 | 2 |"),
        ("👷 Работы", "25 выполнений в порту             | 2 | 4 |\n25 выполнений на шахте            | 2 | 4 |\n25 выполнений на стройке          | 2 | 4 |\n25 вызовов пожарного              | 1 | 2 |\n10 посылок на почте               | 1 | 2 |\n10 действий на ферме              | 1 | 2 |\n15 рейсов на дальнобойщике        | 2 | 4 |\n2 рейса на автобусе               | 2 | 4 |"),
        ("🎮 Одиночные", "3 часа AFK                       | 2 | 4 |\nАрендовать Киностудию            | 2 | 4 |\nТир                              | 1 | 2 |\nКазино выигрыш по 0/00           | 2 | 4 |\n20 подходов в зале               | 1 | 2 |\nКупить билет в лотерее           | 1 | 2 |\n2 внешности                      | 2 | 4 |"),
        ("🤝 Парные", "Гонка в картинге                 | 1 | 2 |\nУличная гонка                    | 1 | 2 |\nDance Battle x3                  | 2 | 4 |\nMaze Bank Arena x3               | 1 | 2 |\nТренировочный Комплекс x5        | 1 | 2 |"),
    ]
    for name, value in sections:
        embed.add_field(name=name, value=f"```{value}```", inline=False)
    return embed


class BPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_id: int | None = None

    async def start(self):
        self.bot.add_view(BPView())
        await self.update_terminal()

    async def ensure_terminal(self):
        if not self.message_id:
            await self.update_terminal(); return
        try:
            ch = await self.bot.fetch_channel(self.bot.settings.bp_channel)
            await ch.fetch_message(self.message_id)
        except Exception:
            self.message_id = None
            await self.update_terminal()

    async def update_terminal(self):
        ch = await self.bot.fetch_channel(self.bot.settings.bp_channel)
        if self.message_id:
            try:
                msg = await ch.fetch_message(self.message_id)
                await msg.edit(embed=bp_embed(), view=BPView())
                return
            except Exception:
                self.message_id = None
        await clear_channel(ch)
        msg = await ch.send(embed=bp_embed(), view=BPView())
        self.message_id = msg.id
