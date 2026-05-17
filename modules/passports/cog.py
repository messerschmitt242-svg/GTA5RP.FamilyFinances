import discord
from discord.ext import commands

from core.utils import resolve_member, safe_pin


class PassportService:
    def __init__(self, db):
        self.db = db

    def add(self, uid: int, passport: str) -> None:
        old_phone = self.phone(uid)
        with self.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO passports (user_id, passport, phone) VALUES (?, ?, ?)", (str(uid), passport, old_phone))

    def delete(self, uid: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM passports WHERE user_id=?", (str(uid),))

    def all(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT user_id, passport, phone FROM passports").fetchall()

    def passport(self, uid: int) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT passport FROM passports WHERE user_id=?", (str(uid),)).fetchone()
            return row[0] if row else None

    def phone(self, uid: int) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT phone FROM passports WHERE user_id=?", (str(uid),)).fetchone()
            return row[0] if row else None

    def set_phone(self, uid: int, phone: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE passports SET phone=? WHERE user_id=?", (phone, str(uid)))


def passport_embed() -> discord.Embed:
    return discord.Embed(
        title="🪪 РЕЕСТР WAYNE INC.",
        description="```fix\nПАСПОРТНАЯ СИСТЕМА GTA RP\n```\n\n────────────────────────────\n⚙️ Используйте кнопки ниже",
        color=discord.Color.dark_blue(),
    )


class PassportUI(discord.ui.View):
    def __init__(self, cog: "PassportCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="➕ Добавить", style=discord.ButtonStyle.green, custom_id="passport_add")
    async def add_btn(self, interaction, button):
        await interaction.response.send_message("👤 Выберите игрока", view=AddPassportView(self.cog), ephemeral=True)

    @discord.ui.button(label="❌ Удалить", style=discord.ButtonStyle.red, custom_id="passport_delete")
    async def del_btn(self, interaction, button):
        await interaction.response.send_modal(DeletePassportModal(self.cog))

    @discord.ui.button(label="📱 Телефон", style=discord.ButtonStyle.gray, custom_id="passport_phone")
    async def phone_btn(self, interaction, button):
        await interaction.response.send_modal(AddPhoneModal(self.cog))

    @discord.ui.button(label="🔍 Найти", style=discord.ButtonStyle.blurple, custom_id="passport_find")
    async def find_btn(self, interaction, button):
        await interaction.response.send_modal(FindPassportModal(self.cog))

    @discord.ui.button(label="📋 Реестр", style=discord.ButtonStyle.gray, custom_id="passport_registry")
    async def registry_btn(self, interaction, button):
        data = self.cog.service.all()
        rows = []
        for row in data:
            member = interaction.guild.get_member(int(row["user_id"]))
            if member:
                rows.append((member.display_name.lower(), f"👤 {member.display_name}\n🪪 {row['passport']} | ☎️ {row['phone'] or '—'}"))
        rows.sort(key=lambda x: x[0])
        desc = "\n\n".join(r[1] for r in rows) or "Пусто"
        await interaction.response.send_message(embed=discord.Embed(title="📋 ПАСПОРТНЫЙ РЕЕСТР", description=desc, color=discord.Color.dark_blue()), ephemeral=True)


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, cog):
        super().__init__(placeholder="Выберите игрока...", min_values=1, max_values=1, custom_id="passport_member_select")
        self.cog = cog
    async def callback(self, interaction):
        await interaction.response.send_modal(AddPassportModal(self.cog, self.values[0]))


class AddPassportView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.add_item(MemberSelect(cog))


class AddPassportModal(discord.ui.Modal, title="Добавить паспорт"):
    passport = discord.ui.TextInput(label="Номер паспорта")
    def __init__(self, cog, member: discord.Member):
        super().__init__(); self.cog = cog; self.member = member
    async def on_submit(self, i):
        passport = self.passport.value.strip()
        if not passport.isdigit() or len(passport) != 6:
            return await i.response.send_message("❌ Паспорт должен быть 6-значным", ephemeral=True)
        self.cog.service.add(self.member.id, passport)
        await i.response.send_message(embed=discord.Embed(title="✅ ПАСПОРТ ДОБАВЛЕН", description=f"👤 {self.member.mention}\n🪪 #{passport}", color=discord.Color.green()), ephemeral=True)


class AddPhoneModal(discord.ui.Modal, title="Добавить телефон"):
    user = discord.ui.TextInput(label="Игрок")
    phone = discord.ui.TextInput(label="Номер телефона")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        member = await resolve_member(i.guild, self.user.value)
        if not member:
            return await i.response.send_message("❌ Игрок не найден", ephemeral=True)
        if not self.cog.service.passport(member.id):
            return await i.response.send_message("❌ Сначала добавьте паспорт", ephemeral=True)
        phone = self.phone.value.strip()
        if not phone.isdigit() or len(phone) != 7:
            return await i.response.send_message("❌ Телефон должен быть 7-значным", ephemeral=True)
        self.cog.service.set_phone(member.id, phone)
        await i.response.send_message(embed=discord.Embed(title="📱 ТЕЛЕФОН ДОБАВЛЕН", description=f"👤 {member.mention}\n☎️ #{phone}", color=discord.Color.green()), ephemeral=True)


class FindPassportModal(discord.ui.Modal, title="Найти паспорт"):
    user = discord.ui.TextInput(label="Игрок")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        member = await resolve_member(i.guild, self.user.value)
        if not member:
            return await i.response.send_message("❌ Игрок не найден", ephemeral=True)
        passport = self.cog.service.passport(member.id)
        if not passport:
            return await i.response.send_message("❌ Паспорт не найден", ephemeral=True)
        phone = self.cog.service.phone(member.id)
        await i.response.send_message(embed=discord.Embed(title="🪪 ПАСПОРТ ГРАЖДАНИНА", description=f"👤 {member.mention}\n🪪 #{passport}\n☎️ {phone if phone else 'Не указан'}", color=discord.Color.blurple()), ephemeral=True)


class DeletePassportModal(discord.ui.Modal, title="Удалить паспорт"):
    user = discord.ui.TextInput(label="Игрок")
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, i):
        member = await resolve_member(i.guild, self.user.value)
        if not member:
            return await i.response.send_message("❌ Игрок не найден", ephemeral=True)
        passport = self.cog.service.passport(member.id)
        if not passport:
            return await i.response.send_message("❌ Паспорт не найден", ephemeral=True)
        await i.response.send_message(embed=discord.Embed(title="⚠️ ПОДТВЕРЖДЕНИЕ", description=f"👤 {member.mention}\n🪪 #{passport}\n\nУдалить паспорт?", color=discord.Color.orange()), view=DeletePassportConfirm(self.cog, member.id), ephemeral=True)


class DeletePassportConfirm(discord.ui.View):
    def __init__(self, cog, uid):
        super().__init__(timeout=30); self.cog = cog; self.uid = uid
    @discord.ui.button(label="✅ Да", style=discord.ButtonStyle.green)
    async def yes(self, i, b):
        self.cog.service.delete(self.uid)
        await i.response.edit_message(embed=discord.Embed(title="🗑️ ПАСПОРТ УДАЛЁН", description=f"<@{self.uid}>", color=discord.Color.red()), view=None)
    @discord.ui.button(label="❌ Нет", style=discord.ButtonStyle.gray)
    async def no(self, i, b):
        await i.response.edit_message(embed=discord.Embed(title="❌ УДАЛЕНИЕ ОТМЕНЕНО", color=discord.Color.dark_gray()), view=None)


class PassportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = PassportService(bot.db)
        self.message_id: int | None = None

    async def start(self):
        self.bot.add_view(PassportUI(self))
        self.bot.add_view(AddPassportView(self))
        await self.update_terminal()

    async def ensure_terminal(self):
        if not self.message_id:
            await self.update_terminal(); return
        try:
            ch = await self.bot.fetch_channel(self.bot.settings.passport_channel)
            await ch.fetch_message(self.message_id)
        except Exception:
            self.message_id = None
            await self.update_terminal()

    async def update_terminal(self):
        ch = await self.bot.fetch_channel(self.bot.settings.passport_channel)
        if self.message_id:
            try:
                msg = await ch.fetch_message(self.message_id)
                await msg.edit(embed=passport_embed(), view=PassportUI(self))
                return
            except Exception:
                self.message_id = None
        async for m in ch.history(limit=20):
            if m.author == self.bot.user and m.embeds and "РЕЕСТР WAYNE" in (m.embeds[0].title or ""):
                self.message_id = m.id
                await m.edit(embed=passport_embed(), view=PassportUI(self))
                return
        msg = await ch.send(embed=passport_embed(), view=PassportUI(self))
        await safe_pin(msg)
        self.message_id = msg.id
