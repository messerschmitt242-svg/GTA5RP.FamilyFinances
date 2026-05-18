from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

from core.utils import clear_channel, safe_pin

CAR_LOG_ROLES = [1345267230300049408, 1447306587571228672]


class CarService:
    def __init__(self, db):
        self.db = db

    def add(self, name: str, image: str) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO cars (name, image) VALUES (?, ?)", (name, image))

    def delete(self, car_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM cars WHERE id=?", (car_id,))

    def update_image(self, car_id: int, image: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE cars SET image=? WHERE id=?", (image, car_id))

    def all(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, name, image, taken_by FROM cars ORDER BY name ASC").fetchall()

    def available(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, name, image FROM cars WHERE taken_by IS NULL ORDER BY name ASC").fetchall()

    def taken(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, name, image, taken_by FROM cars WHERE taken_by IS NOT NULL ORDER BY name ASC").fetchall()

    def name(self, car_id: int) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT name FROM cars WHERE id=?", (car_id,)).fetchone()
            return row[0] if row else None

    def take(self, car_id: int, uid: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute("UPDATE cars SET taken_by=? WHERE id=? AND taken_by IS NULL", (str(uid), car_id))
            return cur.rowcount > 0

    def return_car(self, car_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE cars SET taken_by=NULL WHERE id=?", (car_id,))

    def add_log(self, action: str, car_name: str, uid: int) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO car_logs (action, car_name, user_id, time) VALUES (?, ?, ?, ?)", (action, car_name, str(uid), datetime.now().strftime("%d.%m %H:%M")))

    def logs(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT action, car_name, user_id, time FROM car_logs ORDER BY id DESC LIMIT 10").fetchall()


def car_embed(service: CarService) -> discord.Embed:
    available = len(service.available())
    taken = len(service.taken())
    return discord.Embed(
        title="🚘 АВТОПАРК WAYNE INC.",
        description=(
            "```fix\nСИСТЕМА ВЫДАЧИ ТРАНСПОРТА\n```\n\n"
            f"🚗 Свободно: {available}\n────────────────────\n\n"
            f"🔒 Выдано: {taken}\n────────────────────\n\n"
            "⚙️ Используйте кнопки ниже"
        ),
        color=discord.Color.dark_teal(),
    )


class AvailableSingleCarView(discord.ui.View):
    def __init__(self, cog: "CarsCog", car):
        super().__init__(timeout=300)
        self.cog = cog
        self.car = car

    @discord.ui.button(label="🚘 Забронировать автомобиль", style=discord.ButtonStyle.green)
    async def take(self, i, b):
        await i.response.defer()

        try:
            ok = self.cog.service.take(self.car["id"], i.user.id)
            if not ok:
                return await i.edit_original_response(
                    content="❌ Автомобиль уже занят",
                    embed=None,
                    view=None,
                )

            self.cog.service.add_log("ВЗЯТ", self.car["name"], i.user.id)
            await self.cog.update_terminal()
            await i.edit_original_response(
                content="✅ Автомобиль забронирован",
                embed=None,
                view=None,
            )
        except Exception as exc:
            print(f"CAR TAKE ERROR: {exc}")
            await i.edit_original_response(
                content="❌ Ошибка при бронировании автомобиля. Проверьте логи Railway.",
                embed=None,
                view=None,
            )


class TakenSingleCarView(discord.ui.View):
    def __init__(self, cog: "CarsCog", car):
        super().__init__(timeout=300)
        self.cog = cog
        self.car = car

    @discord.ui.button(label="🔓 Вернуть автомобиль", style=discord.ButtonStyle.red)
    async def return_car_btn(self, i, b):
        await i.response.defer()

        try:
            self.cog.service.return_car(self.car["id"])
            self.cog.service.add_log("ВОЗВРАЩЕН", self.car["name"], i.user.id)
            await self.cog.update_terminal()
            await i.edit_original_response(
                content="✅ Автомобиль возвращен",
                embed=None,
                view=None,
            )
        except Exception as exc:
            print(f"CAR RETURN ERROR: {exc}")
            await i.edit_original_response(
                content="❌ Ошибка при возврате автомобиля. Проверьте логи Railway.",
                embed=None,
                view=None,
            )


class CarUI(discord.ui.View):
    def __init__(self, cog: "CarsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🚘 Доступные автомобили", style=discord.ButtonStyle.green, custom_id="cars_available")
    async def available(self, i, b):
        cars = self.cog.service.available()
        if not cars:
            return await i.response.send_message("❌ Нет свободных автомобилей", ephemeral=True, delete_after=15)
        await i.response.send_message("🚘 Список доступных автомобилей:", ephemeral=True)
        for idx, car in enumerate(cars, start=1):
            embed = discord.Embed(title=f"{idx}. {car['name']}", color=discord.Color.dark_teal())
            embed.set_image(url=car["image"])
            await i.followup.send(embed=embed, view=AvailableSingleCarView(self.cog, car), ephemeral=True)

    @discord.ui.button(label="🔒 Вернуть автомобиль", style=discord.ButtonStyle.red, custom_id="cars_return")
    async def return_btn(self, i, b):
        cars = self.cog.service.taken()
        if not cars:
            return await i.response.send_message("❌ Нет выданных автомобилей", ephemeral=True, delete_after=15)
        await i.response.send_message("🔒 Список занятых автомобилей:", ephemeral=True)
        for idx, car in enumerate(cars, start=1):
            embed = discord.Embed(title=f"{idx}. {car['name']} [НЕДОСТУПЕН]", color=discord.Color.red())
            embed.set_image(url=car["image"])
            await i.followup.send(embed=embed, view=TakenSingleCarView(self.cog, car), ephemeral=True)

    @discord.ui.button(label="📜 Логи", style=discord.ButtonStyle.gray, custom_id="cars_logs")
    async def logs(self, i, b):
        if not any(role.id in CAR_LOG_ROLES for role in i.user.roles):
            return await i.response.send_message("❌ Нет доступа", ephemeral=True)
        data = self.cog.service.logs()
        desc = "\n".join([f"[{r['time']}] {r['action']} | {r['car_name']} | <@{r['user_id']}>" for r in data]) or "Нет логов"
        await i.response.send_message(embed=discord.Embed(title="📜 ЛОГИ АВТОПАРКА", description=desc, color=discord.Color.dark_teal()), ephemeral=True)


class DeleteCarSelect(discord.ui.Select):
    def __init__(self, cog, options):
        super().__init__(placeholder="Выберите автомобиль...", options=options)
        self.cog = cog
    async def callback(self, interaction):
        car_id = int(self.values[0])
        name = self.cog.service.name(car_id)
        if not name:
            return await interaction.response.send_message("❌ Автомобиль не найден", ephemeral=True)
        self.cog.service.delete(car_id)
        await self.cog.update_terminal()
        await interaction.response.edit_message(content=f"✅ Автомобиль удалён: {name}", view=None)


class ChangeCarSelect(discord.ui.Select):
    def __init__(self, cog, options):
        super().__init__(placeholder="Выберите автомобиль...", options=options)
        self.cog = cog
    async def callback(self, interaction):
        await interaction.response.send_modal(ChangeCarModal(self.cog, int(self.values[0])))


class ChangeCarModal(discord.ui.Modal, title="Изменить фото автомобиля"):
    image = discord.ui.TextInput(label="Новая ссылка на изображение")
    def __init__(self, cog, car_id):
        super().__init__(); self.cog = cog; self.car_id = car_id
    async def on_submit(self, i):
        self.cog.service.update_image(self.car_id, self.image.value.strip())
        await self.cog.update_terminal()
        await i.response.send_message("✅ Фото автомобиля обновлено", ephemeral=True)


class CarsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = CarService(bot.db)
        self.message_id: int | None = None

    async def start(self):
        self.bot.add_view(CarUI(self))
        await self.update_terminal()

    async def ensure_terminal(self):
        if not self.message_id:
            await self.update_terminal(); return
        try:
            ch = await self.bot.fetch_channel(self.bot.settings.car_channel)
            await ch.fetch_message(self.message_id)
        except Exception:
            self.message_id = None
            await self.update_terminal()

    async def update_terminal(self):
        ch = await self.bot.fetch_channel(self.bot.settings.car_channel)
        embed = car_embed(self.service)
        if self.message_id:
            try:
                msg = await ch.fetch_message(self.message_id)
                await msg.edit(embed=embed, view=CarUI(self))
                return
            except Exception:
                self.message_id = None
        await clear_channel(ch)
        msg = await ch.send(embed=embed, view=CarUI(self))
        await safe_pin(msg)
        self.message_id = msg.id

    def _admin_channel_ok(self, i: discord.Interaction) -> bool:
        return i.channel and i.channel.id == self.bot.settings.car_admin_channel

    @app_commands.command(name="add_car")
    @app_commands.guild_only()
    async def add_car_cmd(self, i: discord.Interaction, name: str, image: discord.Attachment):
        if not self._admin_channel_ok(i):
            return await i.response.send_message("❌ Не тот канал", ephemeral=True)
        self.service.add(name, image.url)
        await self.update_terminal()
        await i.response.send_message(f"✅ Добавлен автомобиль: {name}", ephemeral=True)

    @app_commands.command(name="delete_car")
    @app_commands.guild_only()
    async def delete_car_cmd(self, i: discord.Interaction):
        if not self._admin_channel_ok(i):
            return await i.response.send_message("❌ Не тот канал", ephemeral=True)
        cars = self.service.all()
        if not cars:
            return await i.response.send_message("❌ Автомобилей нет", ephemeral=True)
        options = [discord.SelectOption(label=car["name"][:100], value=str(car["id"])) for car in cars[:25]]
        view = discord.ui.View(timeout=60)
        view.add_item(DeleteCarSelect(self, options))
        await i.response.send_message("🗑️ Выберите автомобиль:", view=view, ephemeral=True)

    @app_commands.command(name="change_car")
    @app_commands.guild_only()
    async def change_car_cmd(self, i: discord.Interaction):
        if not self._admin_channel_ok(i):
            return await i.response.send_message("❌ Не тот канал", ephemeral=True)
        cars = self.service.all()
        if not cars:
            return await i.response.send_message("❌ Автомобилей нет", ephemeral=True)
        options = [discord.SelectOption(label=car["name"][:100], value=str(car["id"])) for car in cars[:25]]
        view = discord.ui.View(timeout=60)
        view.add_item(ChangeCarSelect(self, options))
        await i.response.send_message("🛠️ Выберите автомобиль:", view=view, ephemeral=True)
