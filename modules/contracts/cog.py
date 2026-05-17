from __future__ import annotations

import tempfile
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.utils import clear_channel, extract_rp_name, has_any_role, has_role, safe_pin
from modules.contracts.services import ContractService, format_requirements
from modules.ocr.scanner import TemplateOcrScanner
from modules.skills.constants import STAT_KEYS, stat_name

COLOR = discord.Color.from_rgb(255, 148, 36)


def is_family_member(member: discord.Member, family_role: int) -> bool:
    return has_role(member, family_role)


def can_participate(member: discord.Member, family_role: int, wrestler_role: int) -> bool:
    return has_any_role(member, family_role, wrestler_role)


class ContractPanel(discord.ui.View):
    def __init__(self, cog: "ContractsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="📸 OCR контракта", style=discord.ButtonStyle.green, custom_id="contracts_ocr_create")
    async def ocr_contract(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Создавать контракты может только роль Family", ephemeral=True)
        self.cog.bot.active_uploads[i.user.id] = {"channel_id": i.channel_id, "callback": self.cog.handle_contract_screenshot}
        await i.response.send_message("📸 Отправь скриншот контракта следующим сообщением в этот канал.", ephemeral=True)

    @discord.ui.button(label="👥 OCR персонала", style=discord.ButtonStyle.blurple, custom_id="contracts_ocr_personnel")
    async def ocr_personnel(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Обновлять персонал может только роль Family", ephemeral=True)
        self.cog.bot.active_uploads[i.user.id] = {"channel_id": i.channel_id, "callback": self.cog.handle_personnel_screenshot}
        await i.response.send_message("👥 Отправь полный скриншот списка персонала. Бот обновит всех найденных игроков одной пачкой.", ephemeral=True)

    @discord.ui.button(label="➕ Ручной контракт", style=discord.ButtonStyle.gray, custom_id="contracts_manual_create")
    async def manual_contract(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Создавать контракты может только роль Family", ephemeral=True)
        await i.response.send_modal(ManualContractModal(self.cog))

    @discord.ui.button(label="✏️ Ручное обновление", style=discord.ButtonStyle.gray, custom_id="contracts_manual_profile")
    async def manual_profile(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Обновлять навыки может только Family", ephemeral=True)
        await i.response.send_modal(ManualProfileModal(self.cog))

    @discord.ui.button(label="📋 Активные", style=discord.ButtonStyle.secondary, custom_id="contracts_active")
    async def active(self, i: discord.Interaction, _):
        rows = self.cog.service.list_open_contracts()
        desc = "\n".join(f"`#{r['id']}` — **{r['title']}** / {r['status']}" for r in rows) or "Активных контрактов нет"
        await i.response.send_message(embed=discord.Embed(title="📋 Активные контракты", description=desc, color=COLOR), ephemeral=True)

    @discord.ui.button(label="🔗 Связать ники", style=discord.ButtonStyle.secondary, custom_id="contracts_link_names")
    async def link_names(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Доступно только Family", ephemeral=True)
        count = self.cog.service.link_guild_members(i.guild)
        await i.response.send_message(f"✅ Связано Discord ↔ RP nickname: {count}", ephemeral=True)


class ContractActionView(discord.ui.View):
    def __init__(self, cog: "ContractsCog", contract_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.contract_id = contract_id

    @discord.ui.button(label="✅ Участвовать", style=discord.ButtonStyle.green, custom_id="contract_join")
    async def join(self, i: discord.Interaction, _):
        if not can_participate(i.user, self.cog.bot.settings.role_family, self.cog.bot.settings.role_wrestler):
            return await i.response.send_message("❌ Участвовать могут Family или Wrestler", ephemeral=True)
        rp = extract_rp_name(i.user.display_name)
        self.cog.service.upsert_profile(rp, i.user.id, i.user.display_name, {})
        self.cog.service.add_participant(self.contract_id, rp, i.user.id, i.user.id)
        await i.response.send_message(f"✅ Ты записан на контракт `#{self.contract_id}` как **{rp}**", ephemeral=True)
        await self.cog.refresh_contract_message(i.message, self.contract_id)

    @discord.ui.button(label="🚪 Выйти", style=discord.ButtonStyle.gray, custom_id="contract_leave")
    async def leave(self, i: discord.Interaction, _):
        rp = extract_rp_name(i.user.display_name)
        self.cog.service.remove_participant(self.contract_id, rp, i.user.id)
        await i.response.send_message(f"✅ Ты вышел из контракта `#{self.contract_id}`", ephemeral=True)
        await self.cog.refresh_contract_message(i.message, self.contract_id)

    @discord.ui.button(label="🧠 Подбор", style=discord.ButtonStyle.blurple, custom_id="contract_suggest")
    async def suggest(self, i: discord.Interaction, _):
        data = self.cog.service.get_contract(self.contract_id)
        if not data:
            return await i.response.send_message("❌ Контракт не найден", ephemeral=True)
        _, req, _ = data
        team, remaining, chance = self.cog.service.suggest_team(req, self.cog.bot.settings.max_contract_members)
        desc = "\n".join(f"{n+1}. **{c.rp_name}** — вклад {c.score}, Подрядчик {c.contractor}" for n, c in enumerate(team)) or "Нет подходящих игроков"
        left = "\n".join(f"• {stat_name(k)}: {v}" for k, v in remaining.items() if v > 0) or "Все требования закрыты"
        await i.response.send_message(embed=discord.Embed(title=f"🧠 Подбор состава #{self.contract_id}", description=f"{desc}\n\n**Шанс:** {chance}%\n\n**Остаток:**\n{left}", color=COLOR), ephemeral=True)

    @discord.ui.button(label="🏁 Завершить", style=discord.ButtonStyle.red, custom_id="contract_complete")
    async def complete(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Завершать контракты может только Family", ephemeral=True)
        self.cog.service.close_contract(self.contract_id, i.user.id, "completed")
        await i.response.send_message("✅ Контракт завершен и сохранен в историю", ephemeral=True)
        try:
            await i.message.edit(view=None)
        except Exception:
            pass


class ManualProfileModal(discord.ui.Modal, title="Ручное обновление профиля"):
    rp_name = discord.ui.TextInput(label="RP nickname", placeholder="Wolf_Wayne или John Wick")
    values = discord.ui.TextInput(label="Навыки/ранги", style=discord.TextStyle.paragraph, placeholder="Шахтёр=30\nПодрядчик=5\nФедеральный агент=2")

    def __init__(self, cog: "ContractsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, i: discord.Interaction):
        vals = self.cog.parse_manual_requirements(str(self.values.value))
        if not vals:
            return await i.response.send_message("❌ Не удалось распознать значения. Формат: `Шахтёр=30`", ephemeral=True)
        self.cog.service.upsert_profile(str(self.rp_name.value).strip(), None, None, vals)
        await self.cog.contract_log(f"<@{i.user.id}> вручную обновил профиль **{str(self.rp_name.value).strip()}**\n{format_requirements(vals)}")
        await i.response.send_message("✅ Профиль обновлен", ephemeral=True)


class ManualContractModal(discord.ui.Modal, title="Ручной контракт"):
    name = discord.ui.TextInput(label="Название контракта", max_length=80)
    requirements = discord.ui.TextInput(label="Требования", style=discord.TextStyle.paragraph, placeholder="Шахтёр=30\nДальнобойщик=43\nПодрядчик=5")

    def __init__(self, cog: "ContractsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, i: discord.Interaction):
        req = self.cog.parse_manual_requirements(str(self.requirements.value))
        if not req:
            return await i.response.send_message("❌ Не удалось распознать требования. Формат: `Шахтёр=30`", ephemeral=True)
        cid = self.cog.service.create_contract(str(self.name.value), i.user.id, req, "manual")
        await i.response.send_message(f"✅ Контракт создан: `#{cid}`", ephemeral=True)
        await self.cog.publish_contract(cid)


class ContractsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = ContractService(bot.db)
        self.scanner = TemplateOcrScanner()
        self.panel_message_id: int | None = None

    async def cog_load(self):
        self.bot.add_view(ContractPanel(self))

    async def start(self):
        await self.ensure_terminal()

    async def ensure_terminal(self):
        channel = self.bot.get_channel(self.bot.settings.channel_contract_panel)
        if not channel:
            return
        embed = discord.Embed(
            title="📑 СИСТЕМА КОНТРАКТОВ WAYNE INC.",
            description=(
                "```fix\nGTA5RP CONTRACTS MANAGER\n```\n"
                "• OCR контракта — добавить контракт в систему путём отправки скриншота окна контракта.\n"
                "• OCR персонала — массово обновить навыки/ранги/клубы по скриншоту списка персонала.\n"
                "• Подбор состава до 5 участников\n"
                "• Бонус Подрядчика: +2% за уровень до 5 уровня\n"
                "• История контрактов сохраняется в PostgreSQL\n\n"
                "⚙️ Выберите действие ниже."
            ),
            color=COLOR,
        )
        if self.panel_message_id:
            try:
                msg = await channel.fetch_message(self.panel_message_id)
                await msg.edit(embed=embed, view=ContractPanel(self))
                return
            except Exception:
                pass
        await clear_channel(channel)
        msg = await channel.send(embed=embed, view=ContractPanel(self))
        self.panel_message_id = msg.id
        await safe_pin(msg)

    async def admin_alert(self, text: str):
        ch = self.bot.get_channel(self.bot.settings.channel_admin_alerts)
        if ch:
            await ch.send(embed=discord.Embed(title="⚠️ Contracts Alert", description=text, color=discord.Color.red()))

    async def contract_log(self, text: str):
        ch = self.bot.get_channel(self.bot.settings.channel_contract_logs)
        if ch:
            await ch.send(embed=discord.Embed(title="📑 Contracts Log", description=text, color=COLOR))

    async def handle_contract_screenshot(self, message: discord.Message):
        if not message.attachments:
            raise RuntimeError("Нужен файл изображения")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / message.attachments[0].filename
            await message.attachments[0].save(path)
            req = self.scanner.parse_contract_image(str(path))
        if not req:
            await self.admin_alert(f"OCR контракта не нашёл требования. Загружено templates: {self.scanner.template_count()}. Проверь путь assets/ocr/templates/<skills|ranks|clubs>/ и названия файлов.")
            raise RuntimeError("OCR не нашёл иконки/числа. Проверь templates и качество скрина.")
        title = f"Контракт OCR #{message.id}"
        cid = self.service.create_contract(title, message.author.id, req, "ocr")
        await self.publish_contract(cid)
        await self.contract_log(f"<@{message.author.id}> создал контракт OCR `#{cid}`\n{format_requirements(req)}")

    async def handle_personnel_screenshot(self, message: discord.Message):
        if not message.attachments:
            raise RuntimeError("Нужен файл изображения")

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / message.attachments[0].filename
            await message.attachments[0].save(path)
            personnel = self.scanner.parse_personnel_table(str(path))

        if not personnel:
            await self.admin_alert(
                f"OCR персонала не нашёл строки игроков. Загружено templates: {self.scanner.template_count()}. "
                "Проверь полный скрин списка персонала и шаблоны assets/ocr/templates/<skills|ranks|clubs>/."
            )
            raise RuntimeError("OCR не нашёл строки персонала/иконки/числа. Проверь templates и качество скрина.")

        updated = 0
        total_values = 0
        preview_lines: list[str] = []

        for rp_name, values in personnel.items():
            if not values:
                continue
            self.service.upsert_profile(rp_name, None, None, values)
            updated += 1
            total_values += len(values)
            preview_lines.append(f"• **{rp_name}** — {len(values)} знач.")

        # After OCR created/updated RP profiles, try to link them with Discord members
        # by display nickname: `Wolf_Wayne [Саня]` -> `Wolf_Wayne`.
        linked = 0
        if message.guild is not None:
            linked = self.service.link_guild_members(message.guild)

        if updated <= 0:
            raise RuntimeError("OCR нашёл строки, но не нашёл значений навыков/рангов/клубов.")

        shown = "\n".join(preview_lines[:20])
        if len(preview_lines) > 20:
            shown += f"\n…и ещё {len(preview_lines) - 20}"

        await self.contract_log(
            f"<@{message.author.id}> массово обновил персонал через OCR\n"
            f"Игроков обновлено: **{updated}**\n"
            f"Значений записано: **{total_values}**\n"
            f"Discord ↔ RP связано: **{linked}**\n\n"
            f"{shown}"
        )

    @app_commands.command(name="contracts_clear_db", description="Полностью очистить базу контрактов/профилей GTA OCR")
    async def contracts_clear_db(self, i: discord.Interaction):
        if i.channel_id != self.bot.settings.channel_admin_alerts:
            return await i.response.send_message("❌ Эту команду можно использовать только в admin-alerts канале.", ephemeral=True)
        if not isinstance(i.user, discord.Member) or not is_family_member(i.user, self.bot.settings.role_family):
            return await i.response.send_message("❌ Очистка доступна только роли Family.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        self.service.clear_contract_database()
        await self.contract_log(f"🧹 <@{i.user.id}> полностью очистил базу контрактов, профилей, требований, участников и истории.")
        await i.followup.send("✅ База контрактов полностью очищена.", ephemeral=True)

    def parse_manual_requirements(self, text: str) -> dict[str, int]:
        from modules.skills.constants import ALL_STATS
        aliases = {}
        for stat in ALL_STATS:
            aliases[stat.ru.lower()] = stat.key
            aliases[stat.key.lower()] = stat.key
            for a in stat.aliases:
                aliases[a.lower()] = stat.key
        req = {}
        for line in text.replace(":", "=").splitlines():
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            key = aliases.get(name.strip().lower())
            digits = "".join(ch for ch in value if ch.isdigit())
            if key and digits:
                req[key] = int(digits)
        return req

    def contract_embed(self, contract_id: int) -> discord.Embed:
        data = self.service.get_contract(contract_id)
        if not data:
            return discord.Embed(title="❌ Контракт не найден", color=discord.Color.red())
        contract, req, parts = data
        team, remaining, chance = self.service.suggest_team(req, self.bot.settings.max_contract_members)
        participants = "\n".join(f"• **{p['rp_name']}**" for p in parts) or "Пока никто не записался"
        left = "\n".join(f"• **{stat_name(k)}:** {v}" for k, v in remaining.items() if v > 0) or "Все требования закрыты"
        return discord.Embed(
            title=f"📑 Контракт #{contract_id}: {contract['title']}",
            description=f"**Требования:**\n{format_requirements(req)}\n\n**Участники:**\n{participants}\n\n**Авто-шанс лучшего состава:** {chance}%\n\n**Нехватка:**\n{left}",
            color=COLOR,
        )

    async def publish_contract(self, contract_id: int):
        channel = self.bot.get_channel(self.bot.settings.channel_contract_panel)
        if not channel:
            return
        await channel.send(embed=self.contract_embed(contract_id), view=ContractActionView(self, contract_id))

    async def refresh_contract_message(self, message: discord.Message, contract_id: int):
        try:
            await message.edit(embed=self.contract_embed(contract_id), view=ContractActionView(self, contract_id))
        except Exception as exc:
            await self.admin_alert(f"Не удалось обновить embed контракта #{contract_id}: {exc}")


async def setup(bot):
    await bot.add_cog(ContractsCog(bot))
