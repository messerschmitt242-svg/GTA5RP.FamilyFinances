from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from core.utils import extract_rp_name, has_any_role, has_role, safe_pin
from modules.contracts.services import ContractService, format_duration, format_requirements
from modules.skills.constants import CLUBS, RANKS, SKILLS, stat_name

COLOR = discord.Color.from_rgb(255, 148, 36)
CATEGORY_ITEMS = {"skills": SKILLS, "ranks": RANKS, "clubs": CLUBS}
CATEGORY_NAMES = {"skills": "Навыки", "ranks": "Ранги", "clubs": "Клубы"}


def is_family_member(member: discord.Member, family_role: int) -> bool:
    return has_role(member, family_role)


def can_participate(member: discord.Member, family_role: int, wrestler_role: int) -> bool:
    return has_any_role(member, family_role, wrestler_role)


def max_value_for(stat_key: str) -> int:
    if stat_key == "fishing":
        return 6
    if stat_key == "shooting":
        return 10
    if stat_key == "moto_club":
        return 4
    if stat_key.endswith("_rank"):
        return 15
    return 5


def parse_time_to_minutes(raw: str) -> int | None:
    text = raw.strip().replace(",", ".")
    if not text:
        return 0
    try:
        if "." in text:
            hours, minutes = text.split(".", 1)
            h = int(hours or 0)
            m = int(minutes or 0)
        else:
            h = int(text)
            m = 0
    except ValueError:
        return None
    if h < 0 or m < 0 or m > 59:
        return None
    return h * 60 + m


def parse_pg_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def member_line(row) -> str:
    mention = f"<@{row['discord_id']}>" if row.get("discord_id") else "без тега"
    return f"> 🔸 **{row['rp_name']}** — {mention}"


