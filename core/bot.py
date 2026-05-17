import discord
from discord.ext import commands, tasks

from core.config import Settings
from core.database import Database
from modules.bank.cog import BankCog
from modules.passports.cog import PassportCog
from modules.cars.cog import CarsCog
from modules.bp.cog import BPCog
from modules.contracts.cog import ContractsCog


class WayneBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        intents.members = True

        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.settings = settings
        self.db = db
        self.guild_object = discord.Object(id=settings.guild_id)
        self._ready_once = False

    async def setup_hook(self) -> None:
        await self.add_cog(BankCog(self))
        await self.add_cog(PassportCog(self))
        await self.add_cog(CarsCog(self))
        await self.add_cog(BPCog(self))
        await self.add_cog(ContractsCog(self))
        self.tree.copy_global_to(guild=self.guild_object)
        await self.tree.sync(guild=self.guild_object)

    async def on_ready(self) -> None:
        print(f"WAYNE BOT ONLINE: {self.user} ({self.user.id})")
        if self._ready_once:
            return
        self._ready_once = True

        for cog in self.cogs.values():
            starter = getattr(cog, "start", None)
            if starter:
                await starter()

        if not self.terminal_guard.is_running():
            self.terminal_guard.start()

    @tasks.loop(seconds=30)
    async def terminal_guard(self) -> None:
        for cog_name in ("BankCog", "PassportCog", "CarsCog", "BPCog", "ContractsCog"):
            cog = self.get_cog(cog_name)
            if not cog:
                continue
            updater = getattr(cog, "ensure_terminal", None)
            if updater:
                try:
                    await updater()
                except Exception as exc:
                    print(f"{cog_name} terminal error: {exc}")

    @terminal_guard.before_loop
    async def before_terminal_guard(self) -> None:
        await self.wait_until_ready()
