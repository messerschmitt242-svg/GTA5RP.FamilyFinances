from pathlib import Path
import tempfile
import discord

from modules.ocr.scanner import TemplateOcrScanner
from modules.contracts.services import ContractService


class PersonnelService:
    def __init__(self, db):
        self.contracts = ContractService(db)
        self.scanner = TemplateOcrScanner()

    async def parse_attachment(self, attachment: discord.Attachment, rp_name: str, discord_id: int, discord_name: str) -> dict[str, int]:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / (attachment.filename or "personnel.png")
            await attachment.save(path)
            values = self.scanner.parse_image(str(path))
            self.contracts.upsert_profile(rp_name, discord_id, discord_name, values)
            return values