class ContractPanel(discord.ui.View):
    def __init__(self, cog: "ContractsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="➕ Добавить контракт", style=discord.ButtonStyle.green, custom_id="contracts_add_contract")
    async def add_contract(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Создавать контракты может только роль Family", ephemeral=True)
        await i.response.send_modal(StartContractModal(self.cog))

    @discord.ui.button(label="👤 Добавить человека", style=discord.ButtonStyle.blurple, custom_id="contracts_add_person")
    async def add_person(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Добавлять людей может только роль Family", ephemeral=True)
        await i.response.send_modal(StartPersonModal(self.cog))

    @discord.ui.button(label="✏️ Редактировать навык", style=discord.ButtonStyle.gray, custom_id="contracts_edit_skill")
    async def edit_skill(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Редактировать навыки может только роль Family", ephemeral=True)
        profiles = self.cog.service.list_profiles(25)
        if not profiles:
            return await i.response.send_message("❌ Сначала добавь хотя бы одного человека.", ephemeral=True)
        await i.response.send_message("Выбери игрока для редактирования:", view=ProfileSelectView(self.cog, profiles), ephemeral=True)

    @discord.ui.button(label="📋 Активные", style=discord.ButtonStyle.secondary, custom_id="contracts_active")
    async def active(self, i: discord.Interaction, _):
        rows = self.cog.service.list_open_contracts()
        if not rows:
            desc = "Активных контрактов нет"
        else:
            desc = "\n\n".join(
                f"`#{r['id']}` — **{r['title']}** ({'идёт' if r['status']=='started' else 'набор'})\n"
                f"Награда: {r['reward_bills']} векс. / ${r['reward_dollars']} | Время: {format_duration(r['duration_minutes'])}"
                for r in rows
            )
        await i.response.send_message(embed=discord.Embed(title="📋 Активные контракты", description=desc, color=COLOR), ephemeral=True)

    @discord.ui.button(label="📜 История контрактов", style=discord.ButtonStyle.secondary, custom_id="contracts_history")
    async def history(self, i: discord.Interaction, _):
        rows = self.cog.service.list_history_contracts(10)
        if not rows:
            desc = "История завершенных контрактов пуста"
        else:
            status_map = {"success": "✅ успех", "failed": "❌ провал"}
            desc = "\n\n".join(
                f"`#{r['id']}` — **{r['title']}**\n"
                f"Статус: **{status_map.get(r['status'], r['status'])}**\n"
                f"Награда: {r['reward_bills']} векс. / ${r['reward_dollars']} | Время: {format_duration(r['duration_minutes'])}"
                for r in rows
            )
        await i.response.send_message(embed=discord.Embed(title="📜 Последние 10 завершенных контрактов", description=desc, color=COLOR), ephemeral=True)


class ContractActionView(discord.ui.View):
    def __init__(self, cog: "ContractsCog", contract_id: int, started: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.contract_id = contract_id
        if started:
            for child in list(self.children):
                if getattr(child, "custom_id", "") in {"contract_join", "contract_leave", "contract_suggest", "contract_promote", "contract_start"}:
                    self.remove_item(child)

    @discord.ui.button(label="✅ Участвовать", style=discord.ButtonStyle.green, custom_id="contract_join")
    async def join(self, i: discord.Interaction, _):
        if not can_participate(i.user, self.cog.bot.settings.role_family, self.cog.bot.settings.role_wrestler):
            return await i.response.send_message("❌ Участвовать могут Family или Wrestler", ephemeral=True)
        rp = extract_rp_name(i.user.display_name)
        rp = self.cog.service.add_participant(self.contract_id, rp, i.user.id, i.user.id, self.cog.bot.settings.max_contract_members)
        await i.response.send_message(f"✅ Ты записан на контракт `#{self.contract_id}` как **{rp}**. Система пересчитала топ-5.", ephemeral=True)
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
        _, req, _, _ = data
        team, remaining, chance = self.cog.service.suggest_team(req, self.cog.bot.settings.max_contract_members)
        desc = "\n".join(f"{n+1}. **{c.rp_name}** — вклад {c.score}, Подрядчик {c.contractor}" for n, c in enumerate(team)) or "Нет подходящих игроков"
        left = "\n".join(f"• {stat_name(k)}: {v}" for k, v in remaining.items() if v > 0) or "Все требования закрыты"
        await i.response.send_message(embed=discord.Embed(title=f"🧠 Подбор состава #{self.contract_id}", description=f"{desc}\n\n**Шанс:** {chance}%\n\n**Остаток:**\n{left}", color=COLOR), ephemeral=True)

    @discord.ui.button(label="➕ Добавить желающих", style=discord.ButtonStyle.blurple, custom_id="contract_promote")
    async def promote(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Добавлять желающих может только Family", ephemeral=True)
        moved = self.cog.service.promote_waitlist(self.contract_id, i.user.id, self.cog.bot.settings.max_contract_members)
        await i.response.send_message(f"✅ Добавлено из желающих: **{moved}**", ephemeral=True)
        await self.cog.refresh_contract_message(i.message, self.contract_id)

    @discord.ui.button(label="▶️ Начать контракт", style=discord.ButtonStyle.green, custom_id="contract_start")
    async def start_contract(self, i: discord.Interaction, _):
        if not is_family_member(i.user, self.cog.bot.settings.role_family):
            return await i.response.send_message("❌ Начать контракт может только Family", ephemeral=True)
        self.cog.service.start_contract(self.contract_id, i.user.id)
        await i.response.send_message(f"▶️ Контракт `#{self.contract_id}` начат. Таймер запущен.", ephemeral=True)
        await self.cog.refresh_contract_message(i.message, self.contract_id)

    @discord.ui.button(label="🏁 Успех", style=discord.ButtonStyle.red, custom_id="contract_success")
    async def success(self, i: discord.Interaction, _):
        await self.cog.finish_contract(i, self.contract_id, "success")

    @discord.ui.button(label="💀 Провал", style=discord.ButtonStyle.red, custom_id="contract_failed")
    async def failed(self, i: discord.Interaction, _):
        await self.cog.finish_contract(i, self.contract_id, "failed")


class StartContractModal(discord.ui.Modal, title="Добавить контракт"):
    title_input = discord.ui.TextInput(label="Название контракта", max_length=80)
    count_input = discord.ui.TextInput(label="Количество навыков/рангов/клубов", placeholder="Например: 3", max_length=2)

    def __init__(self, cog: "ContractsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, i: discord.Interaction):
        try:
            count = int(str(self.count_input.value).strip())
        except ValueError:
            return await i.response.send_message("❌ Количество должно быть числом.", ephemeral=True)
        if count < 1 or count > 20:
            return await i.response.send_message("❌ Укажи количество от 1 до 20.", ephemeral=True)
        state = {"type": "contract", "title": str(self.title_input.value).strip(), "count": count, "values": {}}
        await i.response.send_message(self.cog.progress_text(state), view=SkillValueView(self.cog, state), ephemeral=True)


class StartPersonModal(discord.ui.Modal, title="Добавить человека"):
    discord_nick = discord.ui.TextInput(label="Ник в Discord", placeholder="Например: Wolf_Wayne [Саня]", max_length=80)
    rp_name = discord.ui.TextInput(label="Ник в игре", placeholder="Например: Wolf_Wayne", max_length=80)
    count_input = discord.ui.TextInput(label="Количество прокачанных навыков/рангов/клубов", placeholder="Например: 5", max_length=2)

    def __init__(self, cog: "ContractsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, i: discord.Interaction):
        try:
            count = int(str(self.count_input.value).strip())
        except ValueError:
            return await i.response.send_message("❌ Количество должно быть числом.", ephemeral=True)
        if count < 1 or count > 34:
            return await i.response.send_message("❌ Укажи количество от 1 до 34.", ephemeral=True)
        state = {"type": "person", "discord_name": str(self.discord_nick.value).strip(), "rp_name": str(self.rp_name.value).strip(), "count": count, "values": {}}
        await i.response.send_message(self.cog.progress_text(state), view=SkillValueView(self.cog, state), ephemeral=True)


class RewardModal(discord.ui.Modal, title="Награда и время"):
    bills = discord.ui.TextInput(label="Награда в векселях", placeholder="Например: 10", max_length=10)
    dollars = discord.ui.TextInput(label="Награда в долларах", placeholder="Например: 50000", max_length=12)
    duration = discord.ui.TextInput(label="Время через точку", placeholder="2.10 = 2 часа 10 минут", max_length=8)

    def __init__(self, cog: "ContractsCog", state: dict):
        super().__init__()
        self.cog = cog
        self.state = state

    async def on_submit(self, i: discord.Interaction):
        try:
            bills = int(str(self.bills.value).replace(" ", ""))
            dollars = int(str(self.dollars.value).replace(" ", ""))
        except ValueError:
            return await i.response.send_message("❌ Награда должна быть числом.", ephemeral=True)
        minutes = parse_time_to_minutes(str(self.duration.value))
        if minutes is None:
            return await i.response.send_message("❌ Время укажи в формате `2.10`, где после точки минуты от 00 до 59.", ephemeral=True)
        cid = self.cog.service.create_contract(self.state["title"], i.user.id, self.state["values"], "manual", bills, dollars, minutes)
        await i.response.send_message(f"✅ Контракт создан: `#{cid}`", ephemeral=True)
        await self.cog.publish_contract(cid)


class RewardButtonView(discord.ui.View):
    def __init__(self, cog: "ContractsCog", state: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.state = state

    @discord.ui.button(label="💰 Ввести награду и время", style=discord.ButtonStyle.green)
    async def open_reward_modal(self, i: discord.Interaction, _):
        await i.response.send_modal(RewardModal(self.cog, self.state))


class SkillAmountModal(discord.ui.Modal, title="Количество очков"):
    amount = discord.ui.TextInput(label="Количество очков", placeholder="Введи число", max_length=3)

    def __init__(self, cog: "ContractsCog", state: dict, stat_key: str):
        super().__init__()
        self.cog = cog
        self.state = state
        self.stat_key = stat_key

    async def on_submit(self, i: discord.Interaction):
        try:
            value = int(str(self.amount.value).strip())
        except ValueError:
            return await i.response.send_message("❌ Значение должно быть числом.", ephemeral=True)
        if value < 0:
            return await i.response.send_message("❌ Значение не может быть меньше 0.", ephemeral=True)
        if self.state["type"] in {"person", "edit"}:
            limit = max_value_for(self.stat_key)
            if value > limit:
                return await i.response.send_message(f"❌ Для **{stat_name(self.stat_key)}** максимум: {limit}.", ephemeral=True)
        self.state["values"][self.stat_key] = value
        if self.state["type"] == "edit":
            self.cog.service.update_profile_skill(self.state["rp_name"], self.stat_key, value, i.user.id)
            return await i.response.send_message(f"✅ У **{self.state['rp_name']}** обновлено: {stat_name(self.stat_key)} = {value}", ephemeral=True)
        if len(self.state["values"]) >= self.state["count"]:
            if self.state["type"] == "contract":
                text = (
                    "✅ Все требования контракта добавлены.\n\n"
                    f"**{self.state['title']}**\n"
                    f"{format_requirements(self.state['values'])}\n\n"
                    "Нажми кнопку ниже, чтобы ввести награду и время выполнения."
                )
                return await i.response.send_message(text, view=RewardButtonView(self.cog, self.state), ephemeral=True)
            self.cog.service.upsert_profile(self.state["rp_name"], None, self.state["discord_name"], self.state["values"])
            await self.cog.contract_log(f"<@{i.user.id}> добавил человека **{self.state['rp_name']}**\n{format_requirements(self.state['values'])}")
            return await i.response.send_message(f"✅ Человек **{self.state['rp_name']}** добавлен/обновлен.", ephemeral=True)
        await i.response.send_message(self.cog.progress_text(self.state), view=SkillValueView(self.cog, self.state), ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(self, state: dict):
        options = [discord.SelectOption(label=name, value=key) for key, name in CATEGORY_NAMES.items()]
        super().__init__(placeholder="1) Выбери категорию", min_values=1, max_values=1, options=options)
        self.state = state

    async def callback(self, i: discord.Interaction):
        self.state["category"] = self.values[0]
        await i.response.edit_message(content=i.message.content, view=SkillValueView(i.client.get_cog("ContractsCog"), self.state))


class StatSelect(discord.ui.Select):
    def __init__(self, state: dict):
        category = state.get("category", "skills")
        options = [discord.SelectOption(label=s.ru, value=s.key) for s in CATEGORY_ITEMS[category]]
        super().__init__(placeholder="2) Выбери навык/ранг/клуб", min_values=1, max_values=1, options=options)
        self.state = state

    async def callback(self, i: discord.Interaction):
        self.state["stat_key"] = self.values[0]
        await i.response.send_modal(SkillAmountModal(i.client.get_cog("ContractsCog"), self.state, self.values[0]))


class SkillValueView(discord.ui.View):
    def __init__(self, cog: "ContractsCog", state: dict):
        super().__init__(timeout=300)
        self.add_item(CategorySelect(state))
        self.add_item(StatSelect(state))


class ProfileSelect(discord.ui.Select):
    def __init__(self, profiles):
        options = [discord.SelectOption(label=r["rp_name"], value=r["rp_name"]) for r in profiles[:25]]
        super().__init__(placeholder="Выбери ник игрока в Discord/профиль", min_values=1, max_values=1, options=options)

    async def callback(self, i: discord.Interaction):
        state = {"type": "edit", "rp_name": self.values[0], "count": 1, "values": {}}
        await i.response.edit_message(content=f"Игрок: **{self.values[0]}**\nТеперь выбери навык/ранг/клуб и введи новое число.", view=SkillValueView(i.client.get_cog("ContractsCog"), state))


class ProfileSelectView(discord.ui.View):
    def __init__(self, cog: "ContractsCog", profiles):
        super().__init__(timeout=300)
        self.add_item(ProfileSelect(profiles))


class ContractsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = ContractService(bot.db)

    async def cog_load(self):
        self.bot.add_view(ContractPanel(self))

    async def start(self):
        await self.ensure_terminal()

    def panel_embed(self) -> discord.Embed:
        return discord.Embed(
            title="📑 СИСТЕМА КОНТРАКТОВ WAYNE INC.",
            description=(
                "```fix\nGTA5RP CONTRACTS MANAGER\n```\n"
                "• Добавить контракт — создание требований, наград и времени.\n"
                "• Контракты публикуются в 〖🧰〗доступные-контракты.\n"
                "• Участники — топ-5, остальные попадают в желающие.\n"
                "• Начать контракт — запускает таймер и скрывает кнопки набора."
            ),
            color=COLOR,
        )

    async def find_existing_panel_message(self, channel: discord.abc.Messageable) -> discord.Message | None:
        async for message in channel.history(limit=50):
            if message.author.id == self.bot.user.id and message.embeds and message.embeds[0].title == "📑 СИСТЕМА КОНТРАКТОВ WAYNE INC.":
                return message
        return None

    async def ensure_terminal(self):
        channel = self.bot.get_channel(self.bot.settings.channel_contract_panel)
        if not channel:
            return
        embed = self.panel_embed()
        msg = await self.find_existing_panel_message(channel)
        if msg:
            await msg.edit(embed=embed, view=ContractPanel(self))
            return
        msg = await channel.send(embed=embed, view=ContractPanel(self))
        await safe_pin(msg)

    def progress_text(self, state: dict) -> str:
        added = len(state.get("values", {}))
        lines = [f"Добавлено: **{added}/{state['count']}**"]
        if state.get("values"):
            lines.append(format_requirements(state["values"]))
        lines.append("\nDiscord Select ограничен 25 пунктами, поэтому полный список разбит на категории: навыки, ранги, клубы.")
        return "\n".join(lines)

    def contract_embed(self, contract_id: int) -> discord.Embed:
        data = self.service.get_contract(contract_id)
        if not data:
            return discord.Embed(title="❌ Контракт не найден", color=discord.Color.red())
        contract, req, parts, wait = data
        team, remaining, chance = self.service.suggest_team(req, self.bot.settings.max_contract_members)
        participants = "\n".join(member_line(p) for p in parts) or "Пока никто не записался"
        waitlist = "\n".join(member_line(p) for p in wait) or "Пусто"
        left = "\n".join(f"• **{stat_name(k)}:** {v}" for k, v in remaining.items() if v > 0) or "Все требования закрыты"
        status = contract["status"]
        desc = f"**Требования:**\n{format_requirements(req)}\n\n**👥 Участники / топ-{self.bot.settings.max_contract_members}:**\n{participants}\n\n**🙋 Желающие:**\n{waitlist}\n\n**Авто-шанс лучшего состава:** {chance}%\n\n**Нехватка:**\n{left}"
        if status == "started":
            started_at = parse_pg_datetime(contract.get("started_at"))
            if started_at and int(contract["duration_minutes"] or 0) > 0:
                end_at = started_at + timedelta(minutes=int(contract["duration_minutes"]))
                desc += f"\n\n▶️ **Контракт начат**\n⏳ Окончание: <t:{int(end_at.timestamp())}:R> / <t:{int(end_at.timestamp())}:T>"
            else:
                desc += "\n\n▶️ **Контракт начат**"
        embed = discord.Embed(title=f"📑 Контракт #{contract_id}: {contract['title']}", description=desc, color=COLOR)
        embed.add_field(name="Статус", value="▶️ идёт" if status == "started" else "🟢 набор", inline=True)
        embed.add_field(name="Награда", value=f"{contract['reward_bills']} векс. / ${contract['reward_dollars']}", inline=True)
        embed.add_field(name="Время", value=format_duration(contract["duration_minutes"]), inline=True)
        return embed

    async def publish_contract(self, contract_id: int):
        channel = self.bot.get_channel(self.bot.settings.channel_available_contracts)
        if not channel:
            await self.admin_alert("CHANNEL_AVAILABLE_CONTRACTS не найден. Проверь переменную окружения и права бота.")
            return
        msg = await channel.send(embed=self.contract_embed(contract_id), view=ContractActionView(self, contract_id))
        self.service.set_available_message_id(contract_id, msg.id)

    async def refresh_contract_message(self, message: discord.Message, contract_id: int):
        data = self.service.get_contract(contract_id)
        started = bool(data and data[0]["status"] == "started")
        try:
            await message.edit(embed=self.contract_embed(contract_id), view=ContractActionView(self, contract_id, started=started))
        except Exception as exc:
            await self.admin_alert(f"Не удалось обновить embed контракта #{contract_id}: {exc}")

    async def finish_contract(self, i: discord.Interaction, contract_id: int, status: str):
        if not is_family_member(i.user, self.bot.settings.role_family):
            return await i.response.send_message("❌ Завершать контракты может только Family", ephemeral=True)
        self.service.close_contract(contract_id, i.user.id, status)
        text = "успех" if status == "success" else "провал"
        await i.response.send_message(f"✅ Контракт `#{contract_id}` завершен. Статус: **{text}**", ephemeral=True)
        try:
            await i.message.edit(embed=self.contract_embed(contract_id), view=None)
        except Exception:
            pass

    async def contract_log(self, text: str):
        channel = self.bot.get_channel(self.bot.settings.channel_contract_logs)
        if channel:
            await channel.send(text)

    async def admin_alert(self, text: str):
        channel = self.bot.get_channel(self.bot.settings.channel_admin_alerts)
        if channel:
            await channel.send(f"⚠️ {text}")

    @commands.command(name="contracts_wipe")
    @commands.has_permissions(administrator=True)
    async def contracts_wipe(self, ctx: commands.Context):
        if ctx.channel.id != self.bot.settings.channel_admin_alerts:
            return await ctx.reply("❌ Команду можно использовать только в CHANNEL_ADMIN_ALERTS.", delete_after=10)

        await ctx.send(
            embed=discord.Embed(
                title="⚠ Полная очистка контрактов",
                description="Будут удалены все контракты, требования, участники, желающие и история.\n\nДля подтверждения напиши: `CONFIRM WIPE`",
                color=discord.Color.red(),
            ),
            delete_after=60,
        )

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRM WIPE"

        try:
            await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("⌛ Очистка отменена.", delete_after=10)

        self.service.wipe_contracts(ctx.author.id)
        await ctx.send("✅ База контрактов полностью очищена.", delete_after=15)


async def setup(bot):
    await bot.add_cog(ContractsCog(bot))
