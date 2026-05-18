import discord
from discord.ext import commands

from core.config import Settings
from core.database import Database

from modules.bank.cog import BankCog
from modules.passports.cog import PassportCog
from modules.cars.cog import CarsCog
from modules.bp.cog import BPCog
from modules.contracts.cog import ContractsCog
from modules.music.cog import MusicCog


class WayneBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        intents.members = True
        intents.voice_states = True

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
        await self.add_cog(MusicCog(self))

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
